#!/usr/bin/python

prog='mp4tomkv'
version='0.1'
author='Carl Edman (CarlEdman@gmail.com)'
desc='Convert all mp4 files within directory to mkv, perserving meta-data.'

import argparse
import logging
import logging.handlers
import os
import os.path
import sys
import csv

from cetools import *
from tagmp4 import *  # pylint: disable=unused-wildcard-import

parser = None
args = None
log = logging.getLogger()

def main():
  for root, _, files in os.walk(args.directory):
    for file in sorted(files):
      pass

if __name__ == "__main__":
  parser = argparse.ArgumentParser(fromfile_prefix_chars='@',prog=prog,epilog='Written by: '+author)
  parser.add_argument('--version', action='version', version='%(prog)s ' + version)
  parser.add_argument('-v','--verbose',dest='loglevel',action='store_const', const=logging.INFO)
  parser.add_argument('-d','--debug',dest='loglevel',action='store_const', const=logging.DEBUG)
  parser.set_defaults(loglevel=logging.WARN)
  parser.add_argument('directory', nargs='?', default='.', help='Directory to convert in (default: current)')

  args = parser.parse_args()

  log = logging.getLogger()
  log.setLevel(0)

  slogger=logging.StreamHandler()
  slogger.setLevel(args.loglevel)
  slogger.setFormatter(logging.Formatter('[%(levelname)s] %(asctime)s: %(message)s'))
  log.addHandler(slogger)

  sys.stdout.reconfigure(encoding='utf-8')
  main()
