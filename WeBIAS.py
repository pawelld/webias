#!/usr/bin/python
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


import cherrypy
import sys

import gnosis.xml.objectify as objectify

objectify.keep_containers(1)

import config
import os,glob

import field
import data 

import auth
import admin
import user
import application
import statistics

import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from util import *

import traceback


sys.path.append(config.BIAS_DIR+"/modules")


class WeBIAS:
    @staticmethod
    def scan_app_dir(session):
        apps=session.query(data.Application).all()

        files=glob.glob(config.BIAS_DIR+'/apps/*.xml')

        defs={}

        for f in files:
            try:
                defin=objectify.make_instance(f, p=objectify.DOM)
            except:
                defin=None
                print 'Invalid application definition: ', f
                traceback.print_exc()

            apps=getattr(defin,'application', [])
            groups=getattr(defin,'group', [])

            for app in apps:
                if defs.has_key(app.id):
                    print 'Application %s defined in %s and redefined in %s.' % (app.id, defs[app.id], f)
                else:
                    defs[app.id]=f
                    dbapp=session.query(data.Application).get(app.id)

                    out_files=''

                    if hasattr(app.setup, 'output_files'):
                        out_files=app.setup.output_files.PCDATA

                    if dbapp==None:
                        dbapp=data.Application(app.id, os.path.basename(f), app.setup.param_template.PCDATA, out_files, False)
                        session.add(dbapp)

    def __init__(self):
        engine = create_engine(config.DB_URL, echo=False)
        session=scoped_session(sessionmaker(autoflush=True, autocommit=False))
        session.configure(bind=engine)

        data.Base.metadata.create_all(engine)

        WeBIAS.scan_app_dir(session)
        
        self.apps={}
        self.groups={}

        self.login=auth.Login()
        self.admin=admin.Admin()
        self.user=user.User()
        self.statistics=statistics.Statistics()

        dbapps=session.query(data.Application).all()

        for dbapp in dbapps:
            app=self.load_app(dbapp)

            if app!=None:
                self.apps[app.id]=app
                app.enabled=dbapp.enabled

        session.commit()
        session.remove()
        engine.dispose()

        self.server_map()
        field.objectify_clean()

    def server_map(self):
        try:
            filename=config.BIAS_DIR+'/apps/server_map.xml'
            defin=objectify.make_instance(filename, p=objectify.DOM)
            cherrypy.engine.autoreload.files.add(filename)
            self.store_groups(defin)
        except:
            print 'Invalid or missing server_map.xml.'

        d=dict(self.apps)
        d.update(self.groups)

        used=[]
        for gr in self.groups.values():
            gr.assign_elts(d)
            used.extend(gr.used_apps())
            used.remove(gr.id)


        all=dict(self.apps)
        all.update(self.groups)

        for id in used:
            all.pop(id,None)


        self.root=application.AppGroup(all.values())
        
    def store_groups(self, defin):
        try:
            groups=defin.appgroup
        except:
            groups=[]

        for gr in groups:
            self.groups[gr.id]=gr
        
                
    def deregister(self,app_id):
        self.apps[app_id].enabled=False

    def register(self,app_id):
        self.apps[app_id].enabled=True

    def load_app(self,dbapp):
        filename=config.BIAS_DIR+'/apps/'+dbapp.definition
        cherrypy.engine.autoreload.files.add(filename)

        try:
            defin=objectify.make_instance(filename, p=objectify.DOM)
            for app in defin.application:
                if app.id==dbapp.id:
                    app.dbapp=dbapp

                    if app.setup.param_template.PCDATA != dbapp.param_template:
                        print "Updating param_template for application %s.\n"%dbapp.id
                        dbapp.param_template=app.setup.param_template.PCDATA


                    out_files=''

                    if hasattr(app.setup, 'output_files'):
                        out_files=app.setup.output_files.PCDATA

                    if out_files != dbapp.output_files:
                        print "Updating output_files for application %s.\n"%dbapp.id
                        dbapp.output_files=app.setup.output_files.PCDATA

                    self.store_groups(defin)

                    return app
        except:
            print "Cannot load %s required for application %s. Disabling.\n"%(filename, dbapp.id)
            print ''.join(traceback.format_exception(*sys.exc_info()))
            dbapp.enabled=False
            return None
    

    @cherrypy.expose
    @persistent
    def index(self):
        return self.root.index()

