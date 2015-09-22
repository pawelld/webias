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

import webias.gnosis.xml.objectify as objectify
import config
import time
import data
import query
import field

import sys, traceback


try:
    import biofield
except ImportError:
    cherrypy.engine.log('Failed to import biofield module. Bioinformatics fields will be disabled. Install BioPython to enable them.')

import auth

import uuid

import util
from util import *

class Description(objectify._XO_):
    def __str__(self):
        try:
            return self._XML
        except AttributeError:
            return self.PCDATA


class Application(objectify._XO_):

    @staticmethod
    def get_run(session, request, runid=None):
        run=request.get_run(runid)

        if run==None:
            if runid!=None:
                raise cherrypy.HTTPError(400, "Please provide a valid runid or none.")
            else:
                raise cherrypy.HTTPError(400, "No run found.")

        return run

    @staticmethod
    def get_file(session, r, pathname):
        if pathname is not "":
            if pathname.strip("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ._-/")!='':
                raise cherrypy.HTTPError(400, "Please provide a valid filename.")


        (path,name)=data.File.split_name(pathname)

        file=r.get_file(path, name)

        if file==None:
            raise cherrypy.HTTPError(400,"File not found.")

        return file

    def __setattr__(self, item, value):
        if item=='setup' and hasattr(value, 'module'):
            for m in value.module:
                __import__(m.PCDATA)
        return super(Application, self).__setattr__(item, value)


    def get_dbapp(self):
        session = cherrypy.request.db
        return data.Application.get_app(session, self.id)

    @property
    def _acl(self):
        dbapp = self.get_dbapp()
        acl = dbapp.get_acl()

        return acl


    def get_user(self, session, pars):
        try:
            email=pars.BIAS_email._getValue()
        except:
            email=None

        return data.User.get_by_email(session, email, insert=True)

    def is_available(self):
        return self.enabled and auth.ForceLogin().match_acl(self._acl, auth.get_login())

    def store_query(self, session, pars):
        user=self.get_user(session, pars)

        date=time.strftime("%Y-%m-%d %H:%M:%S")
        uid=uuid.uuid1().hex
        ip_address=cherrypy.request.remote.ip

        # print "query::"+pars._makeXML()
        req=data.Request(date=date, status="CREATING", uuid=uid, ip_address=ip_address, user=user, app_id=self.id, query=pars._makeXML(), session=cherrypy.session.id)
        session.add(req)
        pars._store(session, req)
        req.status='READY'

        return req

    def render_form(self, query=None):
        return render('system/form/form.genshi', app=self, description=str(self.description), parameters=self.parameters, query=query)

    @cherrypy.expose
    # @auth.with_acl(app_acl)
    @persistent
    def index(self):
        return self.render_form()

    def validate_acl(self, *args, **kwargs):
        status, messages, pars=self.parameters.process_parameters(kwargs)

        cherrypy.session['validate_result']=[status, messages, pars]

        if status!='VALID':
            return self._acl
        else:
            return self.submit_acl(*args, **kwargs)



    def submit_acl(self, *args, **kwargs):
        val=field.Email().process_parameters(kwargs)[2]

        if val==None:
            return self._acl
        else:
            email=val._getValue()

            session=cherrypy.request.db
            user=data.User.get_by_email(session, email, insert=False)

            if user==None or user.login==None:
                return self._acl
            else:
                if auth.ForceLogin.match_acl(self._acl, user.login):
                    return [[user.login],'admin']
                else:
                    return ['admin']

    def submit_int(self, status, messages, pars, nobase=False):
        if status!='VALID':
            return render('system/form/error.genshi',app=self, errors=[m.message for m in messages],nobase=nobase)
        else:
            session=cherrypy.request.db
            req = self.store_query(session, pars)
            cherrypy.request.req_sub=True
            if(req.user.id<=0):
                email=False
            else:
                email=True
                util.email(req.user.e_mail,'system/email/scheduled.genshi',app=self,uuid=req.uuid)

            return render('system/msg/scheduled.genshi',app=self,uuid=req.uuid,email=email,nobase=nobase)


    @cherrypy.expose
    @auth.with_acl(validate_acl, noauth=True)
    def validate(self,**kwds):
        status, messages, pars=cherrypy.session.get('validate_result')
        return self.submit_int(status, messages, pars, nobase=True)

    @cherrypy.expose
    @auth.with_acl(submit_acl)
    def submit(self,**kwds):
        status, messages, pars=self.parameters.process_parameters(kwds)
        return self.submit_int(status, messages, pars)




    def render_result(self, uuid, owner, tag, starred, query_string, runid=None, result_string=None):
        q=query.Query(query_string)

        r=result_string != None and query.Result(result_string) or None

        try:
            param_table=self.setup.param_table_template.PCDATA
        except:
            param_table="system/results/param_table.genshi"

        param_table = cherrypy.engine.templateProcessor.template_filename(param_table)

        try:
            result_table=self.setup.result_table_template.PCDATA
        except:
            result_table="system/results/result_table.genshi"

        result_table = cherrypy.engine.templateProcessor.template_filename(result_table)

        try:
            if self.setup.result_template!=None:
                tmpl=self.setup.result_template.PCDATA
        except:
            tmpl="system/results/results.genshi"


        return render(tmpl,app=self,uuid=uuid, owner=owner, runid=runid, query=q, result=r, param_table=param_table, result_table=result_table, tag=tag, starred=starred)

    def result_acl(self,uuid,runid=None,**kwargs):
        session=cherrypy.request.db

        request=data.Request.get_request(session, uuid)

        if request.user.login!=None:
            l=[request.user.login]
        else:
            l='any'

        return [l, 'admin']

    @cherrypy.expose
    @auth.with_acl(result_acl)
    @persistent
    def params(self,uuid,runid=None):
        session=cherrypy.request.db

        request=data.Request.get_request(session,uuid)

        return self.render_result(uuid, request.user.login, request.tag, request.starred, request.query)

    @cherrypy.expose
    @auth.with_acl(result_acl)
    @persistent
    def result(self,uuid,runid=None):
        session=cherrypy.request.db

        request=data.Request.get_request(session, uuid)

        if request.status=='FINISHED' or runid!=None:
            run=self.get_run(session,request,runid)
            return self.render_result(uuid, request.user.login, request.tag, request.starred, request.query, run.id, run.result)
        elif request.status=='FAILED':
            return render('system/results/failure.genshi',app=self, uuid=request.uuid, html="Your job (%s) has exited abnormally. <br/><br/> If you have any questions, please contact our administrator"%(request.uuid))
        elif request.status in ['READY', 'PROCESSING']:
            cherrypy.response.headers['Refresh']='30; url=%s/%s/result?uuid=%s'%(config.server_url,self.id,request.uuid)
            return render('system/results/no_results.genshi', uuid=request.uuid, app=self)
        else:
            raise cherrypy.HTTPError(500, "Your job (%s) has an invalid status (%s)."%(request.uuid, request.status))

    @cherrypy.expose
    @auth.with_acl(result_acl)
    def file(self,uuid,pathname,runid=None):
        session=cherrypy.request.db

        request=data.Request.get_request(session,uuid)

        try:
            run=self.get_run(session,request,runid)
            file=self.get_file(session,run,pathname)
        except cherrypy.HTTPError as e:
            if runid==None:
                file=self.get_file(session,request,pathname)
            else:
                raise e

        ext=file.name.split('.')[-1]

        cherrypy.response.headers['Content-disposition']="attachment; filename=%s"%file.name

        mime_types = eval(config.get('Server', 'mime_types'))

        if ext in mime_types:
            mime = mime_types[ext]
            cherrypy.response.headers['Content-type'] = mime
            if mime == 'text/html':
                cherrypy.response.headers['Content-disposition']="inline; filename=%s"%file.name
        else:
            cherrypy.response.headers['Content-type']='application/octet-stream'

        return file.data

