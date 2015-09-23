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
import webhelpers.html.tools
import webhelpers.text
from genshi.template.loader import TemplateLoader
from genshi.template import NewTextTemplate

import auth
import util
import config

import ConfigParser

import pkg_resources
import os

class TemplateArgs:
    def __init__(self,app=None):
        if app!=None:
            self.app=app.id

    def set(self, key, val):
        self.__dict__[key]=val

    def get(self, key):
        return self.__dict__[key]


class TemplateProcessor:
    def __init__(self):
        self.paths = [os.path.join(d, 'templates') for d in [config.server_dir, pkg_resources.resource_filename('webias', 'data')]]
        self.templateLoader=TemplateLoader(self.paths, auto_reload=True)

    def template_filename(self, name):
        for p in self.paths:
            res = os.path.join(p, name)
            if os.path.isfile(res):
                return res

    def base_filename(self):
        return self.template_filename('system/base.genshi')

    def email(self,addr,sbj,body,attachments=[]):
        import smtplib,os
        from email.MIMEMultipart import MIMEMultipart
        from email.MIMEBase import MIMEBase
        from email.MIMEText import MIMEText
        from email.Utils import  formatdate
        from email import Encoders

        msg=MIMEMultipart()
        msg["To"]      = addr
        msg["Subject"] = sbj
        msg['Date'] = formatdate(localtime=True)

        msg.attach(MIMEText(body))

        for file in attachments:
            part = MIMEBase('application', "octet-stream")
            #part = MIMEText('text','plain')
            part.set_payload(open(file,"r").read() )
            Encoders.encode_base64(part)
            part.add_header('Content-Disposition', 'attachment; filename="%s"' % os.path.basename(file))
            msg.attach(part)

        try:
            msg["From"]    = config.get('Mail', 'smtp_mail_from')
            msg["Return-Path"] = config.get('Mail', 'smtp_mail_from')
            s=smtplib.SMTP(config.get('Mail', 'smtp_host'))
            try:
                s.login(config.get('Mail', 'smtp_login'), config.get('Mail', 'smtp_password'))
            except ConfigParser.NoOptionError:
                pass

            res = s.sendmail(config.get('Mail', 'smtp_mail_from'),addr,msg.as_string())
            s.quit()
            return res
        except:
            cherrypy.engine.log("Cannot send e-mail:\n" + msg.as_string(), 40)

    def email_message(self, address, file='system/email/generic.genshi', app=None, **kwargs):

        email=self.message(file=file,app=app, type='text', **kwargs)

        try:
            (subject, body)=email.split('\n',1)

            if subject.startswith('Subject:'):
                subject=webhelpers.text.lchop(subject, 'Subject:').strip()
            else:
                raise Exception()
        except:
            subject="Mesage from %s server."%config.get('Server', 'name')
            body=email


        return self.email(address,subject,body)

    def message(self, file='system/msg/generic.genshi', app=None, type='xhtml', **kwargs):
        args=TemplateArgs(app)

        for key in kwargs:
            args.set(key, kwargs[key])

        return self.processTemplate(file, args, type=type)

    def processTemplate(self,file, args, type='xhtml'):
        if type=='xhtml':
            tmplt=self.templateLoader.load(file)
        elif type=='text':
            tmplt=self.templateLoader.load(file, cls=NewTextTemplate)

        try:
            args.mailto=webhelpers.html.tools.mail_to(config.get('Mail', 'admin_email'), unicode(config.get('Mail', 'admin_name'),"UTF-8"), encode="hex")
        except:
            pass

        try:
            args.e_mail=config.get('Mail', 'admin_email')
        except:
            pass

        try:
            args.server=config.get('Server', 'name')
        except:
            pass

        try:
            args.address=config.server_url
        except:
            pass

        try:
            args.css=config.get('Server', 'css_url')
        except:
            pass

        try:
            args.media=config.root + '/media'
        except:
            pass

        try:
            args.root=config.root
        except:
            pass

        try:
            tmp = cherrypy.request.db
        except:
            pass
        else:
            if tmp is not None:
                args.navigation_bar = util.get_WeBIAS().navigation_bar()
            else:
                args.navigation_bar = []

        args.base = self.base_filename()

        # args.template_base = config.server_dir + '/templates'
        args.login=auth.get_login()

        stream = tmplt.generate(**args.__dict__)

        return stream.render(type, encoding='UTF-8')

    def processTemplatePaged(self,file, page, attr, args):
        count=len(args.get(attr))
        step=20
        start=(page-1)*step

        pages=(count+step-1)/step

        if page<1 or (page>pages and pages>0):
            raise cherrypy.HTTPError(400, "Page out of range.")

        args.set(attr,args.get(attr)[start:start+step])
        args.pages=pages
        args.page=page

        return self.processTemplate(file, args)

def error_page(status, message, traceback, version):
    args=TemplateArgs()
    args.html=message
    args.status=status
    args.traceback=traceback

    import util

    return util.get_template_proc().processTemplate('system/error.genshi',args)


cherrypy.config.update({'error_page.default': error_page})

