#!/usr/bin/python

import argparse
import glob
import logging
import logging.handlers
import pathlib
import re

import cetools

prog = "serialize"
version = "0.2"
author = "Carl Edman (CarlEdman@gmail.com)"
desc = "Sort files into seasonal folders."

parser = None
args = None
log = logging.getLogger()

pat_epis = re.compile(r"\bS(?P<season>\d+)E(?P<episode>\d+)")
pat_spec = re.compile(r"\bSP(?P<episode>\d+)\b")


def serialize(p: pathlib.Path):
  if not p.exists():
    log.warning(f'"{p}" does not exist')
    return
  if not p.is_file():
    log.warning(f'"{p}" is not a file')
    return

  if mat := re.search(pat_epis, p.stem):
    if int(mat.group("season")) == 0:
      d = "Specials"
      n = re.sub(r"\bS00E", "SP", p.name, count=1)
    else:
      d = f"Season {mat.group('season')}"
      n = p.name
  elif re.search(pat_spec, p.stem):
    d = "Specials"
    n = p.name
  else:
    log.warning(f'"{p}" not serializable, skipping')
    return

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
    "--title-case",
    dest="titlecase",
    action="store_true",
    help="rename files to proper title case.",
  )
  parser.add_argument(
    "--verbose",
    dest="loglevel",
    action="store_const",
    const=logging.INFO,
    help="print informational (or higher) log messages",
  )
  parser.add_argument(
    "--debug",
    dest="loglevel",
    action="store_const",
    const=logging.DEBUG,
    help="print debugging (or higher) log messages.",
  )
  parser.add_argument(
    "--taciturn",
    dest="loglevel",
    action="store_const",
    const=logging.ERROR,
    help="only print error level (or higher) log messages.",
  )
  parser.add_argument(
    "--log", dest="logfile", action="store", help="location of alternate log file"
  )
  parser.add_argument(
    "paths", nargs="+", help="paths to be operated on; may include wildcards"
  )
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

  for d in ig:
    serialize(d)
