# Copyright 2013, 2014 Pawel Daniluk, Bartek Wilczynski
#
# This file is part of WeBIAS.
#
# WeBIAS is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.
#
# WeBIAS is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License along with WeBIAS. If not, see
# <http://www.gnu.org/licenses/>.

import time, os, sys, traceback, platform
import sqlalchemy
import data
import glob
import imp
from genshi.template import NewTextTemplate
import gnosis.xml.objectify as objectify
import template

import statistics

import scheduler.interfaces.slurm

import cherrypy

SLEEP_TIME=5

config=None


class LockPlugin(cherrypy.process.plugins.SimplePlugin):
    def __init__(self, bus, sched_id, config, forcelock=False):
        self.forcelock = forcelock
        self.sched_id = sched_id
        self.config = config
        self.engine = sqlalchemy.create_engine(config.DB_URL, echo=False)
        self.engine.connect();
        self.Session = sqlalchemy.orm.sessionmaker(bind=self.engine)
        cherrypy.process.plugins.SimplePlugin.__init__(self, bus)

    def grab_lock(self):
        session=self.Session()

        dbsched=session.query(data.Scheduler).get(self.sched_id)

        if dbsched==None:
            dbsched=data.Scheduler(self.sched_id)
            session.add(dbsched)
            try:
                session.commit()
            except:
                pass

        try:
            dbsched=session.query(data.Scheduler).with_lockmode('update').get(self.sched_id)

            if dbsched.status!='STOPPED':
                raise Exception("Scheduler %s already has status %s." % (self.sched_id, dbsched.status))

            dbapps=[]

            try:
                self.config.APPS
            except:
                self.config.APPS=None

            if self.config.APPS != None:
                dbapps=session.query(data.Application).filter(data.Application.id.in_(self.config.APPS)).all()
            else:
                dbapps=session.query(data.Application).all()

            dbsched.apps=dbapps
            dbsched.status='RUNNING'

            pid=str(os.getpid())
            host=platform.node()
            status='NORMAL'
            lock_start=time.strftime("%Y-%m-%d %H:%M:%S")

            dbschedlock=data.SchedulerLock(dbsched, pid, host, status, lock_start)
            session.add(dbschedlock)

            session.commit()
            session.close()
            return True
        except Exception, e:
            session.close()
            cherrypy.engine.log("Failed to grab scheduler lock. %s" % e)
            return False



    def release_lock(self, status='NORMAL'):
        session=self.Session()

        try:
            dbsched=session.query(data.Scheduler).with_lockmode('update').get(self.sched_id)

            if dbsched.status!='STOPPED':
                dbsched.status='STOPPED'
                for dbschedlock in dbsched.locks:
                    if dbschedlock.lock_end==None:
                        dbschedlock.lock_end=time.strftime("%Y-%m-%d %H:%M:%S")
                        dbschedlock.status=status

                session.commit()
            else:
                raise Exception("Scheduler %s is already stopped." % (self.sched_id))

            session.close()
            return True
        except Exception, e:
            session.close()
            cherrypy.engine.log("Failed to release scheduler lock. %s\n" % e)
            return False

    def start(self):
        if self.forcelock:
            self.release_lock('FORCED')
            cherrypy.engine.log("Forcefully released scheduler lock.")
            self.started = False
        else:
            self.started = self.grab_lock()

        if not self.started:
            cherrypy.engine.exit()


    def stop(self):
        if self.started:
            self.release_lock()

    start.priority = 70


