#!/usr/bin/python3
import argparse
import glob
import pathlib
import re
import logging

from logging.handlers import WatchedFileHandler

import cetools

prog = "serialize"
version = "0.4"
author = "Carl Edman (CarlEdman@gmail.com)"
desc = "Sort files into seasonal folders."

log = logging.getLogger()
parser = None
args = None

# for h in logging.handlers:

#   case h:

videxts = {
  ".mp4",
  ".mkv",
  ".avi",
  ".mpg",
  ".m4v",
  ".mp3",
}

pat = re.compile(
  r'(?P<show>.*)\s+(S(?P<season>\d+)E|(?P<special>SP))(?P<episode>\d+)(?P<extraeps>(E\d+)+)?(?:\s+(?P<desc>.*))?'
)

def serialize(p: pathlib.Path):
  if not p.exists():
    log.warning(f'"{p}" does not exist, skipping.')
    return
  if not p.is_file():
    log.warning(f'"{p}" is not a file, skipping.')
    return
  if p.suffix not in videxts:
    log.warning(f'"{p}" is not a recognized video file, skipping.')
    return

  if mat := pat.fullmatch(p.stem):
    show = mat.group('show')
    season = mat.group('season')
    special = mat.group('special')
    episode = mat.group('episode')
    extraeps = mat.group('extraeps')
    desc = mat.group('desc')
    if special or (season and int(season) == 0):
      if episode and int(episode) > 100:
        d = 'Extras'
        if desc:
          n = f'{desc}{p.suffix}'
        else:
          log.warning(f'"{p}" is not a recognized extras video file, skipping.')
          return
      else:
        d = 'Specials'
        n = f'{show} S00E{episode}'
        if extraeps:
          n += extraeps
        if desc:
          n += f' {desc}'
        n += p.suffix
    elif season and int(season) > 0 and episode and int(episode) > 0:
      d = f'Season {int(season):02}'
      n = f'{show} S{season}E{episode}'
      if extraeps:
        n += extraeps
      if desc:
        n += f' {desc}'
      n += p.suffix
  else:
    d = 'Extras'
    n = str(p)
#    log.warning(f'"{p}" not serializable, skipping')
#    return

  if args.titlecase:
    n = cetools.to_title_case(n)

  td = p.parent / d
  if not td.exists():
    log.info(f"mkdir {td}")
    if not args.dryrun:
      td.mkdir(mode=0o755)
  elif td.is_dir():
    pass
  else:
    log.warning(f'"{td}" exists and is not a directory, skipping {p}')
    return

  t = td / n
  if t.exists():
    log.warning(f'"{t}" exists, skipping {p}')
    return

  log.info(f'mv "{p}" "{t}"')
  if not args.dryrun:
    p.rename(t)

if __name__ == "__main__":
  parser = argparse.ArgumentParser(fromfile_prefix_chars="@", prog=prog, epilog="Written by: " + author)

  parser.add_argument(
    "--debug",
    dest="loglevel",
    action="store_const",
    const=logging.DEBUG,
    help="print debugging (or higher) log messages",
  )
  parser.add_argument(
    "--taciturn",
    dest="loglevel",
    action="store_const",
    const=logging.ERROR,
    help="only print error level (or higher) log messages.",
  )
  parser.add_argument(
    "--verbose",
    dest="loglevel",
    action="store_const",
    const=logging.INFO,
    help="print informational (or higher) log messages",
  )
  parser.add_argument(
    "--title-case",
    dest="titlecase",
    action="store_true",
    help="rename files to proper title case",
  )
  parser.add_argument(
    "--version",
    action="version",
    version="%(prog)s " + version,
  )
  parser.add_argument(
    "--dryrun",
    dest="dryrun",
    action="store_true",
    help="do not perform operations, but only print them",
  )
  parser.add_argument(
    "--log",
    dest="logfile",
    action="store",
    help="location of alternate log file",
  )
  parser.add_argument(
    "paths",
    nargs="+",
    help="paths to be operated on; may include wildcards",
  )

  parser.set_defaults(loglevel=logging.WARN)

  args = parser.parse_args()
  if args.dryrun and args.loglevel > logging.INFO:
    args.loglevel = logging.INFO

  log.setLevel(0)
  logformat = logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s")

  if args.logfile:
    flogger = WatchedFileHandler(args.logfile, "a", "utf-8")
    flogger.setLevel(logging.DEBUG)
    flogger.setFormatter(logformat)
    log.addHandler(flogger)

  slogger = logging.StreamHandler()
  slogger.setLevel(args.loglevel)
  slogger.setFormatter(logformat)
  log.addHandler(slogger)

  fs = (pathlib.Path(fd) for a in args.paths for fd in glob.iglob(a))

  errand = False
  for f in fs:
    errand = True
    if f.is_dir():
      for f2 in f.iterdir():
        if f2.is_file():
          serialize(f2)
          errand = True
    elif f.is_file():
      serialize(f)
      errand = True
      
  if not errand:
    log.warning(f"No proper files matching {args.paths}.")
