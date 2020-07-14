#!/usr/bin/python

prog='mp4infos'
version='2.1'
author='Carl Edman (CarlEdman@gmail.com)'

import logging
import re
import shlex
import os
import os.path
import argparse
import sys
import subprocess
import codecs

from cetools import *

sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

parser = argparse.ArgumentParser(description='Tabular list of mp4 metadata in directory and all subdirectories.')
parser.add_argument('--version', action='version', version='%(prog)s ' + version)
parser.add_argument('-v','--verbose',dest='loglevel',action='store_const', const=logging.INFO)
parser.add_argument('-d','--debug',dest='loglevel',action='store_const', const=logging.DEBUG)
parser.set_defaults(loglevel=logging.WARN)
parser.add_argument('directory', nargs='?', default='.', help='Directory to collect from (default: current)')
args = parser.parse_args()
startlogging(None,args.loglevel)

cats=['Filename']
tcats=[]
vals=[]

for root, dirs, files in os.walk(args.directory):
  for file in sorted(files):
    if os.path.splitext(file)[1] not in ['.m4a', '.mp4', '.m4r', '.m4b']: continue
    f=os.path.join(root,file)
    debug('Processing "' + f + '"')
    vals.append(dict({'Filename':f}))
    try:
      mi = subprocess.check_output(['mp4info',f])
    except subprocess.CalledProcessError:
      continue
    for l in mi.decode(errors='ignore').splitlines():
      if m := re.fullmatch(r'\s+(.+?)\s*:\s*(.+?)\s*',l):
        if m[1] not in cats: cats.append(m[1])
        vals[-1][m[1]]=m[2]
      if m := re.fullmatch(r'(\d+)\s+(\w+)\s*(.*)',l):
        type='TrackType'+m[1]
        if type not in tcats: tcats.append(type)
        vals[-1][type]=m[2]
        info='TrackInfo'+m[1]
        if info not in tcats: tcats.append(info)
        vals[-1][info]=m[3]

print('\t'.join(cats + tcats))
for v in vals:
  print('\t'.join([v[c] if c in v else '' for c in (cats+tcats)]))
