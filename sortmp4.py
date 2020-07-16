#!/usr/bin/python

prog='SortMP4'
version='0.5'
author='Carl Edman (CarlEdman@gmail.com)'
desc='Sort mp4s from current directory to target subdirectories'

import shutil
import os
import os.path
import argparse
import logging
import subprocess
import glob
import re

import mutagen
from mutagen.mp4 import MP4
from cetools import *

parser = None
args = None
log = logging.getLogger()

def optAndMove(opath,dir,nname=None):
  (odir, oname) = os.path.split(opath)
  if nname==None: nname=oname
  npath = os.path.join(dir,nname)

  log.info(f'Optimizing and moving {opath} to {npath}')
  if args.dryrun: return

  if not os.path.exists(dir): os.mkdir(dir)
  if os.path.exists(npath):
    log.warning(f'{nname} already in {dir}, skipping.')
    return

  t = os.path.join(odir, f'temp{os.path.splitext(oname)[1]}')
  try:
    os.rename(opath, t)
    cp = subprocess.run(['mp4file', '--optimize', t], check=True, capture_output=True)
  except subprocess.CalledProcessError as cpe:
    log.error(f'Error code for {cpe.cmd}: {cpe.returncode} : {cpe.stdout} : {cpe.stderr}')
    raise

  try:
    shutil.move(t, npath)
  except:
    os.remove(npath)
    raise

def main(f):
  try:
    mutmp4 = MP4(f)
  except mutagen.MutagenError:
    log.warning(f'Opening "{f}" metadata with mutagen failed, skipping.')
    continue

  tags = mutmp4.tags

  if tags is None:
    log.warning(f'Metadata of "{f}" is empty, skipping.')
    continue

  if 'stik' in tags and tags['stik']:
    stik = tags['stik'][0]
  else:
    log.warning(f'No Media Type in {f}, skipping.')
    continue

  if '©gen' in tags and tags['©gen']:
    genre = tags['©gen'][0]
  else:
    log.warning(f'No Genre in {f}, skipping.')
    continue

  if '©day' in tags and tags['©day']:
    year = tags['©day'][0]
  else:
    log.warning(f'No Year in {f}, skipping.')
    continue

  if 'desc' in tags and tags['desc']:
    pass
  else:
    log.warning(f'No Description in {f}, skipping.')
    continue

  if '©nam' in tags and tags['©nam']:
    name = tags['©nam'][0]
  else:
    log.warning(f'No Name in {f}, skipping.')
    continue

  if 'covr' in tags and tags['covr']:
    pass
  else:
    log.warning(f'No Cover Art in {f}, skipping.')
    continue

  if stik in { 6, 10 }:
    if 'tvsh' in tags and tags['tvsh']:
      tvsh = tags['tvsh'][0].strip()
    else:
      log.warning(f'No tv show title in {f}.')
      continue

    optAndMove(f,os.path.join(args.target,'TV',sanitize_filename(alphabetize(tvsh))))
  elif stik in { 0, 9 }:
    if not os.path.isdir(os.path.join(args.target,'Movies',genre)):
      log.warning(f'Genre "{genre}" in {f} not recognized, skipping.')
      continue

    if ':' in name:
      (main, sub) = name.rsplit(':', 2)
      sub = sub.strip()
      if 'interview' in sub.casefold():
        suffix = '-interview'
      elif 'scene' in sub.casefold():
        suffix = '-deleted'
      elif 'trailer' in sub.casefold():
        suffix = '-trailer'
      else:
        suffix = '-behindthescenes'
      ndir  = sanitize_filename(alphabetize(f'{main} ({year})'))
      nname = sanitize_filename(alphabetize(f'{sub}{suffix}.mp4'))
      optAndMove(f, os.path.join(args.target, 'Movies', genre, ndir), nname)
    else:
      ndir  = sanitize_filename(alphabetize(f'{name} ({year})'))
      nname = ndir + ".mp4"
      optAndMove(f, os.path.join(args.target, 'Movies', genre, ndir), nname)
  elif stik in { 2 }:
    optAndMove(f, os.path.join(args.target,'Audiobooks'))
  elif stik in { 14 }:
    optAndMove(f, os.path.join(args.target,'Music','Ringtones'))
  else:
    log.warning(f'Media Type "{stik}" in {f} not recognized, skipping.')
    continue

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description=desc,fromfile_prefix_chars='@',prog=prog,epilog='Written by: '+author)
  parser.add_argument('-v','--verbose',dest='loglevel',action='store_const', const=logging.INFO)
  parser.add_argument('-d','--debug',dest='loglevel',action='store_const', const=logging.DEBUG)

  parser.set_defaults(loglevel=logging.WARN)
  parser.add_argument('--dryrun', action='store_true', default=False, help='only print moves, but do not execute them.')
  parser.add_argument('--version', action='version', version='%(prog)s '+version)
  parser.add_argument('--target', action='store', default= 'Y:\\')
  parser.add_argument('files', nargs='*', metavar='FILES', help='files to sort')

  args = parser.parse_args()
  if args.dryrun and args.loglevel > logging.INFO: args.loglevel = logging.INFO

  log = logging.getLogger()
  logformat = logging.Formatter('%(asctime)s [%(levelname)s]: %(message)s')

  slogger=logging.StreamHandler()
  slogger.setLevel(args.loglevel)
  slogger.setFormatter(logformat)
  log.addHandler(slogger)

  if not args.files: args.files = ['*.mp4', '*.m4r', '*.m4b', '*.m4a']
  infiles = []
  for f in args.files: infiles.extend(glob.glob(f))
  if not infiles:
    log.error(f'No input files.')
    exit(1)

  for f in infiles: sortmp4(f)
