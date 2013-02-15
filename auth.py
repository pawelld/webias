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
import urlparse
import config
import time

import util 
import data 

import uuid
import sqlalchemy


import string
import random

def is_sequence(arg):
    return (not hasattr(arg, "strip") and
        hasattr(arg, "__getitem__") or
        hasattr(arg, "__iter__"))

def https_filter():
    request = cherrypy.request

    # Check for a special header 'X-Forwarded-Ssl'.
    # If we have it, then we substitute the secure base URL.
    headers = request.headers
    forwarded_ssl = headers.get('X-Forwarded-Ssl', 'off')
    if forwarded_ssl == 'on':
        base = headers.get('X-Forwarded-Host', 'localhost')
        request.base = 'https://' + base

cherrypy.tools.https_filter = cherrypy.Tool('on_start_resource', https_filter)

def make_secure():
    url = urlparse.urlparse(cherrypy.url(qs=cherrypy.request.query_string))

    if not url[0]=='https':
        secure_url = urlparse.urlunparse(('https', url[1], url[2], url[3], url[4],url[5]))
        cherrypy.request.preserve=True
        raise cherrypy.HTTPRedirect(secure_url)

cherrypy.tools.secure = cherrypy.Tool('before_handler', make_secure, priority=20)

def protect(allowed):
    ok=False
    admin=False
    login=False
    logout=False

    handler=cherrypy.request.handler.callable

    if hasattr(handler, 'has_acl'):
        handler.__func__.get_acl=True
        allowed=cherrypy.request.handler.__call__()

    if cherrypy.request.method=='POST':
        handler=cherrypy.request.handler
        new_handler=cherrypy._cpdispatch.PageHandler(handler.callable, *handler.args, **handler.kwargs)

        def action():
            return new_handler.__call__()
        fl=ForceLogin(acl=allowed, action=action)
    else:
        fl=ForceLogin(acl=allowed, goto=cherrypy.url(qs=cherrypy.request.query_string))
    
    if not fl.match(get_login()):
        fl.do()
    else:
        return

cherrypy.tools.protect= cherrypy.Tool('before_handler', protect)

class CleanupUsers(cherrypy.process.plugins.Monitor):
    def __init__(self, bus, frequency=300):
        self.engine= sqlalchemy.create_engine(config.DB_URL, echo=False)
        self.engine.connect();
        self.Session=sqlalchemy.orm.sessionmaker(bind=self.engine)
        cherrypy.process.plugins.Monitor.__init__(self,bus,self.run,frequency)

    def run(self):
        session=self.Session()

        date=time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(time.time()-24*3600))

        session.query(data.User).filter(data.User.date < date, data.User.status=='NEW', ~data.User.requests.any() ).delete(synchronize_session=False)
        session.query(data.User).filter(data.User.date < date, data.User.status=='NEW', data.User.requests.any() ).update({'login':None, 'password':None, 'date':None, 'status':'', 'uuid':None, 'last_login':None}, synchronize_session=False)

        session.commit()


def set_admin_pw():
    engine= sqlalchemy.create_engine(config.DB_URL, echo=False)
    engine.connect();
    Session=sqlalchemy.orm.sessionmaker(bind=engine)
    session=Session()

    import getpass

    e_mail=raw_input("Enter administrator e-mail: ")
    passwd=getpass.getpass("Enter password: ")
    passwd1=getpass.getpass("Re-enter password: ")

    if passwd!=passwd1:
        print "Passwords do not match."
        return

    u=session.query(data.User).get(0)

    if u==None:
        u=data.User(e_mail,'admin',passwd,'OK')
        session.add(u)
        session.commit()
        u.id=0
        session.commit()
    elif u.login!='admin':
        print 'User table corrupted. Repair it manually.'
        return
    else:
        u.update_passwd(passwd)
        u.e_mail=e_mail
        session.commit()



    




class ForceLogin():
    def __init__(self, message="You have to be logged in to access this page.", acl=None, login=None, goto=None, action=None):
        self.message=message
        if acl==None:
            if login != None:
                if is_sequence(login):
                    acl=[login]
                else:
                    acl=[[login]]
            else:
                acl=['any']

        self.acl=acl
        self.login=login
        self.goto=goto
        self.action=action

    @staticmethod
    def match_acl(acl, login):
        if acl==None:
            return True

        for i in acl:
            if i=='any':
                return True
            elif i=='anonymous' and login==None:
                return True
            elif i=='user' and login!=None:
                return True
            elif i=='admin' and login=='admin':
                return True
            elif is_sequence(i) and login in i:
                return True

        return False


    def match(self, login):
        return ForceLogin.match_acl(self.acl, login)

    def do(self):
        login=get_login()

        ok=False

        if self.match(login):
            ok=True
        elif self.match(None):
            set_login(None)
            ok=True

        if ok:
            return self.success()
        elif login!=None:
            raise cherrypy.HTTPError(403,"You are not authorized to access this page.")

        cherrypy.session['force_login']=self
        self.keep=True
        raise cherrypy.HTTPRedirect(config.APP_ROOT+"/login/")


    def success(self):
        if self.action!=None:
            return self.action()
        elif self.goto != None:
            raise cherrypy.HTTPRedirect(self.goto)
        else:
            util.go_back()



def login_form(tmpl):
    fl=cherrypy.session.get('force_login')

    if fl != None:
        message=fl.message
        fl.keep=True
    else:
        message=cherrypy.session.get('message')
        try:
            cherrypy.session.pop('message')
        except KeyError:
            pass

    return util.render(tmpl, message=message)

def get_login():
    try:
        return cherrypy.session.get('login')
    except: 
        None

