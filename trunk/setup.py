#!/usr/bin/env python


#from ez_setup import use_setuptools
#use_setuptools()

#Pylint will treat all variables as constants.
#pylint: disable=C0103

import os
import os.path
from setuptools import setup, find_packages


setup(name='WeBIAS',
      version='0.x',
      description='',
      author='Pawel Daniluk',
      author_email='pawel@bioexploratorium.pl',
      url='http://webias.googlecode.com',
      packages=find_packages(),
      entry_points={'console_scripts': [
          'webiasd = webias:main',
          'webiasschedd = webias.scheduler:main',
          'webias-createdir = webias.console:create_dir'
      ]},
      install_requires = [
          'CherryPy >= 3.6',
          'Genshi >= 0.7',
          'SQLAlchemy >= 0.9',
          'MySQL-python >= 1.2.5',
          'WebHelpers >= 1.3',
          'importlib >= 1'
      ],
      include_package_data = True,
      )
