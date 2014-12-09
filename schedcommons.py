# Copyright 2013 Pawel Daniluk, Bartek Wilczynski
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

from daemon import Daemon
import time, syslog, os, sys, traceback, platform
import sqlalchemy
import data
import glob
import imp
from genshi.template import NewTextTemplate
import gnosis.xml.objectify as objectify
from template import *

SLEEP_TIME=5

config=None

class SchedDaemon(Daemon):


    def __init__(self, sched_class):
        global config

        self.ops={
            'start': self.start,
            'stop': self.stop,
            'restart': self.restart,
            'foreground': self.foreground,
            'removelock': self.removelock,
            'ensurerunning': self.ensurerunning
        }

        if len(sys.argv) >= 3:
            self.op=sys.argv[1]
            self.config_file=sys.argv[2]

            if self.op not in self.ops.keys():
                print "Unknown command"
                sys.exit(2)

            if not os.path.exists(self.config_file):
                self.config_file+='.py'

            try:
                config=imp.load_source('config', self.config_file)
            except:
                print "Cannot load config file: %s\n" % (self.config_file)
                sys.exit(2)

            if len(sys.argv) >= 4:
                self.sched_id=sys.argv[3]
            else:
                try:
                    self.sched_id=config.SCHED_ID
                except:
                    self.sched_id=sched_class.default_id
        else:
            print "usage: %s start|stop|restart|foreground|removelock|ensurerunning config_file [sched_id]" % sys.argv[0]
            sys.exit(2)


        Daemon.__init__(self, ident=self.sched_id)
        self.sched_class=sched_class

    def schedrun(self):
        self.ops.get(self.op)()


    def run(self):
        self.scheduler=self.sched_class(self.sched_id, config)
        self.scheduler.grab_lock()
        self.scheduler.run()
        self.scheduler.release_lock()

    def stop(self):
        self.scheduler=self.sched_class(self.sched_id, config)
        self.scheduler.get_lock()
        if(self.scheduler.host != platform.node()):
            raise Exception("Scheduler %s is running on a different host (%s)." % (self.sched_id, self.scheduler.host))

        Daemon.stop(self,self.scheduler.pid)


    def cleanup(self):
        print "Cleanup called\n"
        self.scheduler.terminate=True

    def removelock(self):
        self.scheduler=self.sched_class(self.sched_id, config)
        self.scheduler.release_lock('FORCED')

    def ensurerunning(self):
        self.scheduler=self.sched_class(self.sched_id, config)
        self.scheduler.get_lock()
        if(self.scheduler.host != platform.node()):
            msg="Scheduler %s is running on a different host (%s)." % (self.sched_id, self.scheduler.host)
            syslog.syslog(msg)
            raise Exception(msg)

        pid=self.scheduler.pid

        if self.isrunning(pid):
            secs=self.scheduler.last_ping(self.scheduler.Session())
            if secs > 5 * SLEEP_TIME:
                msg="Scheduler %s (PID %s) is running but seems unresponsive (last activity %d seconds ago)."%(self.sched_id, pid, int(secs+0.5))
                syslog.syslog(msg)
                print msg
            else:
                msg="Scheduler %s (PID %s) seems to be healthy."%(self.sched_id, pid)
                syslog.syslog(msg)
                print msg
                return
        else:
            msg="Scheduler %s (PID %s) is not running."%(self.sched_id, pid)
            syslog.syslog(msg)
            print msg

        msg="Restarting scheduler %s."%(self.sched_id)
        syslog.syslog(msg)
        print msg

        self.removelock()
        self.start()


