#!/usr/bin/python

from optparse import OptionParser
import tempfile,os,re,sys

parser=OptionParser()

parser.add_option('--name', dest='name')
parser.add_option('--mood', type=int, dest='mood')
(options,args) = parser.parse_args()

mresp={
        0: 'that\'s great',
        1: 'nice to meet you',
        2: 'please discuss this matter with ELIZA',
        3: 'CowboyNeal likes you too'
        }

response='Hello %s, %s.'%(options.name, mresp[options.mood])

print "<TestResult><response>%s</response></TestResult>"%response
