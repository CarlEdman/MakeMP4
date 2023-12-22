#!/usr/bin/python

import argparse
import glob
import logging
import logging.handlers
import subprocess
import pathlib

from cetools import *  # noqa: F403

prog='addsub'
version='0.1'
author='Carl Edman (CarlEdman@gmail.com)'
desc='Integrate subtitles into video files.'

parser = None
args = None
log = logging.getLogger()

def addSubs(dir: pathlib.Path):
  for subfile in dir.iterdir():
    integrated = False
    if not subfile.is_file():
      continue
    if subfile.suffix not in ('.srt'):
      continue

    vidfile = (subfile.parent / subfile.stem).with_suffix('.mkv')
    if vidfile.is_file():
      log.info(f'adding "{subfile}" to "{vidfile}"')
      if args.dryrun:
        continue
      tempfile = vidfile.with_stem(vidfile.stem + "-temp")
      try:
        subprocess.run(["mkvmerge", "-o", str(tempfile), str(vidfile), str(subfile)],
                       check=True, capture_output=True)
        tempfile.replace(vidfile)
      except Exception as e:
        log.error(f'adding "{subfile}" to "{vidfile}" failed: {e}')
      else:
        integrated = True

    vidfile = (subfile.parent / subfile.stem).with_suffix('.mp4')
    if vidfile.is_file():
      log.info(f'adding "{subfile}" to "{vidfile}"')
      if args.dryrun:
        continue
      #integrated = True

    if integrated:
      log.info(f'rm "{subfile}"')
      if args.dryrun:
        continue
      subfile.unlink()
    else:
      log.info(f'No video file found for "{subfile}"')

if __name__ == '__main__':
  parser = argparse.ArgumentParser(fromfile_prefix_chars='@',prog=prog,epilog='Written by: '+author)
  parser.add_argument('--version', action='version', version='%(prog)s ' + version)
  parser.add_argument('--dryrun', dest='dryrun', action='store_true', help='do not perform operations, but only print them.')
  parser.add_argument('dirs', nargs='+', help='directories to be operated on; may include wildcards')
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

  ig = [pathlib.Path(d).resolve() for gd in args.dirs for d in glob.iglob(gd) if pathlib.Path(d).is_dir()]
  if len(ig)==0:
    log.warning(f'No directories matching {args.dirs}, skipping.')
  else:
    for d in ig: 
      addSubs(d)
