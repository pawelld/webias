#!/usr/bin/env python


#from ez_setup import use_setuptools
#use_setuptools()

#Pylint will treat all variables as constants.
#pylint: disable=C0103

import os
import os.path
from setuptools import setup, find_packages


setup(name='WeBIAS',
      version='1.0.2',
      author='Pawel Daniluk',
      author_email='pawel@bioexploratorium.pl',
      description = "WeBIAS is a web server for publishing services. A service is a standalone command line program, which has to be supplied with certain parameters, and its output should be returned. Computations may require significant resources and time, and may have to be scheduled for later execution. Users are informed when their requests are finished and can peruse results at their convenience.",
      license = "AGPL",
      url='http://bioinfo.imdik.pan.pl/webias',
      packages=find_packages(),
      entry_points={'console_scripts': [
          'webiasd = webias:main',
          'webiasschedd = webias.scheduler:main',
          'webias-createdir = webias.console:create_dir',
          'webias-createsource= webias.console:create_source'
      ]},
      install_requires = [
          'CherryPy >= 3.8',
          'Genshi >= 0.7',
          'SQLAlchemy >= 0.9',
          'MySQL-python >= 1.2.5',
          'WebHelpers >= 1.3',
          'importlib >= 1'
      ],
      include_package_data = True,
      )
