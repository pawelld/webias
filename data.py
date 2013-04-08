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


import sqlalchemy.ext.declarative 

import hashlib

from util import *

import cherrypy
from cherrypy.process import wspbus, plugins

import os

from sqlalchemy import *
from sqlalchemy.orm import relationship, backref, scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from sqlalchemy.dialects.mysql import MEDIUMBLOB


Base=declarative_base()

 
class SAEnginePlugin(plugins.SimplePlugin):
    def __init__(self, bus):
        plugins.SimplePlugin.__init__(self, bus)
        self.sa_engine = None
        self.bus.subscribe("bind", self.bind)

    def start(self):
        self.sa_engine = create_engine(config.DB_URL, echo=False, pool_recycle=1800)

    def stop(self):
        if self.sa_engine:
            self.sa_engine.dispose()
            self.sa_engine = None

    def bind(self, session):
        session.configure(bind=self.sa_engine)
            
class SATool(cherrypy.Tool):
    def __init__(self):
        cherrypy.Tool.__init__(self, 'on_start_resource', self.bind_session, priority=20)
        self.session = scoped_session(sessionmaker(autoflush=True, autocommit=False))
            
    def _setup(self):
        cherrypy.Tool._setup(self)
        cherrypy.request.hooks.attach('on_end_resource', self.commit_transaction, priority=80)
        
    def bind_session(self):
        cherrypy.engine.publish('bind', self.session)
        cherrypy.request.db = self.session
        
    def commit_transaction(self):
        cherrypy.request.db = None
        try:
            self.session.commit()
        except:
            self.session.rollback()  
            raise
        finally:
            self.session.remove()


def get_by_id(session, cls, id, msg):
    res=session.query(cls).get(id)
    if res != None:
        return res
    raise cherrypy.HTTPError(400, msg)

class Application(Base):
    __tablename__ = 'applications'
    __table_args__ = {'mysql_engine':'InnoDB'}

    id = Column(String(50), primary_key=True, nullable=False)
    enabled = Column(Boolean, nullable=False)
    definition = Column(String(128), nullable=False)

    param_template = Column(Text, nullable=False)
    output_files = Column(Text, nullable=False)

    requests = relationship("Request", backref="app")

    def __init__(self, id, definition, param_template, output_files='', enabled=False):
        self.id = id
        self.definition = definition
        self.param_template = param_template
        self.output_files = output_files
        self.enabled = enabled
    
    def __repr__(self):
        return "<Application('%s', '%s', '%s')>" % (self.id, self.definition, self.enabled)
    
    @staticmethod
    def get_app(session, app_id):
        return get_by_id(session, Application, app_id, "Bad application id.")

    def get_stats(self):
        res={}

        session=sqlalchemy.orm.session.object_session(self)
        
        query=session.query(Request).with_parent(self)

        res['']=query.count()
        res['READY']=query.filter_by(status = 'READY').count()
        res['PROCESSING']=query.filter_by(status = 'PROCESSING').count()
        res['FAILED']=query.filter_by(status = 'FAILED').count()
        res['FINISHED']=query.filter_by(status = 'FINISHED').count()

        return res


