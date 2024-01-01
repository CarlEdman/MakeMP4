#!/usr/bin/python

import argparse
import glob
import logging
import logging.handlers
import pathlib
import subprocess

from cetools import basestem

prog='mp4tomkv'
version='0.1'
author='Carl Edman (CarlEdman@gmail.com)'
desc='Convert mp4 files to mkv files (incorporating separate subtitles).'

parser = None
args = None
log = logging.getLogger()

def mp4tomkv(mp4file: pathlib.Path):
  if mp4file.suffix not in ('.mp4') or not mp4file.is_file():
    log.warning(f'"{mp4file}" is not an mp4 file')
    return
  mkvfile = mp4file.with_suffix('.mkv')
  if mkvfile.exists():
    log.warning(f'"{mkvfile}" exists')
    return
  subfiles = []
  for subfile in mp4file.parent.iterdir():
    if not subfile.is_file():
      continue
    if subfile.suffix not in ('.srt'):
      continue
    if basestem(subfile).with_suffix('.mp4') != mp4file:
      continue
    subfiles.append(subfile)
  log.info(f'mkvmerge -o "{mkvfile}" "{mp4file}" ' + ' '.join([f'"{s}"' for s in subfiles]))
  if args.dryrun:
    return
  subprocess.run(["mkvmerge", "-o", str(mkvfile), str(mp4file)] + [str(s) for s in subfiles],
                 check=True, capture_output=True)
  mp4file.unlink()
  for s in subfiles:
    s.unlink()
  

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
    exit()

  for d in ig: 
    mp4tomkv(d)
