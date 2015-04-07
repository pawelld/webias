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

from subprocess import Popen,PIPE
import re

from . import *

from ... import config

def is_running(pid):
    squeue = config.get_default('Scheduler', 'squeue', 'squeue')
    query_res = Popen("%s -j %d" % (squeue, pid), shell=True, stdout=PIPE, stderr=PIPE)
    if re.match("slurm_load_jobs error: Invalid job id specified", str(query_res.stderr.read())):
        return False
    for x in query_res.stdout.readlines():
        (jobid, part, name, user, state, time, nodes, nodelist) = x.split()
        try:
            jobid = int(jobid)
        except ValueError:
            pass
        else:
            if jobid == pid:
                if str(state) not in ["CA", "CD", "F", "TO"]:
                    return True
                else:
                    return False

    return False

def queue_run(JOB_DIR):
    command_qsub = JOB_DIR+'/'+ get_cmdfile() + '.sbatch'
    fh = open(JOB_DIR + '/' + get_cmdfile() + '.sbatch', 'w')
    fh.write('#!/bin/sh\n')
    fh.write('%s %s %s %s' % (config.runner, get_cmdfile(), get_errfile(), get_resfile()))
    fh.close()

    sbatch = config.get_default('Scheduler', 'sbatch', 'sbatch')
    cmd = '%s -D %s %s' % (sbatch, JOB_DIR, command_qsub)

    proc = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)

    out = proc.stdout.read()
    err = proc.stderr.read()
    pid = out.strip().split(" ")[-1]

    return int(pid)

