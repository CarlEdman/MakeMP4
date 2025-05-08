#!python3

import argparse
import glob
import logging
import logging.handlers
import pathlib
import re

prog = "plexname"
version = "0.4"
author = "Carl Edman (CarlEdman@gmail.com)"
desc = "Rename TV show extras to Plex preferred names."

parser = None
args = None
log = logging.getLogger()


def plexRename(dir: pathlib.Path) -> None:
  base = dir.name
  pat = re.compile(
    re.escape(base)
    + r"\s+S(?P<season>\d+)(E(?P<episode>\d+(-E?\d+)?))?(V(?P<volume>\d+))?\s*(?P<name>.*\.(mkv|mp4|avi))"
  )

  nr = {}
  nrany = False
  for file in dir.iterdir():
    if not file.is_file():
      continue
    mat = pat.fullmatch(file.name)
    if mat is None:
      continue
    nrany = True
    d = mat.groupdict()
    season = int(d["season"])
    episode = d["episode"]
    volume = d["volume"]
    name = d["name"]
    if season > 0 and (episode or volume):
      continue
    if season > 0:
      pre = f"Season {season:d} "
      if not name.startswith(pre):
        name = pre + name
    nr[base + " S00E{:02d} " + name] = file.name

  if not nrany:
    log.warning(f"No appropriate files in {dir}, skipping.")
    return

  for nfn, ep in zip(sorted(nr.keys()), range(1, len(nr) + 1)):
    ofile = dir / nr[nfn]
    nfile = dir / nfn.format(ep)
    if ofile == nfile:
      continue
    if nfile.exists():
      log.warning(f"{nfile} already exists, skipping.")
      continue
    log.info(f'mv "{ofile}" "{nfile}"')
    if args.dryrun:
      continue
    ofile.rename(nfile)


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
    "dirs", nargs="+", help="directories to be operated on; may include wildcards"
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

  ig = [
    pathlib.Path(d).resolve()
    for gd in args.dirs
    for d in glob.iglob(gd)
    if pathlib.Path(d).is_dir()
  ]
  if len(ig) == 0:
    log.warning(f"No directories matching {args.dirs}, skipping.")
    exit()

  for d in ig:
    plexRename(d)
