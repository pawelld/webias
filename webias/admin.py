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

import auth

import statistics

from util import *


class Applications(object):

    _title="Applications"
    _caption="Control available applications"

    @property
    def _acl(self):
        session=cherrypy.request.db
        user_list = map(lambda x: x.login, data.ApplicationACL.get_allowed_users(session, ('ADMIN', 'VIEW')).all())

        return [user_list, 'admin']


    @cherrypy.expose
    @persistent
    def index(self):
        session=cherrypy.request.db

        login=auth.get_login()
        user=data.User.get_by_login(session,login)

        apps=data.Application.get_allowed_apps(session, user, ('VIEW', 'ADMIN'))

        root=cherrypy.tree.apps[config.root].root

        def loaded(app):
            return app.id in root.apps

        view_allowed={}
        admin_allowed={}

        for app in apps:
            admin_allowed[app.id] = auth.ForceLogin.match_acl(app.get_acl('ADMIN'), login)
            view_allowed[app.id] = auth.ForceLogin.match_acl(app.get_acl('VIEW'), login)

        return render('system/admin/apps.genshi', apps=apps, loaded_test=loaded, admin= (login == 'admin'), view_allowed=view_allowed, admin_allowed=admin_allowed)


    @cherrypy.expose
    @auth.with_acl(auth.app_acl('ADMIN'), noauth=True)
    def definition(self, app):
        session=cherrypy.request.db

        dbapp=data.Application.get_app(session, app)

        filename=config.server_dir + '/apps/' + dbapp.definition

        try:
            res=open(filename).read()
            cherrypy.response.headers['Content-type']='text/plain'
            return res
        except:
            raise cherrypy.HTTPError(500, "Configuration file for %s is missing."%app)

    @cherrypy.expose
    @auth.with_acl(auth.app_acl('VIEW'), noauth=True)
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
    @auth.with_acl(['admin'], noauth=True)
    def setaccess(self, app_id, value):
        session=cherrypy.request.db

        dbapp=data.Application.get_app(session, app_id)


        if value not in dbapp.access_levels:
            raise cherrypy.HTTPError(400, "Wrong value given: %s" % value)

        dbapp.access = value
        session.commit()

        go_back()



    @cherrypy.expose
    @auth.with_acl(auth.app_acl('ADMIN'), noauth=True)
    def disable(self,app):
        session=cherrypy.request.db

        dbapp=self.set_enabled(session,app,False)

        cherrypy.tree.apps[config.root].root.deregister(dbapp.id)

        go_back()

    @cherrypy.expose
    @auth.with_acl(auth.app_acl('ADMIN'), noauth=True)
    def enable(self,app):
        session=cherrypy.request.db


        root=cherrypy.tree.apps[config.root].root

        dbapp=None

        if app in root.apps:
            dbapp=self.set_enabled(session,app,True)
            cherrypy.tree.apps[config.root].root.register(dbapp.id)

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

    _title="Requests"
    _caption="View submitted requests"

    @property
    def _acl(self):
        session=cherrypy.request.db

        user_list = map(lambda x: x.login, data.ACL.get_allowed_users(session, ('VIEW',)).all())

        return [user_list, 'admin']

    @cherrypy.expose
    @persistent
    def index(self, p=1, **kwargs):
        session=cherrypy.request.db
        login=auth.get_login()
        user=data.User.get_by_login(session,login)
        q=data.Request.get_allowed_requests(session, user, ('VIEW', 'ADMIN'))

        apps=data.Application.get_allowed_apps(session, user, ('VIEW', 'ADMIN'))

        view_allowed={}
        admin_allowed={}

        for app in apps:
            admin_allowed[app.id] = auth.ForceLogin.match_acl(app.get_acl('ADMIN'), login)
            view_allowed[app.id] = auth.ForceLogin.match_acl(app.get_acl('VIEW'), login)

        return render_query_paged('system/admin/requests.genshi', q, int(p), 'requests', config.root+"/admin/requests/", kwargs, view_allowed=view_allowed, admin_allowed=admin_allowed)


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
    _cp_config={'tools.protect.allowed': ['admin']}

    _title="Users"
    _caption="Control access to site."

    _acl = ['admin']

    @cherrypy.expose
    @persistent
    def index(self, p=1, **kwargs):
        session=cherrypy.request.db

        q=session.query(data.User)

        return render_query_paged('system/admin/users.genshi', q, int(p), 'users', config.root + "/admin/users/", kwargs)

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
            email(usr.e_mail,'system/email/newuser.genshi',newlogin=usr.login, uuid=usr.uuid)
        elif usr.status=='FORGOTTEN':
            email(email,'system/email/forgotten.genshi',newlogin=usr.login, uuid=usr.uuid)

        go_back()

    @cherrypy.expose
    def role(self, id):
        session=cherrypy.request.db

        usr=data.User.get_user(session, id)

        if usr.id<=0:
            raise cherrypy.HTTPError(400, "Operation not allowed for user %d:%s." % (usr.id, usr.login))

        return render('system/admin/users_role.genshi', user=usr, roles=data.UserRole.roles)

    @cherrypy.expose
    def roleset(self, id, role=None, cancel=False):

        if not cancel and role is not None:
            session=cherrypy.request.db
            user=data.User.get_user(session, id)
            if user.id<=0:
                raise cherrypy.HTTPError(400, "Operation not allowed for user %d:%s." % (user.id, user.login))

            if user.role != None and user.role.name != role:
                session.delete(user.role)

            if user.role == None and role != 'NORMAL':
                new_role = data.UserRole(user = user, name = role)
                session.add(new_role)

            # session.commit()

        go_back()

    @cherrypy.expose
    @persistent
    def acl(self, id):
        session=cherrypy.request.db

        user=data.User.get_user(session, id)

        if user.id<=0 or user.role_name != 'POWER':
            raise cherrypy.HTTPError(400, "Operation not allowed for user %d:%s." % (user.id, user.login))

        apps=session.query(data.Application)
        schedulers=session.query(data.Scheduler)

        def fill_data(entities, privileges, acls, acl_attr):
            res = {}
            for ent in entities:
                res[ent.id] = {}
                for t in privileges:
                    res[ent.id][t] = False

            for acl in acls:
                id = getattr(acl, acl_attr).id
                res[id][acl.privilege] = acl.allowed

            return res

        app_data = fill_data(apps, data.ApplicationACL.privileges, user.role.app_acls, 'app')
        sched_data = fill_data(schedulers, data.SchedulerACL.privileges, user.role.sched_acls, 'sched')

        return render('system/admin/users_acls.genshi', user=user, apps=apps, app_data=app_data, app_privileges=data.ApplicationACL.privileges, schedulers=schedulers, sched_data=sched_data, sched_privileges=data.SchedulerACL.privileges)

    def aclset(self, usr_id, ent_id, priv, value, ent_cls, acl_cls, id_field):
        session=cherrypy.request.db

        user=data.User.get_user(session, usr_id)

        if user.id<=0 or user.role_name != 'POWER':
            raise cherrypy.HTTPError(400, "Operation not allowed for user %d:%s." % (usr.id, usr.login))

        ent=data.get_by_id(session, ent_cls, ent_id)

        acl = session.query(acl_cls).with_parent(user.role).with_parent(ent).filter(acl_cls.privilege == priv).first()

        if acl is None:
            acl = acl_cls(role=user.role, privilege=priv, allowed=False , **{id_field: ent.id})
            session.add(acl)

        acl.allowed = (int(value) != 0)
        session.commit()

        go_back()

    @cherrypy.expose
    def aclset_app(self, usr_id, ent_id, priv, value):
        self.aclset(usr_id, ent_id, priv, value, data.Application, data.ApplicationACL, 'app_id')

    @cherrypy.expose
    def aclset_sched(self, usr_id, ent_id, priv, value):
        self.aclset(usr_id, ent_id, priv, value, data.Scheduler, data.SchedulerACL, 'sched_id')

