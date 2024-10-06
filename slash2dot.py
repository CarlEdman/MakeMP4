#!/usr/bin/python3

import argparse
import glob
import logging
import logging.handlers
import pathlib

from cetools import (
  to_title_case,
)

prog = "slash2dot"
version = "0.1"
author = "Carl Edman (CarlEdman@gmail.com)"
desc = "Rename files."

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
  if args.flatten:
    s = dir / r.name
  else:
    s = pathlib.Path(args.separator.join(r.parts))
  if args.titlecase:
    s = s.with_stem(to_title_case(s.stem))
  if s.exists():
    log.error(f"Path {r} cannot be moved to {s} because the target exists, skipping")
    return
  log.info(f'mv "{r}" "{s}"')
  if not args.dryrun:
    r.rename(s)
  if args.empty:
    t = r.parent
    while all(False for _ in t.iterdir()):
      log.info(f"rmdir {t}")
      if not args.dryrun:
        t.rmdir()
      t = t.parent


if __name__ == "__main__":
  parser = argparse.ArgumentParser(
    fromfile_prefix_chars="@", prog=prog, epilog="Written by: " + author
  )
  parser.add_argument("--version", action="version", version="%(prog)s " + version)
  parser.add_argument(
    "--verbose",
    dest="loglevel",
    action="store_const",
    const=logging.INFO,
    help="print informational (or higher) log messages.",
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
    "--log", dest="logfile", action="store", help="location of alternate log file."
  )
  parser.add_argument(
    "--dryrun",
    dest="dryrun",
    action="store_true",
    help="do not perform operations, but only print them.",
  )
  parser.add_argument(
    "--separator",
    dest="separator",
    action="store",
    default=".",
    help="separator to replace slashes",
  )
  parser.add_argument(
    "--flatten",
    dest="flatten",
    action="store_true",
    help="ignore all but final path element",
  )
  parser.add_argument(
    "--empty",
    dest="empty",
    action="store_true",
    help="remove directories left empty by action",
  )
  parser.add_argument(
    "--title-case",
    dest="titlecase",
    action="store_true",
    help="rename files to proper title case.",
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
  else:
    for d in ig:
      slash2dot(d)
