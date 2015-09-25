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


if __name__=="__main__":
    import sys
    import subprocess
    import shlex

    cmdfile=sys.argv[1]
    errfile=sys.argv[2]
    resfile=sys.argv[3]

    cmdline= open(cmdfile).read()
    errfh=open(errfile,'w')
    resfh=open(resfile,'w')

    result = subprocess.call(shlex.split(cmdline), shell=False, stdout=resfh, stderr=errfh)

    errfh.close()
    resfh.close()

    errfh=open(errfile,'r')
    err=errfh.read()
    errfh.close()

    res=None

    if result==0 and err.strip() != 'OK':
        res='OK'

    if result!=0 and err=='':
        res='ERROR: %d'%result

    if res!=None:
        errfh=open(errfile,'w')
        errfh.write(res)
        errfh.close()
