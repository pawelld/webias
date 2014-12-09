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

import time
import datetime

import data

import auth

import sys
import traceback

from util import *

def hit_recorder():
    if sys.exc_info()[0]==cherrypy._cperror.InternalRedirect:
        status='XXX Internal redirect'
        stat_num=0
    elif cherrypy.response.status==None:
        status='500 Internal Server Error'
        stat_num=500
    else:
        status=cherrypy.response.status
        stat_num=int(status.split(' ')[0])

    session=cherrypy.request.db
    login=auth.get_login()

    if login!=None:
        user=data.User.get_by_login(session, login)
        user_id=user.id
    else:
        user_id=None

    date=time.strftime("%Y-%m-%d %H:%M:%S")
    ip_address=cherrypy.request.remote.ip

    url = cherrypy.url(qs=cherrypy.request.query_string)

    req_sub=getattr(cherrypy.request, 'req_sub', False)

    hit=data.Hit(user_id, login, date, ip_address, url, status, cherrypy.session.id, req_sub)
    session.add(hit)
    session.commit()

    if stat_num>400:
        error_recorder(hit.id)


cherrypy.tools.hit_recorder = cherrypy.Tool('on_end_resource', hit_recorder, priority=50)


def error_recorder(hit_id=None):
    session=cherrypy.request.db
    engine=None

    if session==None:
        engine= sqlalchemy.create_engine(config.DB_URL, echo=False)
        engine.connect();
        Session=sqlalchemy.orm.sessionmaker(bind=engine)
        session=Session()

    login=auth.get_login()

    if cherrypy.response.status==None:
        status='500 Internal Server Error'
    else:
        status=cherrypy.response.status


    if login!=None:
        user=data.User.get_by_login(session, login)
        user_id=user.id
    else:
        user_id=None

    date=time.strftime("%Y-%m-%d %H:%M:%S")
    ip_address=cherrypy.request.remote.ip

    url = cherrypy.url(qs=cherrypy.request.query_string)

    headers=["%s: %s"%(k,v) for k,v in cherrypy.request.header_list]

    request='\n'.join([cherrypy.request.request_line] + headers)
    trace=''.join(traceback.format_exception(*sys.exc_info()))

    session_elts=["%s: %s"%(k,v) for k,v in cherrypy.session.items()]
    session_dump='\n'.join(["id: %s"%cherrypy.session.id] + session_elts)

    error=data.Error(user_id, login, hit_id, date, ip_address, url, status, cherrypy.session.id, trace, request, session_dump)
    session.add(error)

    if engine!=None:
        session.commit()
        session.close()


cherrypy.tools.error_recorder = cherrypy.Tool('after_error_response', error_recorder)

class DBLogPlugin(cherrypy.process.plugins.SimplePlugin):
    def __init__(self, bus):
        self.engine= sqlalchemy.create_engine(config.DB_URL, echo=False)
        self.engine.connect();
        self.Session=sqlalchemy.orm.sessionmaker(bind=self.engine)
        cherrypy.process.plugins.SimplePlugin.__init__(self, bus)

    def start(self):
        self.bus.log('Starting up DB logging')
        self.bus.subscribe("log", self.log)

    def stop(self):
        self.bus.log('Stopping down DB logging')
        self.bus.unsubscribe("log", self.log)

    def log(self, message, level):
        session = self.Session()
        log = data.Log(date=datetime.datetime.now(), message=message, level=level)
        session.add(log)
        session.commit()


class Hits:
    _title="Hits"
    _caption="Show HTTP hits in the last 30 days."

    @cherrypy.expose
    @persistent
    def index(self, p=1,**kwargs):

        date=str(datetime.date.today()-datetime.timedelta(30))

        session=cherrypy.request.db

        if kwargs=={}:
            q=session.query(data.Hit).filter(data.Hit.date>=date).order_by(data.Hit.id.desc())
        else:
            q=session.query(data.Hit).order_by(data.Hit.id.desc())

        return render_query_paged('statistics_hits.genshi', q, int(p), 'hits', config.APP_ROOT+"/statistics/hits/",kwargs)

class Sessions:
    _title="Sessions"
    _caption="Show distinct sessions in the last 90 days."


    @cherrypy.expose
    @persistent
    def index(self, p=1):
        session=cherrypy.request.db

        date=str(datetime.date.today()-datetime.timedelta(90))

        q = data.Hit.session_query(session).filter(data.Hit.date>=date).order_by(data.Hit.id.desc())

        return render_query_paged('statistics_sessions.genshi', q, int(p), 'sessions', config.APP_ROOT+"/statistics/sessions/")

    @cherrypy.expose
    @auth.with_acl(['any'])
    def stats(self):

        if auth.get_login()!='admin':
            return ''

        session=cherrypy.request.db
        sub = data.Hit.session_query(session).subquery()
        # sub=session.query(data.Hit.session, sqlalchemy.func.count(data.Hit.id).label('num_hits'), sqlalchemy.func.sum(sqlalchemy.sql.expression.cast(data.Hit.req_sub, sqlalchemy.types.Integer), type_=self.CoerceToInt).label('num_reqs')).group_by(data.Hit.session, data.Hit.ip_address).subquery()
        q=session.query(sqlalchemy.func.sum(sub.c.num_hits), sqlalchemy.func.count(sub.c.session), sqlalchemy.func.sum(sub.c.num_reqs))

        stats=q.one()

        return render('statistics_sessions_stats.genshi', num_hits=stats[0], num_sessions=stats[1], num_reqs=stats[2])



class Errors:
    _title="Errors"
    _caption="Show errors which occured in the last 90 days."

    @cherrypy.expose
    @persistent
    def index(self, p=1):
        session=cherrypy.request.db

        date=str(datetime.date.today()-datetime.timedelta(90))

        q=session.query(data.Error).filter(data.Error.date>=date).order_by(data.Error.hit_id.desc())

        return render_query_paged('statistics_errors.genshi', q, int(p), 'errors', config.APP_ROOT+"/statistics/errors/")

    @cherrypy.expose
    @persistent
    def show(self, error_id):
        session=cherrypy.request.db

        err=data.Error.get_error(session, error_id)

        return render('statistics_errors_show.genshi', error=err)

class ServerLog:
    _title="Server log"
    _caption="Show log entries for the last 90 days."

    @cherrypy.expose
    @persistent
    def index(self, p=1):
        session=cherrypy.request.db

        date=str(datetime.date.today()-datetime.timedelta(90))

        q=session.query(data.Log).filter(data.Log.date>=date).order_by(data.Log.id.desc())

        return render_query_paged('statistics_serverlog.genshi', q, int(p), 'events', config.APP_ROOT+"/statistics/log/")

    @cherrypy.expose
    @persistent
    def show(self, log_id):
        session=cherrypy.request.db

        log=session.query(data.Log).get(log_id)

        return render('statistics_serverlog_show.genshi', log=log)


class Statistics(FeatureList):
    _cp_config={
        'tools.secure.on': True,
        'tools.hit_recorder.on': False,
        'tools.protect.allowed': ['admin']
    }

    _title = 'Site statistics'

    _acl = ['admin']

    def __init__(self):
        self.hits=Hits()
        self.errors=Errors()
        self.sessions=Sessions()
        self.log = ServerLog()
