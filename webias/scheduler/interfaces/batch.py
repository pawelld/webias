#!/usr/bin/python

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


from subprocess import Popen, PIPE

from . import *

from ... import config
import sys

def is_running(pid):
    var = Popen("ps %s | wc -l" % pid, shell=True, stdout=PIPE).stdout.read().strip()
    if int(var) - 1 == 0:
        return False
    else:
        return True

def queue_run(JOB_DIR):
    pid = Popen([config.runner, get_cmdfile(), get_errfile(), get_resfile()], cwd=JOB_DIR).pid
    return pid