def set_login(login=None):
    if login==None:
        cherrypy.session.pop('login')
    else:
        cherrypy.session['login']=login


def random_password():
    f = lambda x, y: ''.join([x[random.randint(0,len(x)-1)] for i in xrange(y)]); 
    return f(list(string.ascii_letters+string.digits), 8) 

class Passwd():
    _cp_config={
        'tools.protect.allowed': ['user', 'admin']
    }


    @cherrypy.expose
    def index(self):
        return login_form('passwd.genshi')

    @cherrypy.expose
    def submit(self, login, oldpass, newpass, verpass):
        session=cherrypy.request.db

        user=data.User.get_by_login(session, login)
        if login != get_login() or user == None:
            clear_session() # cherrypy.session
            cherrypy.session['message']="Error. Please log again."
            raise cherrypy.InternalRedirect("/login/")

        if newpass!=verpass:
            cherrypy.session['message']="Passwords do not match."
            raise cherrypy.InternalRedirect("/login/passwd/")

        if not user.authenticate(oldpass):
            cherrypy.session['message']="Wrong password."
            raise cherrypy.InternalRedirect("/login/passwd/")

        user.update_passwd(newpass)

        util.go_back()

class NewUser():
    @cherrypy.expose
    def index(self):
        return login_form('newuser.genshi')

    @cherrypy.expose
    def submit(self, login, newpass, verpass, email):
        session=cherrypy.request.db

        if data.User.get_by_login(session, login) != None:
            cherrypy.session['message']="User with this login already exists."
            raise cherrypy.InternalRedirect("/login/newuser/")

        old_user=data.User.get_by_email(session, email)

        if old_user != None and old_user.status != '':
            cherrypy.session['message']="User with this e-mail already exists."
            raise cherrypy.InternalRedirect("/login/newuser/")

        if newpass!=verpass:
            cherrypy.session['message']="Passwords do not match."
            raise cherrypy.InternalRedirect("/login/newuser/")

        date=time.strftime("%Y-%m-%d %H:%M:%S")
        uid=uuid.uuid1().hex

        if old_user!=None:
            user=old_user
            user.login=login
            user.status='NEW'
            user.uuid=uid
            user.date=date
            user.update_passwd(newpass)
        else:
            user=data.User(email,login,newpass,'NEW',uid,date)
            session.add(user)

        util.email(email,'email_newuser.genshi',newlogin=login, uuid=uid)
        return util.render('msg_newuser.genshi',newlogin=login)

    @cherrypy.expose
    def confirm(self, login, uuid):
        session=cherrypy.request.db

        user=data.User.get_by_login(session, login)

        if user != None:
            if user.uuid==uuid:
                if user.status=='NEW':
                    user.status='OK'
                    session.commit()
                    return util.render('msg_userconfirm.genshi',login=login)

                if user.status=='OK':
                    raise cherrypy.HTTPError(400, "Account %s already activated."%login)

        raise cherrypy.HTTPError(400)

class Forgotten():
    @cherrypy.expose
    def index(self):
        return login_form('forgotten.genshi')

    @cherrypy.expose
    def submit(self, login, email):
        session=cherrypy.request.db

        user=data.User.get_by_login(session, login)

        if not( user != None and user.e_mail==email and (user.status=='OK' or user.status=='FORGOTTEN')):
            cherrypy.session['message']="User with these credentials does not exist."
            raise cherrypy.InternalRedirect("/login/forgotten/")

        user.status='FORGOTTEN'
        user.uuid=uuid.uuid1().hex
#        user.password=''

        util.email(email,'email_forgotten.genshi',newlogin=login, uuid=user.uuid)
        return util.render('msg_forgotten.genshi',newlogin=login)

    @cherrypy.expose
    def confirm(self, login, uuid):
        session=cherrypy.request.db

        user=data.User.get_by_login(session, login)

        if user != None:
            if user.uuid==uuid:
                if user.status=='FORGOTTEN':
                    user.status='OK'
                    passwd=random_password()
                    user.update_passwd(passwd)
                    return util.render('msg_forgottenconfirm.genshi',newlogin=login,password=passwd)

                if user.status=='OK':
                    raise cherrypy.HTTPError(400, "Expired link.")

        raise cherrypy.HTTPError(400)


class Login:
    _cp_config={
        'tools.secure.on': True,
        'tools.protect.allowed': ['anonymous']
    }

    @cherrypy.expose
    def index(self):
        fl=cherrypy.session.get('force_login')

        if fl!=None:
            fl.keep=True

        return login_form('login.genshi')

    @cherrypy.expose
    def submit(self, login, passwd):
        fl=cherrypy.session.get('force_login', ForceLogin(message=''))

        session=cherrypy.request.db
        if not self.authenticate(session, login, passwd):
            fl.message="Invalid login or password."
    
        return fl.do()

    @cherrypy.expose
    def signout(self):
        set_login(None)
        raise cherrypy.HTTPRedirect(config.SERVER_URL)

    def authenticate(self, session, login, passwd):
        user=data.User.get_by_login(session, login)

        if user != None:
            if user.authenticate(passwd):
                set_login(login)
                user.last_login=time.strftime("%Y-%m-%d %H:%M:%S")
                session.commit()
                return True

        return False

    passwd=Passwd()
    newuser=NewUser()
    forgotten=Forgotten()



def with_acl(acl_fun):
    def with_acl_decorator(handler):
        def wrap_handler(self, *args, **kwargs):
            if wrap_handler.get_acl:
                wrap_handler.get_acl=False
                return acl_fun(self, *args, **kwargs)
            else:
                return handler(self, *args, **kwargs)

        wrap_handler.has_acl=True
        wrap_handler.get_acl=False

        return wrap_handler

    return with_acl_decorator
