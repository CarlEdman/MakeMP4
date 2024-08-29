#!/usr/bin/python

import argparse
import glob
import logging
import logging.handlers
import pathlib
import re


prog='fixmix'
version='0.1'
author='Carl Edman (CarlEdman@gmail.com)'
desc='Renames files to conform with title case.'

parser = None
args = None
log = logging.getLogger()

def fixmix(p: pathlib.Path):
    if not p.exists():
        log.warning(f'"{p}" does not exist')
        return
    
shorts = {
    "A": "a",
    "All": "all",
    "Altho": "altho",
    "Although": "although",
    "An": "an",
    "And": "and",
    "As": "as",
    "Because": "because",
    "Before": "before",
    "Beway": "beway",
    "Beways": "beways",
    "Both": "both",
    "Bt": "bt",
    "But": "but",
    "Cause": "cause",
    "Choose": "choose",
    "Either": "either",
    "Else": "else",
    "Ere": "ere",
    "Ergo": "ergo",
    "Even": "even",
    "Except": "except",
    "For": "for",
    "Forasmuch": "forasmuch",
    "How": "how",
    "Howbeit": "howbeit",
    "However": "however",
    "Howsomever": "howsomever",
    "Iff": "if",
    "Ifff": "iff",
    "Less": "less",
    "Lest": "lest",
    "Let": "let",
    "Like": "like",
    "Neither": "neither",
    "Nevertheless": "nevertheless",
    "Nor": "nor",
    "Not": "not",
    "Once": "once",
    "Only": "only",
    "Or": "or",
    "Plus": "plus",
    "Provided": "provided",
    "The": "the",
    "To": "to",
}

if __name__ == '__main__':
  parser = argparse.ArgumentParser(fromfile_prefix_chars='@',prog=prog,epilog='Written by: '+author)
  parser.add_argument('--version', action='version', version='%(prog)s ' + version)
  parser.add_argument('--dryrun', dest='dryrun', action='store_true', help='do not perform operations, but only print them.')
  parser.add_argument('paths', nargs='+', help='paths to be operated on; may include wildcards')
  parser.add_argument('-v','--verbose',dest='loglevel',action='store_const', const=logging.INFO)
  parser.add_argument('-d','--debug',dest='loglevel',action='store_const', const=logging.DEBUG)
  parser.add_argument('-l','--log',dest='logfile',action='store')
  parser.set_defaults(loglevel=logging.WARN)

  args = parser.parse_args()
  if args.dryrun and args.loglevel > logging.INFO:
    args.loglevel = logging.INFO

  log.setLevel(0)
  logformat = logging.Formatter('%(asctime)s [%(levelname)s]: %(message)s')

  if args.logfile:
    flogger=logging.handlers.WatchedFileHandler(args.logfile, 'a', 'utf-8')
    flogger.setLevel(logging.DEBUG)
    flogger.setFormatter(logformat)
    log.addHandler(flogger)

  slogger=logging.StreamHandler()
  slogger.setLevel(args.loglevel)
  slogger.setFormatter(logformat)
  log.addHandler(slogger)

  ig = [pathlib.Path(d) for gd in args.paths for d in glob.iglob(gd)]
  if len(ig)==0:
    log.warning(f'No paths matching {args.paths}, skipping.')

  for d in ig: 
    fixmix(d)
