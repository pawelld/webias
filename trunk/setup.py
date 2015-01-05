#!/usr/bin/env python


#from ez_setup import use_setuptools
#use_setuptools()

#Pylint will treat all variables as constants.
#pylint: disable=C0103

import os
import os.path
from setuptools import setup


setup(name='WeBIAS',
      version='0.x',
      description='',
      author='Pawel Daniluk',
      author_email='pawel@bioexploratorium.pl',
      url='http://webias.googlecode.com',
      packages=['webias', 'webias.scheduler'],
      entry_points={'console_scripts': [
          'webiasd = webias:main',
          'webiasschedd = webias.scheduler:main',
          'webias-createdir = webias.console:create_dir'
      ]},
      include_package_data = True
      )