class User(Base):
    __tablename__ = 'users'
    __table_args__ = {'mysql_engine':'InnoDB'}

    id = Column(Integer, Sequence('user_id_seq'), primary_key=True)

    date = Column(DateTime , nullable=True)

    login = Column(String(50), unique=True, nullable=True)
    password= Column(String(50), nullable=True)
    e_mail= Column(String(256), unique=True, nullable=False)
    session= Column(String(128), nullable=True)

    status = Column(String(32), nullable=True)
    uuid = Column(String(32), nullable=True)

    last_login = Column(DateTime , nullable=True)

    requests = relationship("Request", backref="user")

    @staticmethod
    def get_by_email(session, e_mail=None, insert=False):
        if e_mail!=None and e_mail!='':
            res=session.query(User).filter(User.e_mail==e_mail).first()

            if insert and res==None:
                user=User(e_mail)
                session.add(user)
                session.commit()
                res=user
        else:
            res=session.query(User).get(-1)

            if insert and res==None:
                user=User('')
                user.id=-1
                session.add(user)
                session.commit()
                res=user

        return res

    @staticmethod
    def get_by_login(session, login):
        res=session.query(User).filter(User.login==login).first()
        return res

    @staticmethod
    def get_user(session, id):
        return get_by_id(session, User, id, "Bad user id.")

    @staticmethod
    def hash_password(passwd):
        if passwd != None:
            return hashlib.md5(passwd).hexdigest()
        else:
            return None

    def authenticate(self, passwd):
        if not self.status in ['OK', 'FORGOTTEN']:
            return False

        if self.password != self.hash_password(passwd):
            return False

        self.status='OK'

        return True

    def update_passwd(self, passwd):
        self.password = self.hash_password(passwd)


    def __init__(self, e_mail, login=None, password=None, status=None, uuid=None, date=None):
        self.date=date
        self.login = login
        self.password = self.hash_password(password)
        self.e_mail = e_mail
        self.status=status
        self.uuid=uuid

    def __repr__(self):
        return "<User('%d', '%s', '%s', '%s', '%s', %s, '%s')>" % (self.id, self.login, self.password, self.e_mail, self.session, self.status, self.uuid)



class File(Base):
    __tablename__ = 'files'
    __table_args__ = {'mysql_engine':'InnoDB'}

    id = Column(Integer, Sequence('file_id_seq'), primary_key=True)

    request_id = Column(Integer, ForeignKey('requests.id', onupdate="cascade", ondelete="cascade"), nullable=False)
    run_id = Column(Integer, ForeignKey('runs.id', onupdate="cascade", ondelete="cascade"), nullable=True)

    path = Column(String(512), nullable=False)
    name = Column(String(256), nullable=False)
    data = Column(sqlalchemy.dialects.mysql.MEDIUMBLOB, nullable=False)
    type = Column(String(8), nullable=False)

    __table_args__ = (UniqueConstraint('request_id','run_id','path','name'), )

    def write(self, dir):
        dir+='/'+self.path
        if not os.access(dir, os.F_OK):
            os.makedirs(dir)
        fh=open(dir+'/'+self.name,'w')
        fh.write(self.data)
        fh.close()

    def __init__(self, request, path, name, data, type, run=None):
        self.request = request
        self.run = run
        self.path = path
        self.name = name
        self.data = data
        self.type = type

    def __repr__(self):
        return "<File('%d', '%s', '%s', '%s', '%s', '%s')>" % (self.id, self.request, self.run, self.path, self.name, self.type)

    @staticmethod
    def split_name(pathname):
        name=pathname.split('/')[-1]
        path=pathname[0:-len(name)]

        return (path,name)


class Run(Base):
    __tablename__ = 'runs'
    __table_args__ = {'mysql_engine':'InnoDB'}

    id = Column(Integer, Sequence('run_id_seq'), primary_key=True)

    request_id = Column(Integer, ForeignKey('requests.id', onupdate="cascade", ondelete="cascade"), nullable=False)

    date = Column(DateTime , nullable=False)
    status = Column(String(30), nullable=False, default='')
    pid = Column(Integer, nullable=True)
    result = Column(Text, nullable=True)
    files = relationship("File", backref="run", primaryjoin="Run.id == File.run_id", cascade="all")

    def get_job_dir(self,work_dir):
        return work_dir+"/%s/jobs/%s/%d"%(self.request.app.id,self.request.uuid,self.id)

    def __init__(self, request, date, pid=None, status='CREATING', result=None):
        self.request = request
        self.date = date
        self.status = status 
        self.pid = pid
        self.result = result

    def __repr__(self):
        return "<Run('%d', '%s', '%s', '%s', %d, '%s')>" %(self.id,self.request, self.date, self.status, self.pid, self.result)

    def get_file(self, path, name):
        session=sqlalchemy.orm.session.object_session(self)
        
        query=session.query(File).with_parent(self).filter_by(name=name,path=path.rstrip('/'))

        return query.first()