class SchedulerLog(statistics.ServerLog):
    _class = data.SchedulerLog

    @cherrypy.expose
    @auth.with_acl(auth.sched_acl('ADMIN'))
    @persistent
    def default(self, sched_id, show=False, id=0, p=1):
        self._location = config.root + '/admin/schedulers/log/' + sched_id + '/'

        if show:
            return statistics.ServerLog.show(self, id)
        else:
            return self.render(p, sched_id, title='Log for scheduler ' + sched_id)

    def show(self, id):
        # This method is to override show in statistics.ServerLog which does
        # not have a proper ACL decorator.
        pass

class Schedulers:
    _title="Schedulers"
    _caption="Control site access."

    def __init__(self):
        self.log = SchedulerLog()

    @property
    def _acl(self):
        session=cherrypy.request.db

        user_list = map(lambda x: x.login, data.SchedulerACL.get_allowed_users(session, ('ADMIN', 'VIEW')).all())

        return [user_list, 'admin']

    @cherrypy.expose
    @persistent
    def index(self):
        session=cherrypy.request.db

        login=auth.get_login()
        user=data.User.get_by_login(session,login)

        schedulers=data.Scheduler.get_allowed_scheds(session, user, ('VIEW', 'ADMIN'))

        view_allowed={}
        admin_allowed={}

        for sched in schedulers:
            admin_allowed[sched.id] = auth.ForceLogin.match_acl(sched.get_acl('ADMIN'), login)
            view_allowed[sched.id] = auth.ForceLogin.match_acl(sched.get_acl('VIEW'), login)

        return render('system/admin/schedulers.genshi', schedulers=schedulers, admin= (login == 'admin'), view_allowed=view_allowed, admin_allowed=admin_allowed)

    @cherrypy.expose
    @auth.with_acl(auth.sched_acl('VIEW'))
    @persistent
    def requests(self, id, status=None):
        qs='sched_id=%s'%id

        if status!=None:
            qs=qs+'&status=%s'%status

        raise cherrypy.InternalRedirect('/admin/requests/', qs)


    @cherrypy.expose
    @auth.with_acl(auth.sched_acl('ADMIN'))
    @persistent
    def locks(self, sched_id, p=1):
        session=cherrypy.request.db

        q=session.query(data.SchedulerLock).filter_by(sched_id=sched_id)

        return render_query_paged('system/admin/schedulers_log.genshi', q, int(p), 'locks', config.root + "/admin/schedulers/log/%s"%sched_id)


class Admin(FeatureList):
    _cp_config={
        'tools.secure.on': True,
        'tools.hit_recorder.on': False,
        'tools.protect.allowed': ['role:POWER', 'admin']
    }

    _title = 'Administration panel'

    def __init__(self):
        self.applications=Applications()
        self.requests=Requests()
        self.schedulers=Schedulers()
        self.users=Users()
