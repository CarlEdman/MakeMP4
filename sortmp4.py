#!/usr/bin/python

prog='SortMP4'
version='0.5'
author='Carl Edman (CarlEdman@gmail.com)'
desc='Sort mp4s from current directory to target subdirectories'

import argparse
import glob
import logging
import os
import os.path
import re
import shutil
import subprocess
import tempfile

from tagmp4 import get_meta_mutagen
from cetools import * # pylint: disable=unused-wildcard-import

parser = None
args = None
log = logging.getLogger()

def optAndMove(opath,dir,nname=None):
  (odir, oname) = os.path.split(opath)
  if nname==None: nname=oname
  npath = os.path.join(dir,nname)

  if args.optimize:
    log.info(f'Optimizing and moving {opath} to {npath}')
  else:
    log.info(f'Moving {opath} to {npath}')

  if args.dryrun: return

  if not os.path.exists(dir): os.mkdir(dir)
  if not args.overwrite and os.path.exists(npath):
    log.warning(f'{nname} already in {dir}, skipping.')
    return

  if args.optimize:
    t = os.path.join(odir, tempfile.mktemp(suffix=os.path.splitext(oname)[1], prefix='tmp'))
    try:
      os.rename(opath, t)
      cpe = subprocess.run(['mp4file', '--optimize', t], check=True, capture_output=True)
      os.rename(t, opath)
    except subprocess.CalledProcessError as cpe:
      log.error(f'Error code for {cpe.cmd}: {cpe.returncode} : {cpe.stdout} : {cpe.stderr}')
      raise

  try:
    shutil.move(opath, npath)
  except:
    os.remove(npath)
    raise

def sortmp4(f):
  its = get_meta_mutagen(f)

  if not its:
    log.warning(f'Metadata of "{f}" is empty, skipping.')
    return

  if 'type' not in its:
    log.warning(f'{f} has no type, skipping.')
    return

  if 'show' not in its:
    log.warning(f'No show title in {f}, skipping.')
    return

  if its['type'] == "tvshow":
    optAndMove(f,os.path.join(args.target,'TV',sanitize_filename(alphabetize(its['show']))))
    return

  if its['type'] == "movie":
    if 'genre' not in its:
      log.warning(f'No Genre in {f}, skipping.')
      return
    if not os.path.isdir(d:=os.path.join(args.target,'Movies',its['genre'])):
      log.warning(f'Genre "{its["genre"]}" in {f} not recognized, skipping.')
      return
    if 'year' not in its:
      log.warning(f'No year for {f}, skipping.')
      return
    if 'name' not in its:
      log.warning(f'No name for {f}, skipping.')
      return
    shyr = alphabetize(sanitize_filename(f'{its["show"]} ({its["year"]})'))
    tdir = os.path.join(d, shyr)
    if its["name"].startswith(its["show"] + ':'):
      sub = its["name"][len(its["show"])+1:].strip()
      if 'interview' in sub.casefold():
        suffix = '-interview'
      elif 'scene' in sub.casefold():
        suffix = '-deleted'
      elif 'trailer' in sub.casefold():
        suffix = '-trailer'
      else:
        suffix = '-behindthescenes'
      optAndMove(f, tdir, sanitize_filename(alphabetize(f'{sub}{suffix}.mp4')))
    else:
      optAndMove(f, tdir, shyr + ".mp4")
    return

  if its['type'] == "audiobook":
    optAndMove(f, os.path.join(args.target,'Audiobooks'))
    return

  if its['type'] == "ringtone":
    optAndMove(f, os.path.join(args.target,'Music','Ringtones'))
    return

  log.warning(f'Media Type "{its["type"]}" in {f} not recognized, skipping.')
  return

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description=desc,fromfile_prefix_chars='@',prog=prog,epilog='Written by: '+author)
  parser.add_argument('-v','--verbose',dest='loglevel',action='store_const', const=logging.INFO)
  parser.add_argument('-d','--debug',dest='loglevel',action='store_const', const=logging.DEBUG)

  parser.set_defaults(loglevel=logging.WARN)
  parser.add_argument('--dryrun', action='store_true', default=False, help='only print moves, but do not execute them.')
  parser.add_argument('--overwrite', action='store_true', default=False, help='overwrite existing target file.')
  parser.add_argument('--optimize', action='store_true', default=True, help='optimize target file.')
  parser.add_argument('--version', action='version', version='%(prog)s '+version)
  parser.add_argument('--target', action='store', default= 'Y:\\')
  parser.add_argument('files', nargs='*', metavar='FILES', help='files to sort')

  args = parser.parse_args()
  if args.dryrun and args.loglevel > logging.INFO: args.loglevel = logging.INFO

  log.setLevel(0)
  logformat = logging.Formatter('%(asctime)s [%(levelname)s]: %(message)s')

  slogger=logging.StreamHandler()
  slogger.setLevel(args.loglevel)
  slogger.setFormatter(logformat)
  log.addHandler(slogger)

  if not args.files: args.files = ['*.mp4', '*.m4r', '*.m4b']
  infiles = []
  for f in args.files: infiles.extend(glob.glob(f))
  if not infiles:
    log.error(f'No input files.')
    exit(1)

  for f in infiles: sortmp4(f)
