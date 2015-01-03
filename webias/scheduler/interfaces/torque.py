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
import re

from . import *
from ... import config

def is_running(pid):
    torqout = Popen("qstat -f %d" % pid, shell=True, stdout=PIPE, stderr=PIPE)
    if re.match("qstat: Unknown Job Id", str(torqout.stderr.read())):
        return False
    for x in torqout.stdout.readlines():
        if re.match("job_state", str(x).strip().split(" ")[0]):
            state = str(x).strip().split(" ")[-1]
            if str(state) in ["R", "Q"]:
                return True
            else:
                return False

def queue_run(JOB_DIR):
    command_qsub=JOB_DIR + '/' + get_cmdfile() + '.qsub'
    fh=open(JOB_DIR + '/' + get_cmdfile() + '.qsub', 'w')
    fh.write('%s %s %s %s' % (config.runner, get_cmdfile(), get_errfile(), get_resfile()))
    fh.close()

    cmd='qsub -d %s %s' % (JOB_DIR, command_qsub)

    out = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE).stdout.read()
    pid = out.strip().split(".")[0]

    return int(pid)
