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
import os
import pkg_resources

import webias.gnosis.xml.objectify as objectify

objectify.keep_containers(1)

import os,glob

import field
import data

import auth
import admin
import user
import application
import statistics
import reports

import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from util import *

import traceback

import config

class WeBIAS:
    @staticmethod
    def scan_app_dir(session):
        apps=session.query(data.Application).all()

        files=glob.glob(config.server_dir + '/apps/*.xml')

        defs={}

        for f in files:
            try:
                defin=objectify.make_instance(f, p=objectify.DOM)
            except:
                defin=None
                cherrypy.engine.log('Invalid application definition: %s' % f)
                cherrypy.engine.log(''.join(traceback.format_exception(*sys.exc_info())))

            apps=getattr(defin,'application', [])
            groups=getattr(defin,'group', [])

            for app in apps:
                if defs.has_key(app.id):
                    cherrypy.engine.log('Application %s defined in %s and redefined in %s.' % (app.id, defs[app.id], f))
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
        engine = create_engine(config.get('Database', 'db_url'), echo=False)
        session=scoped_session(sessionmaker(autoflush=True, autocommit=False))
        session.configure(bind=engine)

        data.Base.metadata.create_all(engine)

        self.scan_app_dir(session)

        self.apps={}
        self.groups={}

        self.login=auth.Login()
        self.admin=admin.Admin()
        self.user=user.User()
        self.statistics=statistics.Statistics()
        self.reports=reports.Reports()

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

        self.no_SSL=False

    def navigation_bar(self):

        # ACLs given below determine link rendering only.
        full_list = [('', 'Application list', ['any']),
                     ('user/requests/', 'My requests', ['user']),
                     ('admin/', 'Administration panel', self.admin._acl),
                     ('statistics/', 'Statistics', self.statistics._acl),
                     ('reports/', 'Reports', self.reports._acl)]


        login = auth.get_login()

        return [(addr, descr) for (addr, descr, acl) in full_list if auth.ForceLogin.match_acl(acl, login)]




    def server_map(self):
        try:
            filename=config.server_dir + '/apps/server_map.xml'
            defin=objectify.make_instance(filename, p=objectify.DOM)
            cherrypy.engine.autoreload.files.add(filename)
            self.store_groups(defin)
        except:
            cherrypy.engine.log('Invalid or missing server_map.xml.')

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
        filename=config.server_dir + '/apps/' + dbapp.definition
        cherrypy.engine.autoreload.files.add(filename)

        try:
            defin=objectify.make_instance(filename, p=objectify.DOM)
            for app in defin.application:
                if app.id==dbapp.id:
                    app.dbapp=dbapp

                    if app.setup.param_template.PCDATA != dbapp.param_template:
                        cherrypy.engine.log("Updating param_template for application %s.\n"%dbapp.id)
                        dbapp.param_template=app.setup.param_template.PCDATA


                    out_files=''

                    if hasattr(app.setup, 'output_files'):
                        out_files=app.setup.output_files.PCDATA

                    if out_files != dbapp.output_files:
                        cherrypy.engine.log("Updating output_files for application %s.\n"%dbapp.id)
                        dbapp.output_files=app.setup.output_files.PCDATA

                    self.store_groups(defin)

                    return app
        except:
            cherrypy.engine.log("Cannot load %s required for application %s. Disabling.\n"%(filename, dbapp.id))
            cherrypy.engine.log(''.join(traceback.format_exception(*sys.exc_info())))
            dbapp.enabled=False
            return None


    @cherrypy.expose
    @persistent
    def index(self):
        return self.root.index()

    @cherrypy.expose
    def page(self, *path):
        import genshi.template

        for i in range(len(path), 0, -1):
            template='/'.join(['page']+list(path[0:i]))+'.genshi'
            return render(template, par=path[i:])

        raise cherrypy.HTTPError(404)


    def _cp_dispatch(self, vpath):
        res=self.root._cp_dispatch(vpath)

        if not res:
            try:
                res=self.apps[vpath[0]]
            except:
                pass

        return res