class SchedulerPlugin(cherrypy.process.plugins.Monitor):
    def __init__(self, bus, sched_id, config, queue_interface):
        self.config = config
        self.slots = config.SLOTS
        self.running = 0
        self.sched_id = sched_id
        self.frequency = SLEEP_TIME
        self.engine = sqlalchemy.create_engine(config.DB_URL, echo=False, pool_recycle=1800)
        self.engine.connect()
        self.Session = sqlalchemy.orm.sessionmaker(bind=self.engine)
        self.templateProcessor = template.TemplateProcessor(config)
        self.queue_interface = queue_interface
        cherrypy.process.plugins.Monitor.__init__(self, bus, self.run, self.frequency)


    def run(self):
        try:
            self.reap()
            self.sow()
        except RuntimeError, msg:
            if msg:
                cherrypy.engine.log(msg)


    def running_reqs(self, session):
        reqs=session.query(data.Request).filter(data.Request.status == 'PROCESSING', data.Request.sched_id == self.sched_id).all()
        return reqs

    def get_uncollected_runs(self, session):
        runs=session.query(data.Run).join(data.Request).filter(data.Run.status == 'RUNNING', data.Request.sched_id == self.sched_id).all()

        for run in runs:
            if not self.queue_interface.is_running(run.pid):
                yield run

    def grab_request(self, session):
        dbsched=session.query(data.Scheduler).get(self.sched_id)

        req=session.query(data.Request).filter(data.Request.status == 'READY', data.Request.sched == None, data.Request.app_id.in_(self.config.APPS)).with_lockmode('update').first()

        if req != None:
            req.sched = dbsched
            session.commit()

        return req

    def get_request_by_id(self, session, id):
        return session.query(data.Request).get(id)

    def get_run_by_id(self, session, id):
        return session.query(data.Run).get(id)

    def launch(self, session, req):
        from tempfile import mkstemp
        from os import write,close
        import os

        run = data.Run(req, time.strftime("%Y-%m-%d %H:%M:%S"))

        session.add(run)
        session.commit()

        try:
            JOB_DIR = run.get_job_dir(self.config.WRK_DIR)
            os.makedirs(JOB_DIR)

            query = objectify.make_instance(req.query, p=objectify.DOM)

            cmd = NewTextTemplate(req.app.param_template).generate(**query.__dict__).render('text').strip()

            fh = open(JOB_DIR+'/'+self.config.CMD_FILE,'w')
            fh.write(cmd)
            fh.close()

            files = session.query(data.File).filter(data.File.request == req, data.File.type == 'input')

            for f in files:
                f.write(JOB_DIR)

            pid = self.queue_interface.queue_run(JOB_DIR,self.config.CMD_FILE,self.config.ERR_FILE,self.config.RES_FILE, self.config)

            self.running += 1

            run.status = 'RUNNING'
            run.pid = pid
            req.status = 'PROCESSING'
            cherrypy.engine.log("Executed run %d, for request %d under PID=%d" % (run.id,req.id,pid))
        except:
            cherrypy.engine.log("Failed to execute run %d, for request %d." % (run.id,req.id))
            cherrypy.engine.log(''.join(traceback.format_exception(*sys.exc_info())))
            run.status = 'FAILED'
            req.status = 'FAILED'

        session.commit()


    def collect(self, session, run):

        job_dir = run.get_job_dir(self.config.WRK_DIR)

        resfile = '%s/%s' % (job_dir, self.config.RES_FILE)
        errfile = '%s/%s' % (job_dir, self.config.ERR_FILE)

        ok = False

        self.running -= 1

        try:
            err = open(errfile,'r').read()
            if err.strip() == 'OK':
                ok = True
        except:
            pass

        req = run.request

        if ok:
            run.status = 'FINISHED'
            req.status = 'FINISHED'
            run.result = open(resfile, 'r').read()
            template = 'system/email/finished.genshi'

            files = sum([glob.glob(p) for p in ['%s/%s'%(job_dir, p) for p in req.app.output_files.split()]],[])

            for fname in files:
                (path,name) = data.File.split_name(fname[len(job_dir)+1:])

                file = data.File(request=req, run=run, path=path, name=name, data=open(fname,'r').read(), type='output')
                session.add(file)
            cherrypy.engine.log("Colleted run %d, for request %d." % (run.id, req.id))
        else:
            run.status = 'FAILED'
            req.status = 'FAILED'
            template = 'system/email/failed.genshi'
            cherrypy.engine.log("Failed to collect run %d, for request %d." % (run.id, req.id))

        session.commit()

        if req.user.id > 0:
            args = TemplateArgs(req.app)
            args.uuid = req.uuid
            self.templateProcessor.email_message(req.user.e_mail, template, app=req.app, uuid=req.uuid)

    def ping(self, session):
        dbsched = session.query(data.Scheduler).get(self.sched_id)
        dbsched.last_act = time.strftime("%Y-%m-%d %H:%M:%S")
        session.commit()

    def last_ping(self, session):
        dbsched = session.query(data.Scheduler).get(self.sched_id)
        last_act = time.mktime(time.strptime(str(dbsched.last_act), "%Y-%m-%d %H:%M:%S"))
        return time.mktime(time.localtime())-last_act

    def reap(self):
        session = self.Session()
        self.ping(session)
        for run in self.get_uncollected_runs(session):
            self.collect(session,run)
        session.close()

    def sow(self):
        session=self.Session()

        self.ping(session)
        while self.slots == 0 or self.slots > self.running:
            req = self.grab_request(session)
            if req:
                self.launch(session,req)
            else:
                break

        session.close()


def main():
    import sys
    from optparse import OptionParser

    parser = OptionParser()
    parser.add_option("--foreground", action="store_true", dest="foreground")
    parser.add_option("--removelock", action="store_true", dest="removelock")
    (options, args)=parser.parse_args()

    config_file=args[0]

    if not os.path.exists(config_file):
        config_file+='.py'

    try:
        config=imp.load_source('config', config_file)
    except:
        print "Cannot load config file: %s\n" % (config_file)
        sys.exit(2)

    try:
        sched_id=args[1]
    except:
        sched_id=config.SCHED_ID

    if options.removelock:
        statistics.DBLogPlugin(cherrypy.engine, sched_id=sched_id).subscribe()
        LockPlugin(cherrypy.engine, sched_id, config, forcelock=True).subscribe()
        cherrypy.engine.start()
        cherrypy.engine.block()


    from cherrypy.process.plugins import Daemonizer, PIDFile, DropPrivileges
#    DropPrivileges(cherrypy.engine, umask=0022, uid=1044, gid=1000).subscribe()


    PIDFile(cherrypy.engine, config.PID_FILE).subscribe()
    cherrypy.engine.signal_handler.subscribe()
    statistics.DBLogPlugin(cherrypy.engine, sched_id=sched_id).subscribe()

    LockPlugin(cherrypy.engine, sched_id, config).subscribe()
    SchedulerPlugin(cherrypy.engine, sched_id, config, interfaces.slurm).subscribe()

    cherrypy.server.unsubscribe()

    if not options.foreground:
        cherrypy.process.plugins.Daemonizer(cherrypy.engine).subscribe()

    cherrypy.engine.start()
    cherrypy.engine.block()
