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

import gnosis.xml.objectify as objectify
import config
import time
import data 
import query
import field

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

    def app_acl(self, *args, **kwargs):
        try:
            return eval(self.acl.PCDATA)
        except:
            return ['any']

    def get_user(self, session, pars):
        try:
            email=pars.BIAS_email._getValue()
        except:
            email=None

        return data.User.get_by_email(session, email, insert=True)

    def store_query(self, session, pars):
        user=self.get_user(session, pars)

        date=time.strftime("%Y-%m-%d %H:%M:%S")
        uid=uuid.uuid1().hex
        ip_address=cherrypy.request.remote.ip
        
        print "query::"+pars._makeXML()
        req=data.Request(date=date, status="CREATING", uuid=uid, ip_address=ip_address, user=user, app_id=self.id, query=pars._makeXML(), session=cherrypy.session.id)
        session.add(req)
        pars._store(session, req)
        req.status='READY'

        return req

    def render_form(self, query=None):
        return render('form.genshi', app=self, description=str(self.description), parameters=self.parameters, query=query)

    @cherrypy.expose    
    @auth.with_acl(app_acl)
    @persistent
    def index(self):
        return self.render_form()
         
    def submit_acl(self, *args, **kwargs):

        val=field.Email().process_parameters(kwargs)[2]

        if val==None:
            return self.app_acl(args, kwargs)
        else:
            email=val._getValue()

            session=cherrypy.request.db
            user=data.User.get_by_email(session, email, insert=False)

            if user==None or user.login==None:
                return self.app_acl(args, kwargs)
            else:
                return [[user.login],'admin']

    @cherrypy.expose
    def validate(self,*lst,**kwds):
        status, messages, pars=self.parameters.process_parameters(kwds)

        if status!='VALID': 
            return render('form_error.genshi',app=self, errors=[m.message for m in messages])
        else:
            
            cherrypy.session['valid_kwds']=kwds
        

            return render('msg_scheduled.genshi',app=self,uuid=req.uuid,email=email)

    @cherrypy.expose
    @auth.with_acl(submit_acl)
    def submit(self,*lst,**parkwds):
        kwds=cherrypy.session.get('valid_kwds', parkwds)

        try:
            cherrypy.session.pop('valid_kwds')
        except:
            pass


        status, messages, pars=self.parameters.process_parameters(kwds)

        if status!='VALID': 
            return render('form_error.genshi',app=self, errors=[m.message for m in messages])
        else:
            session=cherrypy.request.db
            req = self.store_query(session, pars)
            cherrypy.request.req_sub=True
            if(req.user.id<=0):
                email=False
            else:
                email=True
                util.email(req.user.e_mail,'email_scheduled.genshi',app=self,uuid=req.uuid)

            return render('msg_scheduled.genshi',app=self,uuid=req.uuid,email=email)




    def render_result(self, uuid, owner, tag, starred, query_string, runid=None, result_string=None):
        q=query.Query(query_string)

        r=result_string != None and query.Result(result_string) or None

        try:
            if self.setup.param_table_template!=None:
                param_table=self.setup.param_table_template.PCDATA
        except:
            param_table="param_table.genshi"

        try:
            if self.setup.result_table_template!=None:
                result_table=self.setup.result_table_template.PCDATA
        except:
            result_table="result_table.genshi"

        try:
            if self.setup.result_template!=None:
                tmpl=self.setup.result_template.PCDATA
        except:
            tmpl="results.genshi"


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
            return render('failure.genshi',app=self, uuid=request.uuid, html="Your job (%s) has exited abnormally. <br/><br/> If you have any questions, please contact our administrator"%(request.uuid))
        elif request.status in ['READY', 'PROCESSING']:
            cherrypy.response.headers['Refresh']='30; url=%s/%s/result?uuid=%s'%(config.SERVER_URL,self.id,request.uuid)
            return render('no_results.genshi', uuid=request.uuid, app=self)
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
        if ext in config.MIME_TYPES:
            cherrypy.response.headers['Content-type']=config.MIME_TYPES[ext]
            if config.MIME_TYPES[ext]=='text/html':
                cherrypy.response.headers['Content-disposition']="inline; filename=%s"%file.name
        else:
            cherrypy.response.headers['Content-type']='application/octet-stream'

        return file.data
            
objectify._XO_application=Application
objectify._XO_description=Description

