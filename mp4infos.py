#!/usr/bin/python

prog='mp4infos'
version='2.1'
author='Carl Edman (CarlEdman@gmail.com)'
desc='Tabular list of mp4 metadata in directory and all subdirectories.'

import argparse
import codecs
import logging
import logging.handlers
import os
import os.path
import re
import shlex
import subprocess
import sys

from cetools import *

parser = None
args = None
log = logging.getLogger()

#sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

def main():
  cats=['Filename']
  tcats=[]
  vals=[]

  for root, dirs, files in os.walk(args.directory):
    for file in sorted(files):
      if os.path.splitext(file)[1] not in ['.m4a', '.mp4', '.m4r', '.m4b']: continue
      f=os.path.join(root,file)
      log.debug('Processing "' + f + '"')
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


if __name__ == "__main__":
  parser = argparse.ArgumentParser(fromfile_prefix_chars='@',prog=prog,epilog='Written by: '+author)
  parser.add_argument('--version', action='version', version='%(prog)s ' + version)
  parser.add_argument('-v','--verbose',dest='loglevel',action='store_const', const=logging.INFO)
  parser.add_argument('-d','--debug',dest='loglevel',action='store_const', const=logging.DEBUG)
  parser.set_defaults(loglevel=logging.WARN)
  parser.add_argument('directory', nargs='?', default='.', help='Directory to collect from (default: current)')

  args = parser.parse_args()

  log = logging.getLogger()
  log.setLevel(0)

  slogger=logging.StreamHandler()
  slogger.setLevel(args.loglevel)
  slogger.setFormatter(logging.Formatter('[%(levelname)s] %(asctime)s: %(message)s'))
  log.addHandler(slogger)

  main()