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
import config

import data 
import sqlalchemy

from util import *



class Applications:

    title="Applications"
    caption="Control available applications"

    @cherrypy.expose
    @persistent
    def index(self):
        session=cherrypy.request.db

        apps=session.query(data.Application)

        root=cherrypy.tree.apps[config.APP_ROOT].root

        def loaded(app):
            return app.id in root.apps



        return render('admin_apps.genshi', apps=apps, loaded_test=loaded)


    @cherrypy.expose
    def definition(self, app):
        session=cherrypy.request.db

        dbapp=data.Application.get_app(session, app)

        filename=config.BIAS_DIR+'/apps/'+dbapp.definition

        try:
            res=open(filename).read()
            cherrypy.response.headers['Content-type']='text/plain'
            return res
        except:
            raise cherrypy.HTTPError(500, "Configuration file for %s is missing."%app)

    @cherrypy.expose
    @persistent
    def requests(self, app, status=None):
        qs='app_id=%s'%app

        if status!=None:
            qs=qs+'&status=%s'%status

        raise cherrypy.InternalRedirect('/admin/requests/', qs)


    def set_enabled(self, session, app_id, val):
        dbapp=data.Application.get_app(session, app_id)
        dbapp.enabled=val
        session.commit()
        return dbapp

    @cherrypy.expose
    def disable(self,app):
        session=cherrypy.request.db

        dbapp=self.set_enabled(session,app,False)

        cherrypy.tree.apps[config.APP_ROOT].root.deregister(dbapp.id)

        go_back()

    @cherrypy.expose
    def enable(self,app):
        session=cherrypy.request.db


        root=cherrypy.tree.apps[config.APP_ROOT].root
        
        dbapp=None

        if app in root.apps:
            dbapp=self.set_enabled(session,app,True)
            cherrypy.tree.apps[config.APP_ROOT].root.register(dbapp.id)

        if dbapp==None or not dbapp.enabled:
            raise cherrypy.HTTPError(500, "Failed to enable %s."%app)

        go_back()
            
#    @cherrypy.expose
#    def delete(self, app):
#        session=cherrypy.request.db
#
#        dbapp=data.Application.get_app(session, app)
#
#        session.delete(dbapp)
#
#        go_back()

class Requests:

    title="Requests"
    caption="View submitted requests"

    @cherrypy.expose
    @persistent
    def index(self, p=1, **kwargs):
        session=cherrypy.request.db
        q=session.query(data.Request)

        return render_query_paged('admin_requests.genshi', q, int(p), 'requests', config.APP_ROOT+"/admin/requests/", kwargs)


    @cherrypy.expose
    def delete(self, req_uuid):
        session=cherrypy.request.db

        req=data.Request.get_request(session, req_uuid)
        session.delete(req)

        go_back()

    @cherrypy.expose
    def rerun(self, req_uuid):
        session=cherrypy.request.db

        req=data.Request.get_request(session, req_uuid)
        req.status='READY'
        req.sched_id=None

        go_back()

class Users:

    title="Users"
    caption="Control access to site."

    @cherrypy.expose
    @persistent
    def index(self, p=1, **kwargs):
        session=cherrypy.request.db

        q=session.query(data.User)

        return render_query_paged('admin_users.genshi', q, int(p), 'users', config.APP_ROOT+"/admin/users/", kwargs)

    @cherrypy.expose
    @persistent
    def requests(self, id, status=None):
        qs='user_id=%s'%id

        if status!=None:
            qs=qs+'&status=%s'%status

        raise cherrypy.InternalRedirect('/admin/requests/', qs)


    @cherrypy.expose
    def block(self, id):
        session=cherrypy.request.db

        usr=data.User.get_user(session, id)
        usr.status='BLOCKED'

        go_back()


    @cherrypy.expose
    def unblock(self, id):
        session=cherrypy.request.db

        usr=data.User.get_user(session, id)
        usr.status='OK'

        go_back()


    @cherrypy.expose
    def delete(self, id):
        session=cherrypy.request.db

        usr=data.User.get_user(session, id)
        session.delete(usr)

        go_back()


    @cherrypy.expose
    def resend(self, id):
        session=cherrypy.request.db

        usr=data.User.get_user(session, id)

        if usr.status=='NEW':
            email(usr.e_mail,'email_newuser.genshi',newlogin=usr.login, uuid=usr.uuid)
        elif usr.status=='FORGOTTEN':
            email(email,'email_forgotten.genshi',newlogin=usr.login, uuid=usr.uuid)

        go_back()

class Schedulers:

    title="Schedulers"
    caption="Control site access."

    @cherrypy.expose
    @persistent
    def index(self):
        session=cherrypy.request.db

        return render('admin_schedulers.genshi', schedulers=session.query(data.Scheduler))
        

    @cherrypy.expose
    @persistent
    def requests(self, id, status=None):
        qs='sched_id=%s'%id

        if status!=None:
            qs=qs+'&status=%s'%status

        raise cherrypy.InternalRedirect('/admin/requests/', qs)


    @cherrypy.expose
    @persistent
    def log(self, sched_id, p=1):
        session=cherrypy.request.db

        q=session.query(data.SchedulerLock).filter_by(sched_id=sched_id)

        return render_query_paged('admin_schedulers_log.genshi', q, int(p), 'locks', config.APP_ROOT+"/admin/schedulers/log/%s"%sched_id)


class Admin:
    _cp_config={
        'tools.secure.on': True,
        'tools.hit_recorder.on': False,
        'tools.protect.allowed': ['admin']
    }

    def __init__(self):
        self.applications=Applications()
        self.requests=Requests()
        self.users=Users()
        self.schedulers=Schedulers()

    @cherrypy.expose
    @persistent
    def index(self):
        features = dict([(self.__dict__[el].title, {'caption':self.__dict__[el].caption, 'link':el}) for el in self.__dict__ if hasattr(self.__dict__[el], 'title')])

        return render('admin.genshi', features=features)

