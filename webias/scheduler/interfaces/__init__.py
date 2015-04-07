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

from ... import config

def get_cmdfile():
    return config.get('Scheduler', 'cmd_file')

def get_resfile():
    return config.get('Scheduler', 'res_file')

def get_errfile():
    return config.get('Scheduler', 'err_file')