class AppGroup():
    def __init__(self, apps=[]):
        self.elements={}

        for app in apps:
            self.addEntry(app)

    def addEntry(self, entry):
        self.elements[entry.id]=entry

    @property
    def enabled(self):
        return True

    def _cp_dispatch(self, vpath):
        if not vpath:
            return self.index

        el=self.elements.get(vpath[0],None)

        if el and not el.enabled:
            el=None

        return el

    def avail_elts(self):
        return sorted(filter(lambda el: el.is_available() ,self.elements.values()), key=lambda el: el.name)

    def used_apps(self):
        l=[hasattr(el, 'used_apps') and el.used_apps() or [el.id] for el in self.elements.values()]

        try:
            l.append([self.id])
        except:
            pass

        return sum(l, [])

    def is_available(self):
        return len(self.avail_elts()) > 0

    @cherrypy.expose
    @persistent
    def index(self):
        try:
            desc=str(self.description)
        except:
            desc=None

        return render('system/app_list.genshi',apps=self.avail_elts(), name=getattr(self, 'name', None), description=desc)

class AppGroupEntry():
    def __init__(self, app):
        self.app=app

    @property
    def id(self):
        return self.app.id

    @property
    def info(self):
        return self.app.info

    @property
    def name(self):
        return self.app.name

    @property
    def enabled(self):
        return self.app.enabled

    def _cp_dispatch(self, vpath):
        if vpath:
            return getattr(self.app,vpath[0],None)

        return None

    def used_apps(self):
        return [self.app.id]

    def is_available(self):
        return self.app.is_available()

    @property
    def _acl(self):
        return self.app._acl

    @cherrypy.expose
    @persistent
    def index(self):
        return self.app.index()

class AppGroupXML(AppGroup, objectify._XO_):
    def assign_elts(self,elts):
        self.elements={}
        for el in self._seq:
            try:
                el.assign_elts(elts)
                self.elements[el.id]=el
            except:
                pass


class AppGroupEntryXML(objectify._XO_, AppGroupEntry):
    def assign_elts(self, elts):
        self.app=elts[self.appid]




objectify._XO_application=Application
objectify._XO_description=Description
objectify._XO_appgroup=AppGroupXML
objectify._XO_appgroupentry=AppGroupEntryXML

