#!/usr/bin/python3
import argparse
import glob
import logging
import logging.handlers
import pathlib
import subprocess

from cetools import (
  iso6392tolang,
  sortkey,
  files2quotedstring,
)

prog = 'mkvinfos'
version = '0.1'
author = 'Carl Edman (CarlEdman@gmail.com)'
desc = 'List and Manipulate MKV Track Properties.'

parser = None
args = None
log = logging.getLogger()

def doit(mkvfile: pathlib.Path) -> bool:
  if mkvfile.is_dir():
    log.debug(f'Recursing on "{mkvfile}" ...')
    return max(map(doit, sorted(list(mkvfile.iterdir()), key=sortkey)), default=False)

  if mkvfile.suffix.lower() != ".mkv" or not mkvfile.is_file():
    log.debug(f'"{mkvfile}" is not mkv file, skipping')
    return False

  cl = [ "mkvinfo", "--summary", mkvfile]
  log.info(files2quotedstring(cl))
  if not args.dryrun:
    try:
      subprocess.run(list(map(str, cl)), check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
      if e.returncode == 1:
        log.info(e.stdout)
        log.warning(f'{e.stderr}\n{e}\nProceeding and preserving files ...')
      return False

  return True


if __name__ == '__main__':
  parser = argparse.ArgumentParser(
    fromfile_prefix_chars='@', prog=prog, epilog='Written by: ' + author
  )
  # parser.add_argument(
  #   '-f',
  #   '--force',
  #   dest='force',
  #   action='store_true',
  #   help='force remuxing without any apparent need.',
  # )
  parser.add_argument(
    '-l',
    '--language',
    dest='language',
    action='store',
    default='eng',
    choices=iso6392tolang.keys(),
    help='set language of audio and subtitle tracks to given language ISO639-2 code.',
  )
  parser.add_argument(
    '-d',
    '--dryrun',
    dest='dryrun',
    action='store_true',
    help='do not perform operations, but only print them.',
  )
  parser.add_argument('--version', action='version', version='%(prog)s ' + version)
  parser.add_argument(
    '--verbose',
    dest='loglevel',
    action='store_const',
    const=logging.INFO,
    help='print informational (or higher) log messages.',
  )
  parser.add_argument(
    '--debug',
    dest='loglevel',
    action='store_const',
    const=logging.DEBUG,
    help='print debugging (or higher) log messages.',
  )
  parser.add_argument(
    '--taciturn',
    dest='loglevel',
    action='store_const',
    const=logging.ERROR,
    help='only print error level (or higher) log messages.',
  )
  parser.add_argument(
    '--log', dest='logfile', action='store', help='location of alternate log file.'
  )
  parser.add_argument(
    'paths', nargs='+', help='paths to be operated on; may include wildcards; directories convert content.'
  )
  parser.set_defaults(loglevel=logging.WARN)

  args = parser.parse_args()
  if args.dryrun and args.loglevel > logging.INFO:
    args.loglevel = logging.INFO

  log.setLevel(0)
  logformat = logging.Formatter('%(asctime)s [%(levelname)s]: %(message)s')

  if args.logfile:
    flogger = logging.handlers.WatchedFileHandler(args.logfile, 'a', 'utf-8')
    flogger.setLevel(logging.DEBUG)
    flogger.setFormatter(logformat)
    log.addHandler(flogger)

  slogger = logging.StreamHandler()
  slogger.setLevel(args.loglevel)
  slogger.setFormatter(logformat)
  log.addHandler(slogger)

  if not max(map(doit, (pathlib.Path(fd) for a in args.paths for fd in glob.iglob(a))), default=False):
    log.warning(f'No valid video files found for arguments "{args.paths}".')
