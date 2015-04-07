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
import datetime
import time

from sqlalchemy import *
from sqlalchemy.orm import relationship, backref, scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from sqlalchemy.dialects.mysql import MEDIUMBLOB

import template

Base=declarative_base()

def _make_list_dict(l):
    return zip(*l)[0], dict(l)


class SAEnginePlugin(plugins.SimplePlugin):
    def __init__(self, bus):
        plugins.SimplePlugin.__init__(self, bus)
        self.sa_engine = None
        self.bus.subscribe("bind", self.bind)

    def start(self):
        self.sa_engine = create_engine(config.get('Database', 'db_url'), echo=False, pool_recycle=1800)

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
        cherrypy.request.hooks.attach('on_end_request', self.commit_transaction, priority=80)

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


def get_by_id(session, cls, id, msg=None):
    res=session.query(cls).get(id)
    if res != None:
        return res

    if msg is None:
        msg = "Invalid id for class %s: %s" % (str(cls), str(id))

    raise cherrypy.HTTPError(400, msg)

def get_allowed_entities(session, cls, user, modes):
    res = session.query(cls)

    if user.login != 'admin':
        res = res.join(cls.acls).filter(ACL.privilege.in_(modes), ACL.allowed).join(ACL.role).filter(UserRole.user == user)

    return res

class Application(Base):
    __tablename__ = 'applications'
    __table_args__ = {'mysql_engine':'InnoDB'}

    id = Column(String(50), primary_key=True, nullable=False)
    enabled = Column(Boolean, nullable=False)

    access = Column(String(32), nullable=False)

    definition = Column(String(128), nullable=False)

    param_template = Column(Text, nullable=False)
    output_files = Column(Text, nullable=False)

    requests = relationship("Request", backref="app")
    reportsettings = relationship("ReportSettingApp", backref="app")
    acls = relationship("ApplicationACL", backref="app", lazy="dynamic")

    access_levels, access_level_dict = _make_list_dict([('ANY', 'Everyone'), ('POWER', 'Powerusers'), ('ADMIN', 'Administrator')])

    def __init__(self, id, definition, param_template, output_files='', enabled=False, access='ANY'):
        self.id = id
        self.definition = definition
        self.param_template = param_template
        self.output_files = output_files
        self.enabled = enabled
        self.access = 'ANY'

    def __repr__(self):
        return "<Application('%s', '%s', '%s')>" % (self.id, self.definition, self.enabled)

    def get_acl(self, mode = 'QUERY'):
        if mode == 'QUERY':
            if self.access == 'ANY':
                return ['any']
            elif self.access == 'POWER':
                return ['role:POWER']

        acls = self.acls.filter(ApplicationACL.privilege == mode)
        res = [[acl.role.user.login for acl in acls if acl.allowed], 'admin']

        return res

    @staticmethod
    def get_app(session, app_id):
        return get_by_id(session, Application, app_id, "Bad application id.")

    @staticmethod
    def get_allowed_apps(session, user, modes):
        return get_allowed_entities(session, Application, user, modes)


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
    e_mail= Column(String(256, collation='ascii_bin'), unique=True, nullable=False)
    session= Column(String(128), nullable=True)

    # role = Column(String(32), nullable=True)
    role = relationship("UserRole", backref="user", uselist=False, cascade="all, delete-orphan")

    status = Column(String(32), nullable=True)
    uuid = Column(String(32), nullable=True)

    last_login = Column(DateTime , nullable=True)

    requests = relationship("Request", backref="user")
    reportsettings = relationship("ReportSetting", backref="user")
    # app_acls = relationship("ApplicationACL", backref="user")
    # sched_acls = relationship("SchedulerACL", backref="user")

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

    @property
    def role_name(self):
        return None if self.role is None else self.role.name

    def __init__(self, e_mail, login=None, password=None, status=None, uuid=None, date=None):
        self.date=date
        self.login = login
        self.password = self.hash_password(password)
        self.e_mail = e_mail
        self.status=status
        self.uuid=uuid

    def __repr__(self):
        return "<User('%d', '%s', '%s', '%s', '%s', %s, '%s')>" % (self.id, self.login, self.password, self.e_mail, self.session, self.status, self.uuid)

