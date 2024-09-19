#!/usr/bin/python

import argparse
import glob
import logging
import logging.handlers
import pathlib

prog = "alphabetify"
version = "0.1"
author = "Carl Edman (CarlEdman@gmail.com)"
desc = "Sort files into alphabetic folders."

parser = None
args = None
log = logging.getLogger()


def alphabetify(p: pathlib.Path):
  if not p.exists():
    log.warning(f'"{p}" does not exist')
    return
  if len(p.stem) <= 1:
    log.warning(f'"{p}" is not more than one character long, skipping')
    return
  elif p.stem[0].isnumeric():
    d = p.with_name("#")
  else:
    d = p.with_name(p.stem[0].upper())
  if d.is_dir():
    ...
  elif d.exists():
    log.error(f'"{d}" exists and is not a directory.')
    return
  else:
    try:
      log.info(f"mkdir {d}")
      if not args.dryrun:
        d.mkdir(mode=0o755)
    except Exception as e:
      log.error(f'Unable to create directory "{d}": {e}')
      return
  n = d / p.name
  try:
    log.info(f"mv {p} {n}")
    if not args.dryrun:
      p.rename(n)
  except Exception as e:
    log.error(f"Unable to move {p} to {n}: {e}")
    return


if __name__ == "__main__":
  parser = argparse.ArgumentParser(
    fromfile_prefix_chars="@", prog=prog, epilog="Written by: " + author
  )
  parser.add_argument("--version", action="version", version="%(prog)s " + version)
  parser.add_argument(
    "--dryrun",
    dest="dryrun",
    action="store_true",
    help="do not perform operations, but only print them.",
  )
  parser.add_argument(
    "paths", nargs="+", help="paths to be operated on; may include wildcards"
  )
  parser.add_argument(
    "-v", "--verbose", dest="loglevel", action="store_const", const=logging.INFO
  )
  parser.add_argument(
    "-d", "--debug", dest="loglevel", action="store_const", const=logging.DEBUG
  )
  parser.add_argument("-l", "--log", dest="logfile", action="store")
  parser.set_defaults(loglevel=logging.WARN)

  args = parser.parse_args()
  if args.dryrun and args.loglevel > logging.INFO:
    args.loglevel = logging.INFO

  log.setLevel(0)
  logformat = logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s")

  if args.logfile:
    flogger = logging.handlers.WatchedFileHandler(args.logfile, "a", "utf-8")
    flogger.setLevel(logging.DEBUG)
    flogger.setFormatter(logformat)
    log.addHandler(flogger)

  slogger = logging.StreamHandler()
  slogger.setLevel(args.loglevel)
  slogger.setFormatter(logformat)
  log.addHandler(slogger)

  ig = [pathlib.Path(d) for gd in args.paths for d in glob.iglob(gd)]
  if len(ig) == 0:
    log.warning(f"No paths matching {args.paths}, skipping.")
    exit()

  for d in ig:
    alphabetify(d)
