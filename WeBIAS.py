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


class Bias:
    @staticmethod
    def scan_app_dir(session):
        apps=session.query(data.Application).all()

        files=[os.path.basename(n) for n in glob.glob('apps/*.xml')]

        for f in files:
            try:
                defin=objectify.make_instance('apps/'+f, p=objectify.DOM)
                apps=defin.application
            except:
                apps=[]
                print 'Invalid application definition: ', f
                traceback.print_exc()

            for app in apps:
                dbapp=session.query(data.Application).get(app.id)

                out_files=''

                if hasattr(app.setup, 'output_files'):
                    out_files=app.setup.output_files.PCDATA

                if dbapp==None:
                    dbapp=data.Application(app.id, f, app.setup.param_template.PCDATA, out_files, False)
                    session.add(dbapp)

    def __init__(self):
        engine = create_engine(config.DB_URL, echo=False)
        session=scoped_session(sessionmaker(autoflush=True, autocommit=False))
        session.configure(bind=engine)

        data.Base.metadata.create_all(engine)

        Bias.scan_app_dir(session)
        
        self.inactive_apps={}
        self.apps={}

        self.login=auth.Login()
        self.admin=admin.Admin()
        self.user=user.User()
        self.statistics=statistics.Statistics()

        dbapps=session.query(data.Application).all()

        for dbapp in dbapps:
            app=self.load_app(dbapp)

            if app!=None:
                if dbapp.enabled:
                    self.apps[app.id]=app
                else:
                    self.inactive_apps[app.id]=app

        session.commit()
        session.remove()
        engine.dispose()

        field.objectify_clean()

                
    def deregister(self,app_id):
        self.inactive_apps[app_id]=self.apps[app_id]
        del self.apps[app_id]

    def register(self,app_id):
        self.apps[app_id]=self.inactive_apps[app_id]
        del self.inactive_apps[app_id]

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

                    return app
        except:
            print "Cannot load %s required for application %s. Disabling.\n"%(filename, dbapp.id)
            print ''.join(traceback.format_exception(*sys.exc_info()))
            dbapp.enabled=False
            return None
    

    @cherrypy.expose
    @persistent
    def index(self):
        apps=filter(lambda app: auth.ForceLogin().match_acl(app.app_acl(), auth.get_login()),self.apps.values())

        return render('app_list.genshi',apps=apps)

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


    def _cp_dispatch(self, vpath):
        return self.apps.get(vpath[0],None)


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

    cherrypy.tree.mount(Bias(),config.APP_ROOT, config={'/': conf, '/media':mediaconf})
    
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
    
    
