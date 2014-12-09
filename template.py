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


import config

import cherrypy
import webhelpers.html.tools
import webhelpers.text
from genshi.template.loader import TemplateLoader
from genshi.template import NewTextTemplate

import auth
import util

class TemplateArgs:
    def __init__(self,app=None):
        if app!=None:
            self.app=app.id

    def set(self, key, val):
        self.__dict__[key]=val

    def get(self, key):
        return self.__dict__[key]


class TemplateProcessor:
    def __init__(self,config):
        self.config=config
        self.templateLoader=TemplateLoader([self.config.BIAS_DIR+'/templates'],auto_reload=True)

    def email(self,addr,sbj,body,attachments=[]):
        import smtplib,os
        from email.MIMEMultipart import MIMEMultipart
        from email.MIMEBase import MIMEBase
        from email.MIMEText import MIMEText
        from email.Utils import  formatdate
        from email import Encoders

        msg=MIMEMultipart()
        msg["To"]      = addr
        msg["From"]    = self.config.MAIL_FROM
        msg["Return-Path"] = self.config.MAIL_FROM
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
            s=smtplib.SMTP(self.config.MAIL_HOST)
            if self.config.MAIL_PASSWD:
                s.login(self.config.MAIL_ACC,self.config.MAIL_PASSWD)
            res = s.sendmail(self.config.MAIL_FROM,addr,msg.as_string())
            s.quit()
            return res
        except:
            cherrypy.engine.log("Cannot send e-mail:\n" + msg.as_string(), 40)

    def email_message(self, address, file='email_generic.genshi', app=None, **kwargs):

        email=self.message(file=file,app=app, type='text', **kwargs)

        try:
            (subject, body)=email.split('\n',1)

            if subject.startswith('Subject:'):
                subject=webhelpers.text.lchop(subject, 'Subject:').strip()
            else:
                raise Exception()
        except:
            subject="Mesage from %s server."%config.SERVER_NAME
            body=email


        return self.email(address,subject,body)

    def message(self, file='msg_generic.genshi', app=None, type='xhtml', **kwargs):
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
            args.mailto=webhelpers.html.tools.mail_to(self.config.E_MAIL, self.config.MAIL_NAME, encode="hex")
        except:
            pass

        try:
            args.e_mail=self.config.E_MAIL
        except:
            pass

        try:
            args.server=self.config.SERVER_NAME
        except:
            pass

        try:
            args.address=self.config.SERVER_URL
        except:
            pass

        try:
            args.css=self.config.CSS_URL
        except:
            pass

        try:
            args.media=self.config.APP_ROOT+'/media'
        except:
            pass

        try:
            args.root=self.config.APP_ROOT
        except:
            pass


        try:
            tmp = cherrypy.request.db
        except:
            pass
        else:
            args.navigation_bar = util.get_WeBIAS().navigation_bar()

        args.login=auth.get_login()

        stream = tmplt.generate(**args.__dict__)
        return stream.render(type)

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

    return util.get_template_proc().processTemplate('BIAS_error.genshi',args)


cherrypy.config.update({'error_page.default': error_page})