class Request(Base):
    __tablename__ = 'requests'
    __table_args__ = {'mysql_engine':'InnoDB'}

    id = Column(Integer, Sequence('request_id_seq'), primary_key=True)

    date = Column(DateTime , nullable=False)
    status = Column(String(30), nullable=False, default='')
    uuid = Column(String(32), nullable=False)
    ip_address = Column(String(16), nullable=False)
    query = Column(Text, nullable=False)

    starred = Column(Boolean, nullable=False)
    tag = Column(String(256), nullable=True)

    user_id = Column(Integer, ForeignKey('users.id', onupdate="cascade", ondelete="cascade"), nullable=False)
    app_id = Column(String(50), ForeignKey('applications.id', onupdate="cascade", ondelete="restrict"), nullable=False)
    sched_id = Column(String(50), ForeignKey('schedulers.id', onupdate="cascade", ondelete="restrict"), nullable=True)

    
    session = Column(String(40), nullable=True)

    files = relationship("File", backref="request", primaryjoin="Request.id ==File.request_id", cascade="all")
    runs = relationship("Run", backref="request", cascade="all")

    def __init__(self, date, status, uuid, ip_address, app_id, user, query, session=None):
        self.date = date
        self.status = status 
        self.uuid = uuid
        self.ip_address = ip_address
        self.app_id = app_id
        self.user = user
        self.query = query
        self.starred = False
        self.session = session

    def __repr__(self):
        return "<Request('%d', '%s', '%s', '%s', '%s', %s, %s, '%s')>" % (self.id, self.date, self.status, self.uuid, self.ip_address, self.app, self.user, self.query)

    def get_run(self, runid=None):
        session=sqlalchemy.orm.session.object_session(self)
        query=session.query(Run)

        if(runid == None):
            return query.with_parent(self).order_by(Run.id.desc()).first()
        else:
            run=query.get(runid)
            if(run!=None and run.request!=self):
                run=None

            return run

    def get_file(self, path, name):
        session=sqlalchemy.orm.session.object_session(self)
        query=session.query(File).with_parent(self).filter_by(name=name,path=path.rstrip('/'))
        return query.first()

    @staticmethod
    def get_request(session, uuid):
        try:
            check_uuid(uuid)
            return session.query(Request).filter_by(uuid = uuid).one()
        except (ValueError,sqlalchemy.orm.exc.NoResultFound):
            raise cherrypy.HTTPError(400, "Please provide a valid UUID.")

class Scheduler(Base):
    __tablename__ = 'schedulers'
    __table_args__ = {'mysql_engine':'InnoDB'}

    id = Column(String(50), primary_key=True)
    status = Column(String(20), nullable=False)
    last_act = Column(DateTime , nullable=True)

    apps = relationship("Application", secondary=Table('sched_apps', Base.metadata,
        Column('app_id', String(50), ForeignKey('applications.id')),
        Column('sched_id', String(50), ForeignKey('schedulers.id'))))

    locks = relationship("SchedulerLock", backref="sched")
    requests = relationship("Request", backref="sched")

    def __init__(self, sched_id, status='STOPPED', apps=[]):
        self.id = sched_id
        self.status = status
        self.apps = apps

    def __repr__(self):
        return "<Scheduler('%s', '%s', '%s', %s)>" % (self.id, self.status, self.last_act, self.apps)

    def get_apps(self):
        return ', '.join([app.id for app in self.apps])

    def get_stats(self):
        res={}

        session=sqlalchemy.orm.session.object_session(self)
        
        query=session.query(Request).with_parent(self)

        res['']=query.count()
        res['PROCESSING']=query.filter_by(status = 'PROCESSING').count()
        res['FAILED']=query.filter_by(status = 'FAILED').count()
        res['FINISHED']=query.filter_by(status = 'FINISHED').count()

        return res


