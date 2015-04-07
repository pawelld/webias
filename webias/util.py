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
import urlparse
import sqlalchemy
import template
import auth

def staticredirect(section, redirect_section, *args, **kwargs):
    if cherrypy.lib.static.staticdir(section, *args, **kwargs):
        return True
    else:
        path = cherrypy.request.path_info
        raise cherrypy.InternalRedirect(path.replace(section, redirect_section, 1))

cherrypy.tools.staticredirect = cherrypy._cptools.HandlerTool(staticredirect)

class expando(object):
    def __init__(self, **kwargs):
        for k, v in kwargs:
            setattr(self, k, v)

def get_WeBIAS():
    return cherrypy.tree.apps[config.root].root

def gethostbyaddr(ip_address):
    try:
        cache=cherrypy.thread_data.resolve_cache
    except:
        cherrypy.thread_data.resolve_cache={}

    try:
        return cherrypy.thread_data.resolve_cache[ip_address]
    except:
        import socket

        try:
            domain=socket.gethostbyaddr(ip_address)[0]
        except:
            domain=None

        cherrypy.thread_data.resolve_cache[ip_address]=domain

        return domain


def get_template_proc():
    return cherrypy.engine.templateProcessor

def in_site(url):
    urlspl= urlparse.urlparse(url)
    servspl=urlparse.urlparse(config.server_url)
    urlbase=urlspl[1]+urlspl[2]
    servbase=servspl[1]+servspl[2]

    return urlbase.startswith(servbase)

def get_referer():
    return cherrypy.session.get('referer')

def clear_referer():
    try:
        cherrypy.session.pop('referer')
    except:
        pass

def save_referer(url=None):
    clear_referer()

    if url!=None:
        cherrypy.session['referer']=url
    else:
        try:
            url=cherrypy.request.headers['Referer']
            if in_site(url):
                cherrypy.session['referer']=url
        except:
            pass

def clear_session():
    try:
        cherrypy.session.clear()
    except KeyError:
        pass

    raise Error()

def go_back():
    url=get_referer()
    clear_referer()

    try:
        url=cherrypy.session['last_persistent']
    except:
        url=None

    if url==None:
        url=config.root

    raise cherrypy.HTTPRedirect(url)

def check_uuid(text):
    if len(text)!=32:
        raise ValueError
    for letter in text:
        if letter not in "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ":
            raise ValueError


def render(file='system/msg/generic.genshi', app=None, type='xhtml', **kwargs):
    args=template.TemplateArgs(app)

    for key in kwargs:
        args.set(key, kwargs[key])

    return get_template_proc().processTemplate(file, args)

def render_paged(file, page, attr, fallback, app=None, **kwargs):
    args=template.TemplateArgs(app)

    for key in kwargs:
        args.set(key, kwargs[key])

    fb_spl = list(urlparse.urlparse(fallback))
    if fb_spl[4]!='':
        fb_spl[4]=fb_spl[4]+'&p='
    else:
        fb_spl[4]='p='

    args.page_addr=urlparse.urlunparse(fb_spl)

    try:
        return get_template_proc().processTemplatePaged(file, page, attr, args)
    except Exception as e:
        if page!=1:
            raise cherrypy.HTTPRedirect(fallback)
        else:
            raise

def render_query_paged(file, query, page, attr, fallback, filter_kwargs={}, app=None, **kwargs):
    args=[]

    for key in filter_kwargs:
        args.append('%s=%s'%(key, filter_kwargs[key]))

    data=query.filter_by(**filter_kwargs).all()

    fb=fallback

    if args!=[]:
        fb=fb+'?'+'&'.join(args)

    kwargs[attr]=data

    return render_paged(file, page, attr, fb, **kwargs)


def email(address, file='system/email/generic.genshi', app=None, **kwargs):
    return get_template_proc().email_message(address, file, app, **kwargs)

def persistent(handler):

    def wrap_handler(self, *args, **kwargs):
        cherrypy.request.persistent = True
        res=handler(self, *args, **kwargs)
        url = cherrypy.url(qs=cherrypy.request.query_string)
        cherrypy.session['last_persistent']=url
        return res

    return wrap_handler

def clean_session():
    try:
        if cherrypy.request.preserve:
            return
    except:
        pass

    fl=cherrypy.session.get('force_login')

    if fl!=None:
        if fl.keep:
            fl.keep=False
        else:
            cherrypy.session.pop('force_login')

cherrypy.tools.clean_session = cherrypy.Tool('on_end_resource', clean_session)

class FeatureList(object):
    def get_features(self):
        features = dict([(name, el) for name, el in self.__dict__.items() if hasattr(el, '_title')])
        return features

    @cherrypy.expose
    @persistent
    def index(self):
        def sort_key(t):
            try:
                return t[1]._order
            except AttributeError:
                return t[1]._title

        def matches_login(t):
            acl = auth.safe_get_acl(t[1])
            return auth.ForceLogin.match_acl(acl, login)

        login = auth.get_login()

        features = filter(matches_login, self.get_features().items())
        features.sort(key=sort_key)

        return render('system/feature_list.genshi', features=features, title=self._title)

    @property
    def _acl(self):
        return sum(map(auth.safe_get_acl, self.get_features().values()), [])