class UserRole(Base):
    __tablename__ = 'user_roles'
    __table_args__ = {'mysql_engine':'InnoDB'}

    roles = {'NORMAL': 'Normal', 'POWER': 'Poweruser'}

    id = Column(Integer, Sequence('user_role_id_seq'), primary_key=True)

    user_id = Column(Integer, ForeignKey('users.id', onupdate="cascade", ondelete="cascade"), nullable=False)
    name = Column(String(32), nullable=True)

    acls = relationship("ACL", backref="role", lazy="dynamic", cascade="all, delete-orphan")
    app_acls = relationship("ApplicationACL", lazy="dynamic", cascade="all, delete-orphan")
    sched_acls = relationship("SchedulerACL", lazy="dynamic", cascade="all, delete-orphan")


class File(Base):
    __tablename__ = 'files'
    __table_args__ = {'mysql_engine':'InnoDB'}

    id = Column(Integer, Sequence('file_id_seq'), primary_key=True)

    request_id = Column(Integer, ForeignKey('requests.id', onupdate="cascade", ondelete="cascade"), nullable=False)
    run_id = Column(Integer, ForeignKey('runs.id', onupdate="cascade", ondelete="cascade"), nullable=True)

    path = Column(String(512, collation='ascii_bin'), nullable=False)
    name = Column(String(256, collation='ascii_bin'), nullable=False)
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

    @staticmethod
    def get_allowed_requests(session, user, modes):
        apps = [app.id for app in Application.get_allowed_apps(session, user, modes)]
        return session.query(Request).filter(Request.app_id.in_(apps))
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
    reportsettings = relationship("ReportSettingSched", backref="sched")
    acls = relationship("SchedulerACL", backref="sched", lazy="dynamic")

    def get_acl(self, mode):
        acls = self.acls.filter(ACL.privilege == mode)
        res = [[acl.role.user.login for acl in acls if acl.allowed], 'admin']

        return res

    @staticmethod
    def get_allowed_scheds(session, user, modes):
        return get_allowed_entities(session, Scheduler, user, modes)

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

    @staticmethod
    def session_query(session):
        class CoerceToInt(sqlalchemy.types.TypeDecorator):
            impl = sqlalchemy.types.Integer

            def process_result_value(self, value, dialect):
                if value is not None:
                    value = int(value)
                return value

        return session.query(Hit, sqlalchemy.func.count(Hit.id).label('num_hits'), sqlalchemy.func.sum(sqlalchemy.sql.expression.cast(Hit.req_sub, sqlalchemy.types.Integer), type_=CoerceToInt).label('num_reqs')).group_by(Hit.session, Hit.ip_address, Hit.user_id)

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
        return "<Error(%d, %s, %s, %s, %s, %s, %s, '%s', %s)>" % (self.id, self.user_id, self.user_login, self.date, self.ip_address, self.domain, self.url, self.status, self.session)

    @staticmethod
    def get_error(session, id):
        return get_by_id(session, Error, id, "Bad error id.")


class Log(Base):
    __tablename__ = 'server_log'
    __table_args__ = {'mysql_engine':'InnoDB'}

    id = Column(Integer, Sequence('error_id_seq'), primary_key=True)
    date = Column(DateTime, nullable=False)

    level = Column(Integer, nullable=False)
    message = Column(Text(), nullable=False)

    def __repr__(self):
        return "<Log(%d, %s, %d, %s)>" % (self.id, self.date, self.level, repr(self.message))

class SchedulerLog(Base):
    __tablename__ = 'scheduler_log'

    __table_args__ = {'mysql_engine':'InnoDB'}

    id = Column(Integer, Sequence('error_id_seq'), primary_key=True)
    date = Column(DateTime, nullable=False)

    sched_id = Column(String(50), ForeignKey('schedulers.id', onupdate="cascade", ondelete="cascade"), nullable=True)
    level = Column(Integer, nullable=False)
    message = Column(Text(), nullable=False)

    def __repr__(self):
        return "<SchedulerLog(%d, %s, %s, %d, %s)>" % (self.id, self.sched_id, self.date, self.level, repr(self.message))