class SchedulerLock(Base):
    __tablename__ = 'scheduler_locks'
    __table_args__ = {'mysql_engine':'InnoDB'}

    id = Column(Integer, Sequence('scheduler_lock_id_seq'), primary_key=True)

    sched_id = Column(String(50), ForeignKey('schedulers.id', onupdate="restrict", ondelete="restrict"), nullable=False)
    lock_start = Column(DateTime , nullable=False)
    lock_end = Column(DateTime , nullable=True)
    pid = Column(Integer, nullable=False)
    host = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)

    def __init__(self, sched, pid, host, status, lock_start, lock_end=None):
        self.sched = sched
        self.lock_start = lock_start
        self.lock_end = lock_end
        self.pid = pid
        self.host = host
        self.status = status

    def __repr__(self):
        return "<SchedulerLock('%d', '%s', '%s', '%s', '%s', %s, %s)>" % (self.id, self.sched_id, self.lock_start, self.lock_end, self.pid, self.host, self.status)

class Hit(Base):
    __tablename__ = 'hits'
    __table_args__ = {'mysql_engine':'InnoDB'}

    id = Column(Integer, Sequence('hit_id_seq'), primary_key=True)

    user_id = Column(Integer, ForeignKey('users.id', onupdate="cascade", ondelete="set null"), nullable=True)
    user_login = Column(String(50), nullable=True)

    date = Column(DateTime , nullable=False)

    ip_address = Column(String(16), nullable=False)
    domain = Column(String(256), nullable=True)
    url = Column(String(512), nullable=False)

    status = Column(String(128), nullable=False)
    session = Column(String(40), nullable=False)

    req_sub =  Column(Boolean, nullable=False)

    error = relationship("Error", uselist=False, backref="hit")


    def resolve(self):
        if self.domain!=None:
            return

        self.domain=gethostbyaddr(self.ip_address)

    def __init__(self, user_id, user_login, date, ip_address, url, status, session, req_sub=False):
        self.user_id = user_id
        self.user_login = user_login
        self.date = date
        self.ip_address = ip_address
        self.url = url
        self.status = status
        self.session = session
        self.req_sub = req_sub

    def __repr__(self):
        return "<Hit(%s, %s, %s, %s, %s, %s, %s, '%s', %s)>" % (self.id, self.user_id, self.user_login, self.date, self.ip_address, self.domain, self.url, self.status, self.session)

class Error(Base):
    __tablename__ = 'errors'
    __table_args__ = {'mysql_engine':'InnoDB'}

    id = Column(Integer, Sequence('error_id_seq'), primary_key=True)

    user_id = Column(Integer, ForeignKey('users.id', onupdate="cascade", ondelete="set null"), nullable=True)
    user_login = Column(String(50), nullable=True)

    hit_id = Column(Integer, ForeignKey('hits.id', onupdate="set null", ondelete="set null"), nullable=True)

    date = Column(DateTime , nullable=False)

    ip_address = Column(String(16), nullable=False)
    domain = Column(String(256), nullable=True)
    url = Column(String(512), nullable=False)

    status = Column(String(128), nullable=False)
    session = Column(String(40), nullable=False)

    traceback = Column(Text(), nullable=False)
    request = Column(Text(), nullable=False)
    session_dump = Column(Text(), nullable=False)


    def resolve(self):
        if self.domain!=None:
            return

        self.domain=gethostbyaddr(self.ip_address)

    def __init__(self, user_id, user_login, hit_id, date, ip_address, url, status, session, traceback, request, session_dump):
        self.user_id = user_id
        self.user_login = user_login
        self.date = date
        self.hit_id = hit_id
        self.ip_address = ip_address
        self.url = url
        self.status = status
        self.session = session
        self.traceback = traceback
        self.request = request
        self.session_dump = session_dump

    def __repr__(self):
        return "<Error(%d, %d, %s, %s, %s, %s, %s, '%s', %s)>" % (self.id, self.user_id, self.user_login, self.date, self.ip_address, self.domain, self.url, self.status, self.session)

    @staticmethod
    def get_error(session, id):
        return get_by_id(session, Error, id, "Bad error id.")