class Scheduler:
    default_id='default'

    def __init__(self,sched_id,config):
        self.config=config
        self.slots=config.SLOTS
        self.running=0
        self.sched_id=sched_id
        self.engine= sqlalchemy.create_engine(config.DB_URL, echo=False, pool_recycle=1800)
        self.engine.connect()
        self.Session=sqlalchemy.orm.sessionmaker(bind=self.engine)
        self.terminate=False
        self.templateProcessor=TemplateProcessor(config)

    def run_once(self):
        self.reap()
        time.sleep(SLEEP_TIME)
        self.sow()

    def run(self):
        while not self.terminate:
            try:
                self.run_once()
                time.sleep(SLEEP_TIME)
            except RuntimeError,msg:
                if msg:
                    syslog.syslog(msg)

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

        got_lock=False
        try:
            dbsched=session.query(data.Scheduler).with_lockmode('update').get(self.sched_id)

            if dbsched.status!='STOPPED':
                raise Exception("Scheduler %s already has status %s." % (self.sched_id, dbsched.status))

            dbapps=[]

            try:
                config.APPS
            except:
                config.APPS=None

            if config.APPS != None:
                dbapps=session.query(data.Application).filter(data.Application.id.in_(config.APPS)).all()
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
        except Exception, e:
            print "Failed to grab scheduler lock. %s\n" % (e)
            traceback.print_exc()
            if got_lock:
                self.release_lock('FAILED')
            sys.exit(2)

        session.close();


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
        except Exception, e:
            print "Failed to release scheduler lock. %s\n" % (e)
            session.close()
            sys.exit(2)
        session.close()

    def get_lock(self):
        session=self.Session()

        try:
            dbsched=session.query(data.Scheduler).get(self.sched_id)

            if dbsched.status!='STOPPED':
                for dbschedlock in dbsched.locks:
                    if dbschedlock.lock_end==None:
                        self.pid=dbschedlock.pid
                        self.host=dbschedlock.host

            else:
                raise Exception("Scheduler %s is not running." % (self.sched_id))
        except Exception, e:
            print "Failed to get lock info. %s\n" % (e)
            session.close()
            sys.exit(2)

        session.close()

    def running_reqs(self):
        reqs=data.Requests(self.conn)
        reqs.get_all("status='PROCESSING' AND sched_id='%s'"%self.sched_id)
        return reqs


    def get_uncollected_runs(self,session):
        runs=session.query(data.Run).join(data.Request).filter(data.Run.status=='RUNNING', data.Request.sched_id == self.sched_id).all()

        for run in runs:
            if not self.is_running(run.pid):
                yield run

    def grab_request(self,session):
        dbsched=session.query(data.Scheduler).get(self.sched_id)

        req=session.query(data.Request).filter(data.Request.status=='READY', data.Request.sched == None, data.Request.app_id.in_(config.APPS)).with_lockmode('update').first()

        if req != None:
            req.sched=dbsched
            session.commit()

        return req

    def get_request_by_id(self,id):
        self.conn.execute("SELECT * from Requests where id=%d"%id)
        request = self.conn.fetchone()
        return Request(self.conn,*request)

    def get_run_by_id(self,id):
        self.conn.execute("SELECT * from Runs where id=%d and sched_id='%s'"%(id,self.sched_id))
        run = self.conn.fetchone()
        return Run(self.conn,*run)

    def launch(self,session,req):
        from tempfile import mkstemp
        from os import write,close
        import os


        run=data.Run(req, time.strftime("%Y-%m-%d %H:%M:%S"))

        session.add(run)
        session.commit()

        try:
            JOB_DIR=run.get_job_dir(config.WRK_DIR)
            os.makedirs(JOB_DIR)

            query=objectify.make_instance(req.query, p=objectify.DOM)

            cmd=NewTextTemplate(req.app.param_template).generate(**query.__dict__).render('text').strip()

            fh=open(JOB_DIR+'/'+config.CMD_FILE,'w')
            fh.write(cmd)
            fh.close()


            files=session.query(data.File).filter(data.File.request == req, data.File.type == 'input')

            for f in files:
                f.write(JOB_DIR)

            pid = self.queue_run(JOB_DIR,config.CMD_FILE,config.ERR_FILE,config.RES_FILE)

            self.running+=1

            run.status='RUNNING'
            run.pid=pid
            req.status='PROCESSING'
            print "executed run %d, for request %d under PID=%d"%(run.id,req.id,pid)
        except:
            print "failed to execute run %d, for request %d"%(run.id,req.id)
            traceback.print_exc()
            run.status='FAILED'
            req.status='FAILED'

        session.commit()


    def collect(self,session,run):

        job_dir=run.get_job_dir(config.WRK_DIR)

        resfile='%s/%s'%(job_dir,config.RES_FILE)
        errfile='%s/%s'%(job_dir,config.ERR_FILE)

        ok=False

        self.running-=1

        try:
            err=open(errfile,'r').read()
            if err.strip()=='OK':
                ok=True
        except:
            pass

        req=run.request

        if ok:
            run.status='FINISHED'
            req.status='FINISHED'
            run.result=open(resfile,'r').read()
            template='system/email/finished.genshi'

#            files=[os.path.basename(f) for f in sum([glob.glob(p) for p in ['%s/%s'%(job_dir, p) for p in app.output_files]],[])]
            files=sum([glob.glob(p) for p in ['%s/%s'%(job_dir, p) for p in req.app.output_files.split()]],[])

#            print "Globbing: "+str(req.app.output_files.split())
#            print "Files: "+str(files)

            for fname in files:
                (path,name)=data.File.split_name(fname[len(job_dir)+1:])

                file=data.File(request=req, run=run, path=path, name=name, data=open(fname,'r').read(), type='output')
                session.add(file)
        else:
            run.status='FAILED'
            req.status='FAILED'
            template='system/email/failed.genshi'

        session.commit()

        if(req.user.id>0):
            args=TemplateArgs(req.app)
            args.uuid=req.uuid
            self.templateProcessor.email_message(req.user.e_mail, template, app=req.app, uuid=req.uuid)

    def is_running(self,pid):
        """
        This function should be implemented in executable scheduler module.
        id variable is used for passing running job pid from database for
        determination of job's status.
        The function hast to return True if the job is running and False if it is not.
        """
        raise NotImplementedError


    def queue_run(self,JOB_DIR,command,errfile,outfile):
        """
        This function should be implemented in executable scheduler module.
        JOB_DIR specifies where the job has to be run and where the results are going to be stored.
        command is the path to file with command line which should be executed by runner
        output is the path to output file
        run_id is jobs id in the BIAS database
        The function hast to return pid of the submitted job.
        """
        raise NotImplementedError

    def ping(self, session):
        dbsched=session.query(data.Scheduler).get(self.sched_id)
        dbsched.last_act=time.strftime("%Y-%m-%d %H:%M:%S")
        session.commit()

    def last_ping(self, session):
        dbsched=session.query(data.Scheduler).get(self.sched_id)
        last_act=time.mktime(time.strptime(str(dbsched.last_act), "%Y-%m-%d %H:%M:%S"))
        return time.mktime(time.localtime())-last_act

    def reap(self):
        session=self.Session()
        self.ping(session)
        for run in self.get_uncollected_runs(session):
            self.collect(session,run)
        session.close()

    def sow(self):
        session=self.Session()

        self.ping(session)
        while self.slots==0 or self.slots>self.running:
            req=self.grab_request(session)
            if req:
                self.launch(session,req)
            else:
                break

        session.close()




