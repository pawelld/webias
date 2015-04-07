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
import time

import config

import template

import auth
import data
import sqlalchemy

from util import *

report_frequencies = ['N', 'W', 'D', 'H', 'M']

def set_report_freq(reportsetting_class, report_type, report_frequency, report_list=None, ent_id=None):
    session=cherrypy.request.db

    login = auth.get_login()
    user = data.User.get_by_login(session, login)

    query = session.query(reportsetting_class).filter(reportsetting_class.user == user).filter(reportsetting_class.report_type == report_type)

    add_args = {}

    if report_list is not None:
        ent = data.get_by_id(session, report_list.report_class, ent_id)
        query = query.with_parent(ent)
        add_args[report_list.id_column] = ent.id

        if login != 'admin':
            acl = ent.acls.filter(data.ACL.userrole_id == user.role.id, data.ACL.privilege == 'REPORTS').one()
            add_args['acl_id'] = acl.id

    setting = query.first()

    if setting is None:
        setting = reportsetting_class(user=user, report_type=report_type, frequency=report_frequency, **add_args)
        session.add(setting)

    setting.frequency = report_frequency
    session.commit()

class ReportList:
    @property
    def _acl(self):
        session=cherrypy.request.db
        user_list = map(lambda x: x.login, self.acl_class.get_allowed_users(session, ('REPORTS', )).all())

        return [user_list, 'admin']

    @cherrypy.expose
    @persistent
    def index(self, **kwargs):
        session=cherrypy.request.db

        login = auth.get_login()
        user = data.User.get_by_login(session, login)

        # entities=session.query(self.report_class)
        entities=data.get_allowed_entities(session, self.report_class, user, ('REPORTS', ))

        reportsettings = session.query(self.reportsetting_class).filter(self.reportsetting_class.user == user)

        settings = {}

        for ent in entities:
            settings[ent.id] = {}
            for t in self.reportsetting_class.types:
                settings[ent.id][t] = (report_frequencies[0], None)

        for rs in reportsettings:
            ent_id = getattr(rs, self.id_column)
            settings[ent_id][rs.report_type] = (rs.frequency, rs.last)

        return render(self.template, entities=entities, settings=settings, frequencies=report_frequencies, types_dict=self.reportsetting_class.types, **kwargs)

    @cherrypy.expose
    def set(self, ent_id, report_type, report_frequency):
        set_report_freq(self.reportsetting_class, report_type, report_frequency, self, ent_id)
        go_back()

class Applications(ReportList):

    _title="Applications"
    _caption="Report application usage."

    report_class = data.Application

    acl_class = data.ApplicationACL

    reportsetting_class = data.ReportSettingApp
    id_column = 'app_id'
    template = "system/reports/apps.genshi"

    @cherrypy.expose
    @auth.with_acl(auth.app_acl('REPORTS'))
    def set(self, *args, **kwargs):
        return ReportList.set(self, *args, **kwargs)


class Schedulers(ReportList):

    _title="Schedulers"
    _caption="Control site access."

    report_class = data.Scheduler

    acl_class = data.SchedulerACL

    reportsetting_class = data.ReportSettingSched
    id_column = 'sched_id'
    template = "system/reports/schedulers.genshi"

    @cherrypy.expose
    @auth.with_acl(auth.sched_acl('REPORTS'))
    def set(self, *args, **kwargs):
        return ReportList.set(self, *args, **kwargs)


class Server:
    _title = 'WeBIAS server'
    _caption = 'Health of the server'

    _acl = ['admin']


    reportsetting_class = data.ReportSettingServ

    @cherrypy.expose
    @persistent
    def index(self):
        session=cherrypy.request.db

        login = auth.get_login()
        user = data.User.get_by_login(session, login)

        reportsettings = session.query(self.reportsetting_class).filter(self.reportsetting_class.user == user)

        settings = {}

        for t in self.reportsetting_class.types:
            settings[t] = (report_frequencies[0], None)


        for rs in reportsettings:
            settings[rs.report_type] = (rs.frequency, rs.last)

        return render('system/reports/server.genshi', settings=settings, frequencies=report_frequencies, types_dict=self.reportsetting_class.types)

    @cherrypy.expose
    def set(self, report_type, report_frequency):
        set_report_freq(self.reportsetting_class, report_type, report_frequency)
        go_back()

class Reports(FeatureList):
    _cp_config={
        'tools.secure.on': True,
        'tools.hit_recorder.on': False,
        'tools.protect.allowed': ['admin']
    }

    _title = 'Reports'

    def __init__(self):
        self.server=Server()
        self.applications=Applications()
        self.schedulers=Schedulers()


class ReportSender(cherrypy.process.plugins.Monitor):
    def __init__(self, bus, frequency=60):
        self.engine= sqlalchemy.create_engine(config.db_url, echo=False, pool_recycle=1800)
        self.engine.connect();
        self.Session=sqlalchemy.orm.sessionmaker(bind=self.engine)
        cherrypy.process.plugins.Monitor.__init__(self,bus,self.run,frequency)

    def run(self):
        from collections import defaultdict

        session=self.Session()

        reportsettings=session.query(data.ReportSetting)

        date = time.time()

        reports = defaultdict(list)

        for rs in reportsettings:
            if rs.is_due(date):
                try:
                    aa = (rs, rs.generate(session, date))
                except NotImplementedError:
                    cherrypy.engine.log('Cannot generate report: %s' % str(rs))
                else:
                    reports[rs.user].append(aa)

        session.commit()

        template_processor = template.TemplateProcessor()

        for user in reports:
            rep_list = [rs.render(items, template_processor) for (rs, items) in reports[user] if items != []]

            if rep_list != []:
                report_text = '\n'.join(rep_list)
                email(user.e_mail, content=report_text)
