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

import auth
import query

import data
import sqlalchemy

from util import *


class Requests:

    title="Requests"
    caption="View submitted requests"

    @cherrypy.expose
    @persistent
    def index(self, p=1, all=None, **kwargs):
        session=cherrypy.request.db

        login=auth.get_login()
        user=data.User.get_by_login(session,login)

        q=session.query(data.Request).with_parent(user)

        fb = config.root+'/user/requests/'

        all= all!=None

        if not all:
            q=q.filter(data.Request.starred == True)
            if q.count()==0:
                raise cherrypy.HTTPRedirect(fb+'?all')
        else:
            fb=fb+'?all'


        return render_query_paged('system/user/requests.genshi', q, int(p), 'requests', fb, kwargs, all=all)

    def get_req(self, req_uuid):
        session=cherrypy.request.db

        req=data.Request.get_request(session, req_uuid)

        login=auth.get_login()
        user=data.User.get_by_login(session,login)

        return req

    def change_req(self, req_uuid, **kwargs):
        save_referer()

        req=self.get_req(req_uuid)
        for k in kwargs:
            setattr(req, k, kwargs[k])
        go_back()



    def req_acl(self, req_uuid, *args, **kwargs):
        req=self.get_req(req_uuid)

        return [[req.user.login],'admin']

    @cherrypy.expose
    @auth.with_acl(req_acl)
    def tag(self, req_uuid, tag):
        if tag=='':
            tag=None

        self.change_req(req_uuid, tag=tag)

    @cherrypy.expose
    @auth.with_acl(req_acl)
    def star(self, req_uuid):
        self.change_req(req_uuid, starred=True)

    @cherrypy.expose
    @auth.with_acl(req_acl)
    def unstar(self, req_uuid):
        self.change_req(req_uuid, starred=False)

    @cherrypy.expose
    @auth.with_acl(req_acl)
    def rerun(self, req_uuid):
        self.change_req(req_uuid, status='READY', sched_id=None)

    @cherrypy.expose
    @auth.with_acl(req_acl)
    def asnew(self, req_uuid):
        req=self.get_req(req_uuid)
        q=query.Query(req.query)
        q.req=req
        return cherrypy.tree.apps[config.root].root.apps[req.app.id].render_form(q)

class User(FeatureList):
    _cp_config={
        'tools.secure.on': True,
        'tools.protect.allowed': ['user']
    }

    _title = "User panel"

    def __init__(self):
        self.requests=Requests()
