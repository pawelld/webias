#!/usr/bin/python
# Copyright 2014 Pawel Daniluk
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


import sys
import ConfigParser

# This hack is required because actual module is substituted for a Config
# class.

import cherrypy
cherrypy.engine.autoreload.files.add(__file__)

class Config(ConfigParser.SafeConfigParser):

    def load_config(self, dir):
        import sys
        import os
        import cherrypy

        self.server_dir = os.path.abspath(dir)

        self.read(dir + '/conf/config.ini')
        cherrypy.engine.autoreload.files.add(dir + '/conf/config.ini')

        sys.path.append(self.server_dir + "/modules")

    def get_default(self, section, option, default):
        import ConfigParser

        try:
            return self.get(section, option)
        except ConfigParser.NoOptionError:
            return default

    def rename_section(self, section_from, section_to):
        items = self.items(section_from)
        self.add_section(section_to)

        for item in items:
            self.set(section_to, item[0], item[1])

        self.remove_section(section_from)

    def set_sched_id(self, sched_id):
        section_name = 'Scheduler:' + sched_id

        if section_name in self.sections():
            self.remove_section('Scheduler')
            self.rename_section(section_name, 'Scheduler')

        self.set('Scheduler', 'sched_id', sched_id)

    @property
    def root(self):
        return self.get('Server', 'root')

    @property
    def server_url(self):
        return self.get('Server', 'server_url')

    @property
    def db_url(self):
        return self.get('Database', 'db_url')

    @property
    def sched_id(self):
        return self.get('Scheduler', 'sched_id')

    @property
    def runner(self):
        # TODO: Add clever searching for runner
        return self.get('Scheduler', 'runner')

sys.modules[__name__] = Config()
