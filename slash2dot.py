#!/usr/bin/python

import argparse
import glob
import logging
import logging.handlers
import pathlib

from cetools import *  # noqa: F403

prog='slash2dot'
version='0.1'
author='Carl Edman (CarlEdman@gmail.com)'
desc='Rename files.'

parser = None
args = None
log = logging.getLogger()

def slash2dot(p: pathlib.Path):
  dir = pathlib.Path.cwd().resolve()
  try:
    r = p.resolve().relative_to(dir)
  except ValueError:
    log.error(f"Path {p} cannot be rendered relative to {dir}, skipping")
    return
  s = pathlib.Path(args.separator.join(r.parts))
  if (s.exists()):
    log.error(f"Path {r} cannot be moved to {s} because the target exists, skipping")
    return
  log.info(f'mv "{r}" "{s}"')
  if args.dryrun:
    return
  r.rename(s)

if __name__ == '__main__':
  parser = argparse.ArgumentParser(fromfile_prefix_chars='@',prog=prog,epilog='Written by: '+author)
  parser.add_argument('--version', action='version', version='%(prog)s ' + version)
  parser.add_argument('--dryrun', dest='dryrun', action='store_true', help='do not perform operations, but only print them.')
  parser.add_argument('paths', nargs='+', help='paths to be operated on; may include wildcards')
  parser.add_argument('-s', '--separator', dest='separator', action='store', default='.', help='separator to replace slashes')
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
  else:
    for d in ig: 
      slash2dot(d)