#    @cherrypy.expose
#    def error(self):
#        raise cherrypy.HTTPError(500, 'Error example')
#
#    def auth_acl(self, login=None):
#        if login==None:
#            return ['any']
#        else:
#            return [[login]]
#
#    @cherrypy.expose
#    @auth.with_acl(auth_acl)
#    def auth(self, login=None):
#        return "Auth OK login::"+str(login)
#
#
#    @cherrypy.expose
#    def forcelogin(self):
#        def action():
#            return "Zalogowano"
#
#        auth.ForceLogin(action=action).do()
#
#
#    @cherrypy.expose
#    def lowerror(self):
#        abcabv.asd=0

    @cherrypy.expose
    def page(self, *path):
        import genshi.template
    
        for i in range(len(path), 0, -1):
            template='/'.join(['page']+list(path[0:i]))+'.genshi'
#            try:
            return render(template, par=path[i:])
#            except genshi.template.TemplateNotFound:
#                pass

        raise cherrypy.HTTPError(404)
            

    def _cp_dispatch(self, vpath):
        res=self.root._cp_dispatch(vpath)

        if not res:
            try:
                res=self.apps[vpath[0]]
            except:
                pass

        return res


if __name__=="__main__":
    import sys


    from optparse import OptionParser
    parser = OptionParser()
    parser.add_option("--changepw", action="store_true", dest="changepw")
    parser.add_option("--foreground", action="store_true", dest="foreground")
    (options, args)=parser.parse_args()

    if options.changepw:    
        auth.set_admin_pw()
        sys.exit(0)


    from cherrypy.process.plugins import Daemonizer, PIDFile, DropPrivileges
#    DropPrivileges(cherrypy.engine, umask=0022, uid=1044, gid=1000).subscribe()


    PIDFile(cherrypy.engine, config.PID_FILE).subscribe()
    cherrypy.engine.signal_handler.subscribe()  
    auth.CleanupUsers(cherrypy.engine).subscribe()
    data.SAEnginePlugin(cherrypy.engine).subscribe()
    cherrypy.tools.db = data.SATool()

    conf={
        'tools.db.on': True,
        'tools.hit_recorder.on': True,
        'tools.error_recorder.on': True,
        'tools.sessions.on': True,
        'tools.clean_session.on': True,
        'log.screen': False,
        'log.access_file': config.LOG_ACCESS,
        'log.error_file': config.LOG_ERROR,
        'tools.protect.on': True,
        'tools.protect.allowed': ['any']
    }

    mediaconf={
        'tools.staticdir.on': True,
        'tools.protect.on': False,
        'tools.staticdir.dir': config.BIAS_DIR+'/media'
    }

    cherrypy.tree.mount(WeBIAS(),config.APP_ROOT, config={'/': conf, '/media':mediaconf})
    
    cherrypy.config.update({
        'session_filter.on':True,
        "session_filter.timeout":600000
    })

    cherrypy.engine.templateProcessor=template.TemplateProcessor(config)

    if config.PROXY:
        cherrypy.config.update({
            'tools.proxy.on': True,
            'tools.https_filter.on': True,
            'server.thread_pool': 100,
            "server.socket_port": config.SERVER_PORT,
            'server.socket_host': config.SERVER_HOST
        })

    else:
        cherrypy.server.unsubscribe()

        server1 = cherrypy._cpserver.Server()
        server1.socket_port=config.SERVER_SSL_PORT
        server1._socket_host=config.SERVER_HOST
        server1.thread_pool=100
        server1.ssl_module = 'pyopenssl'
        server1.ssl_certificate = config.SSL_CERT;
        server1.ssl_private_key = config.SSL_KEY
        server1.ssl_certificate_chain = config.SSL_CERT_CHAIN
        server1.subscribe()

        server2 = cherrypy._cpserver.Server()
        server2.socket_port=config.SERVER_PORT
        server2._socket_host=config.SERVER_HOST
        server2.thread_pool=100
        server2.subscribe()

    if not options.foreground:
        cherrypy.process.plugins.Daemonizer(cherrypy.engine).subscribe()

    cherrypy.engine.start()
    cherrypy.engine.block()
    
    