def main():
    import sys


    from optparse import OptionParser
    parser = OptionParser(usage="usage: %prog [options] server_dir")
    parser.add_option("--changepw", action="store_true", dest="changepw", help="Prompt for administrator password change and exit")
    parser.add_option("--foreground", action="store_true", dest="foreground", help="Run WeBIAS in foreground (without daemonization)")
    (options, args)=parser.parse_args()

    if len(args) != 1:
        parser.error("incorrect number of arguments")

    config.load_config(args[0])

    if options.changepw:
        auth.set_admin_pw()
        sys.exit(0)


    from cherrypy.process.plugins import Daemonizer, PIDFile, DropPrivileges
#    DropPrivileges(cherrypy.engine, umask=0022, uid=1044, gid=1000).subscribe()


    PIDFile(cherrypy.engine, config.get('Server', 'pid_file')).subscribe()
    cherrypy.engine.signal_handler.subscribe()
    auth.CleanupUsers(cherrypy.engine).subscribe()
    data.SAEnginePlugin(cherrypy.engine).subscribe()
    reports.ReportSender(cherrypy.engine).subscribe()
    statistics.DBLogPlugin(cherrypy.engine).subscribe()
    cherrypy.tools.db = data.SATool()

    conf={
        'tools.db.on': True,
        'tools.hit_recorder.on': True,
        'tools.error_recorder.on': True,
        'tools.sessions.on': True,
        'tools.clean_session.on': True,
        'log.screen': False,
        'tools.protect.on': True,
        'tools.protect.allowed': ['any']
    }

    try:
        conf['log.access_file'] = config.get('Server', 'access_log')
    except config.NoOptionError:
        cherrypy.engine.log('Filename of access log for WeBIAS server not set. Logging will be performed only to standard output.')

    try:
        conf['log.error_file'] = config.get('Server', 'error_log')
    except config.NoOptionError:
        cherrypy.engine.log('Filename of error log for WeBIAS server not set. Logging will be performed only to standard output.')


    mediaconf={
        # 'tools.staticdir.on': True,
        'tools.protect.on': False,
        'tools.staticredirect.on': True,
        'tools.staticredirect.section': '/media',
        'tools.staticredirect.redirect_section': '/media-base',
        'tools.staticredirect.dir': os.path.join(config.server_dir, 'media')
    }

    mediabaseconf={
        'tools.staticdir.on': True,
        'tools.staticdir.dir': os.path.join(pkg_resources.resource_filename('webias', 'data'), 'media')
    }

    webias = WeBIAS()

    cherrypy.tree.mount(webias, config.get('Server', 'root'), config={'/': conf, '/media': mediaconf, '/media-base': mediabaseconf})

    cherrypy.config.update({
        'session_filter.on':True,
        "session_filter.timeout":600000
    })

    cherrypy.engine.templateProcessor=template.TemplateProcessor()

    if config.getboolean('Server', 'proxy'):
        cherrypy.config.update({
            'tools.proxy.on': True,
            'tools.https_filter.on': True,
            'server.thread_pool': 100,
            "server.socket_port": config.getint('Server', 'server_port'),
            'server.socket_host': config.get('Server', 'server_host')
        })

    else:
        cherrypy.server.unsubscribe()

        try:
            server1 = cherrypy._cpserver.Server()
            server1.socket_port=config.getint('Server', 'server_ssl_port')
            server1._socket_host=config.get('Server', 'server_host')
            server1.thread_pool=100
            server1.ssl_module = 'builtin'
            server1.ssl_certificate = config.get('Server', 'ssl_cert')
            server1.ssl_private_key = config.get('Server', 'ssl_key')
            server1.ssl_certificate_chain = config.get('Server', 'ssl_cert_chain')
            server1.subscribe()
        except config.NoOptionError as e:
            webias.no_SSL = True
            cherrypy.engine.log('Option '+e.option+' not set and WeBIAS is not acting as a proxy. SSL will be disabled, and all connections will be unencrypted. DO NOT USE THIS CONFIGURATION IN THE PRODUCTION ENVIRONMENT.')

        server2 = cherrypy._cpserver.Server()
        server2.socket_port = config.getint('Server', 'server_port')
        server2._socket_host = config.get('Server', 'server_host')
        server2.thread_pool=100
        server2.subscribe()

    if not options.foreground:
        cherrypy.process.plugins.Daemonizer(cherrypy.engine).subscribe()

    cherrypy.engine.start()
    cherrypy.engine.block()