class ACL(Base):
    __tablename__ = 'acls'
    __table_args__ = {'mysql_engine':'InnoDB'}

    id = Column(Integer, Sequence('applicationacl_id_seq'), primary_key=True)
    userrole_id = Column(Integer, ForeignKey('user_roles.id', onupdate="cascade", ondelete="cascade"), nullable=False)

    acl_class = Column(String(50), nullable=False)

    privilege = Column(String(32), nullable=False)
    allowed = Column(Boolean, nullable=False)

    report_settings = relationship("ReportSetting", backref="acl", lazy="dynamic", cascade="all, delete-orphan")

    __mapper_args__ = {
        'polymorphic_on': acl_class,
    }

    def __init__(self, *args, **kwargs):
        self.acl_class = self.__class__.__name__
        Base.__init__(self, *args, **kwargs)

    def __repr__(self):
        return "<ACL(%d, %d, %s, %s, %s)>" % (self.id, self.userrole_id, self.acl_class, self.privilege, str(self.allowed))

    @classmethod
    def get_allowed_users(cls, session, privileges=None):

        res = session.query(User).join(User.role).join(cls).filter(UserRole.id == cls.userrole_id, cls.allowed, cls.privilege.in_(privileges))

        if cls != ACL:
            res = res.filter(cls.acl_class == cls.__name__)

        if privileges is not None:
            res = res.filter(cls.privilege.in_(privileges))

        return res.distinct()

class ApplicationACL(ACL):
    __mapper_args__ = {'polymorphic_identity':'ApplicationACL'}

    privileges = {'QUERY': 'Submit queries', 'ADMIN': 'Administration', 'VIEW': 'View requests', 'REPORTS': 'Receive reports'}
    app_id = Column(String(50), ForeignKey('applications.id', onupdate="cascade", ondelete="cascade"), nullable=True)



class SchedulerACL(ACL):
    __mapper_args__ = {'polymorphic_identity':'SchedulerACL'}

    privileges = {'ADMIN': 'Administration', 'VIEW': 'View requests', 'REPORTS': 'Receive reports'}
    sched_id = Column(String(50), ForeignKey('schedulers.id', onupdate="cascade", ondelete="cascade"), nullable=True)


class ReportSetting(Base):
    __tablename__ = 'reportsettings'
    __table_args__ = {'mysql_engine':'InnoDB'}

    id = Column(Integer, Sequence('reportsetting_id_seq'), primary_key=True)

    user_id = Column(Integer, ForeignKey('users.id', onupdate="cascade", ondelete="cascade"), nullable=False)
    report_class = Column(String(50), nullable=False)


    report_type = Column(String(50), nullable=False)
    frequency = Column(String(5), nullable=False)

    last = Column(DateTime, nullable=True)
    last_nonempty = Column(DateTime, nullable=True)

    acl_id = Column(Integer, ForeignKey('acls.id', onupdate="cascade", ondelete="cascade"))

    __mapper_args__ = {
        'polymorphic_on': report_class,
    }



    def is_due(self, date, last=None):
        if self.frequency == 'N':
            return False

        if last is None:
            last = self.last

        if last is None:
            return True

        delay_dict = {'M': 60, 'H': 3600, 'D': 24*3600, 'W': 7*24*3600}

        delay = delay_dict[self.frequency]

        delta_since_epoch = (last - datetime.datetime(1970, 1, 1))
        last_ts = delta_since_epoch.days * 24 * 3600 + delta_since_epoch.seconds
        delta_since_epoch = (datetime.datetime.fromtimestamp(date) - datetime.datetime(1970, 1, 1))
        date_ts = delta_since_epoch.days * 24 * 3600 + delta_since_epoch.seconds

        return int(last_ts)/delay < int(date_ts)/delay


    def generate(self, session, date):
        res = self.run_query(session)

        self.last = datetime.datetime.fromtimestamp(date)

        if res != []:
            self.last_nonempty = datetime.datetime.utcfromtimestamp(date)

        return res

    def render(self, items, template_processor):
        try:
            template_file = self.templates[self.report_type]
        except:
            return 'Missing template for: %s' % self
        else:
            args = template.TemplateArgs()
            args.reportsetting = self
            args.items = items
            return template_processor.processTemplate(template_file, args, 'text')

