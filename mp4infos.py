#!/usr/bin/python
# -*- coding: latin-1 -*-
# Version: 2.1

import logging, re, shlex, os, os.path, argparse, sys, subprocess
from cetools import *

parser = argparse.ArgumentParser(description='Tabular list of mp4 metadata in directory and all subdirectories.')
parser.add_argument('--version', action='version', version='%(prog)s 2.0')
parser.add_argument('--debug', action='store_true', default=False, help='output debugging messages')
parser.add_argument('directory', nargs='?', default='.', help='Directory to collect from (default: current)')
args = parser.parse_args()
startlogging(None,logging.DEBUG)

cats=['Filename']
tcats=[]
vals=[]

for root, dirs, files in os.walk(args.directory):
  for file in sorted(files):
    if os.path.splitext(file)[1] not in ['.m4a', '.mp4', '.m4r', '.m4b']: continue
    f=os.path.join(root,file)
    debug('Processing "' + f + '"')
    vals.append(dict({'Filename':f}))
    for l in subprocess.check_output(['mp4info',f]).decode(encoding='cp1252').splitlines():
      if rser(r'^\s+(.+?)\s*:\s*(.+?)\s*$',l):
        if rget(0) not in cats: cats.append(rget(0))
        vals[-1][rget(0)]=rget(1)
      if rser(r'^(\d+)\s+(\w+)\s*(.*)$',l):
        type='TrackType'+rget(0)
        if type not in tcats: tcats.append(type)
        vals[-1][type]=rget(1)
        info='TrackInfo'+rget(0)
        if info not in tcats: tcats.append(info)
        vals[-1][info]=rget(2)

print('\t'.join(cats + tcats))
for v in vals:
  print('\t'.join([v[c] if c in v else '' for c in (cats+tcats)]))
