#!/usr/bin/python

import argparse
import logging
import pathlib
import shutil
import subprocess
import tempfile

from tagmp4 import get_meta_mutagen, get_meta_enzyme
from cetools import *  # noqa: F403
from sanitize_filename import sanitize

prog='SortMP4'
version='1.0'
author='Carl Edman (CarlEdman@gmail.com)'
desc='Sort mp4s from current directory to target subdirectories'

parser = None
args = None
log = logging.getLogger()

mp4_exts = set([".mp4", ".m4r", "m4b"])
mkv_exts = set([".mkv"])

def sortmp4(f):
  its = get_meta_mutagen(f)

  if not its:
    log.warning(f'Metadata of "{f}" is empty, skipping.')
    return

  if 'type' not in its:
    log.warning(f'{f} has no type, skipping.')
    return

  if its['type'] == "audiobook":
    n = args.target / 'Audiobooks' / f.name
  elif its['type'] == "ringtone":
    n = args.target / 'Music' / 'Ringtones' / f.name
  elif 'show' not in its:
    log.warning(f'No show title in {f}, skipping.')
    return
  elif its['type'] == "tvshow":
    n = args.target / 'TV' / sanitize(alphabetize(its['show'])) / f.name
  elif its['type'] == "movie":
    if 'genre' not in its:
      log.warning(f'No Genre in {f}, skipping.')
      return
    d = args.target / 'Movies' / its['genre']
    if not d.is_dir():
      log.warning(f'Genre "{its["genre"]}" in {f} not recognized, skipping.')
      return
    if 'year' not in its:
      log.warning(f'No year for {f}, skipping.')
      return
    if 'name' not in its:
      log.warning(f'No name for {f}, skipping.')
      return
    name = str(its["name"])
    show = str(its["show"])
    shyr = f'{show} ({its["year"]})'
    tfile = shyr + ".mp4"
    if name.startswith(show + ':'):
      sub = name[len(show)+1:].strip()
      if 'interview' in sub.casefold():
        suffix = '-interview'
      elif 'scene' in sub.casefold():
        suffix = '-deleted'
      elif 'trailer' in sub.casefold():
        suffix = '-trailer'
      else:
        suffix = '-behindthescenes'
      tfile = f'{sub}{suffix}.mp4'
    n = d / sanitize(alphabetize(shyr)) / sanitize(alphabetize(tfile))
    log.warning(f'Media Type "{its["type"]}" in {f} not recognized, skipping.')
    return

  if not args.overwrite and n.exists():
    log.warning(f'{n} already exists, skipping.')
    return

  if args.optimize:
    log.info(f'Optimizing and moving {f} to {n}')
  else:
    log.info(f'Moving {f} to {n}')

  if args.dryrun: return

  n.parent.mkdir(parents=True, exist_ok=True)

  if args.optimize:
    try:
      t = f.parent / tempfile.mktemp(suffix=f.suffix, prefix='tmp')
      f.rename(t)
      subprocess.run(['mp4file', '--optimize', t], check=True, capture_output=True)
      t.rename(f)
    except subprocess.CalledProcessError as cpe:
      log.error(f'Error code for {cpe.cmd}: {cpe.returncode} : {cpe.stdout} : {cpe.stderr}')
      raise

  try:
    shutil.move(f, n)
  except:
    n.unlink()
    raise

def sortmkv(f):
  its = get_meta_enzyme(f)

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description=desc,fromfile_prefix_chars='@',prog=prog,epilog='Written by: '+author)
  parser.add_argument('-v','--verbose',dest='loglevel',action='store_const', const=logging.INFO)
  parser.add_argument('-d','--debug',dest='loglevel',action='store_const', const=logging.DEBUG)

  parser.set_defaults(loglevel=logging.WARN)
  parser.add_argument('--dryrun', action='store_true', default=False, help='only print moves, but do not execute them.')
  parser.add_argument('--overwrite', action='store_true', default=False, help='overwrite existing target file.')
  parser.add_argument('--optimize', action='store_true', default=True, help='optimize target file.')
  parser.add_argument('--version', action='version', version='%(prog)s '+version)
  parser.add_argument('--target', type=dirpath, action='store', default= 'Y:\\')
  parser.add_argument('globs', nargs='*', default = [ '*' + e for e in mp4_exts | mkv_exts ], help='glob pattern of files to sort')

  args = parser.parse_args()
  if args.dryrun and args.loglevel > logging.INFO: args.loglevel = logging.INFO

  log.setLevel(0)
  logformat = logging.Formatter('%(asctime)s [%(levelname)s]: %(message)s')

  slogger=logging.StreamHandler()
  slogger.setLevel(args.loglevel)
  slogger.setFormatter(logformat)
  log.addHandler(slogger)

  infiles = [f for e in args.globs for f in pathlib.Path.cwd().glob(e)]
  if not infiles:
    log.error(f'No matching input files.')
    exit(1)

  for f in infiles:
    if f.suffix in mp4_exts:
      sortmp4(f)
    elif f.suffix in mkv_exts:
      sortmkv(f)
    else:
      log.warning(f"File extension {f.suffix} for {f} not recognized, skipping.")