class ReportSettingApp(ReportSetting):
    app_id = Column(String(50), ForeignKey('applications.id', onupdate="cascade", ondelete="cascade"), nullable=True)

    __mapper_args__ = {
        'polymorphic_identity':'ReportSettingApp'
    }

    templates = {'ALL': 'system/reports/app_all.genshi', 'FAILED': 'system/reports/app_failed.genshi', 'FINISHED': 'system/reports/app_finished.genshi', 'WAITING': 'system/reports/app_waiting.genshi'}

    types = {'ALL': 'Submitted', 'WAITING': 'Waiting', 'FAILED': 'Failed', 'FINISHED': 'Successful'}

    def run_query(self, session):
        q = session.query(Request).with_parent(self.app)

        if self.last is not None:
            q = q.filter(Request.date >= self.last)

        if self.report_type != 'ALL':
            q = q.filter(Request.status == self.report_type)

        return q.all()

    def __repr__(self):
        return "<ReportSettingApp(%d, %d, %s, %s, %s, %s)" % (self.id, self.user_id, self.app_id, self.report_type, self.frequency, str(self.last))

class ReportSettingSched(ReportSetting):
    sched_id = Column(String(50), ForeignKey('schedulers.id', onupdate="cascade", ondelete="cascade"), nullable=True)

    __mapper_args__ = {
        'polymorphic_identity':'ReportSettingSched'
    }

    templates = {'FAILED': 'system/reports/sched_failed.genshi', 'FINISHED': 'system/reports/sched_finished.genshi', 'PROCESSING': 'system/reports/sched_processing.genshi', 'STARTSTOP': 'system/reports/sched_startstop.genshi', 'DEAD': 'system/reports/sched_dead.genshi'}

    types = {'STARTSTOP': 'Start/stop', 'DEAD': 'No response', 'PROCESSING':'Processing', 'FINISHED': 'Success', 'FAILED': 'Failure'}


    def run_query(self, session):
        if self.report_type == 'STARTSTOP':
            q = session.query(SchedulerLock).with_parent(self.sched)
            if self.last is not None:
                q = q.filter((SchedulerLock.lock_start >= self.last) | (SchedulerLock.lock_end >= self.last))

            return q.all()

        if self.report_type == 'DEAD':
            if self.sched.status == 'RUNNING':
                silent = datetime.datetime.now() - self.sched.last_act
                silent_secs = silent.days * 24 * 3600 + silent.seconds

                if silent_secs > 600:
                    return [self.sched]

            return []


        q = session.query(Request).with_parent(self.sched)
        if self.last is not None:
            q = q.filter(Request.date >= self.last)

        q = q.filter(Request.status == self.report_type)

        return q.all()

    def __repr__(self):
        return "<ReportSettingSched(%d, %d, %s, %s, %s, %s)" % (self.id, self.user_id, self.sched_id, self.report_type, self.frequency, str(self.last))

class ReportSettingServ(ReportSetting):
    __mapper_args__ = {
        'polymorphic_identity':'ReportSettingServ'
    }

    templates = {'HEARTBEAT': 'system/reports/serv_heartbeat.genshi', 'NEWUSER': 'system/reports/serv_newuser.genshi', 'ERRORS': 'system/reports/serv_errors.genshi', 'SESSIONS': 'system/reports/serv_sessions.genshi', 'USERLOGIN': 'system/reports/serv_userlogin.genshi', 'LOG': 'system/reports/serv_serverlog.genshi'}

    types = {'LOG': 'Server log', 'SESSIONS': 'New sessions', 'HEARTBEAT':'Heartbeat', 'ERRORS': 'Web errors', 'NEWUSER': 'User registration', 'USERLOGIN': 'User login'}

    def run_query(self, session):
        report_cls = {'ERRORS': Error, 'SESSIONS': Hit, 'NEWUSER': User, 'USERLOGIN': Hit, 'LOG': Log}

        if self.report_type in report_cls:
            rep_cls = report_cls[self.report_type]
            if self.report_type == 'SESSIONS':
                q = Hit.session_query(session).order_by(Hit.date)
            elif self.report_type == 'USERLOGIN':
                q = Hit.session_query(session).order_by(Hit.date).filter(Hit.user_id != None)
            else:
                q = session.query(rep_cls)

            if self.last is not None:
                q = q.filter(rep_cls.date >= self.last)

            return q.all()

        if self.report_type == 'HEARTBEAT':
            q = session.query(sqlalchemy.func.max(ReportSetting.last_nonempty)).with_parent(self.user)

            if self.is_due(time.time(), q.one()[0]):
                return ['OK']

            return []

        raise NotImplementedError()

    def __repr__(self):
        return "<ReportSettingServ(%d, %d, %s, %s, %s)" % (self.id, self.user_id, self.report_type, self.frequency, str(self.last))

