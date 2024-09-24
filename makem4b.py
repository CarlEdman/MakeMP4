#!/usr/bin/python3
import argparse
import glob
import logging
import os
import os.path
import subprocess

from cetools import TitleHandler

prog = "MakeM4B"
version = "0.3"
author = "Carl Edman (CarlEdman@gmail.com)"
desc = "Convert audio files to m4b audiobook, creating chapters as necessary."

parser = None
args = None
log = logging.getLogger()


def main():
  outfile = args.outfile
  _, oext = os.path.splitext(outfile)
  if not oext:
    outfile += ".m4b"
  infiles = [j for i in args.infiles for j in sorted(glob.glob(i))]

  qaac = ["qaac", "--threading"]
  qaac += args.qaacopts.split()
  qaac += ["--concat", "-o", outfile]
  qaac += infiles

  log.info(qaac)
  log.debug(subprocess.check_output(qaac))


if __name__ == "__main__":
  parser = argparse.ArgumentParser(
    fromfile_prefix_chars="@", prog=prog, epilog="Written by: " + author
  )
  parser.add_argument("--version", action="version", version="%(prog)s " + version)
  parser.add_argument(
    "--qaacopts",
    type=str,
    default="--tvbr 45 --quality 2",
    help="options to pass along to qaac",
  )
  parser.add_argument("outfile", type=str, help="resulting m4b file")
  parser.add_argument("infiles", type=str, nargs="+", help="audiofiles to be added")
  parser.add_argument(
    "-v", "--verbose", dest="loglevel", action="store_const", const=logging.INFO
  )
  parser.add_argument(
    "-d", "--debug", dest="loglevel", action="store_const", const=logging.DEBUG
  )
  parser.set_defaults(loglevel=logging.WARN)
  parser.add_argument("-l", "--log", dest="logfile", action="store")

  args = parser.parse_args()

  log = logging.getLogger()
  log.setLevel(0)

  if args.logfile:
    flogger = logging.handlers.WatchedFileHandler(args.logfile, "a", "utf-8")
    flogger.setLevel(logging.DEBUG)
    flogger.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s"))
    log.addHandler(flogger)

  tlogger = TitleHandler()
  tlogger.setLevel(logging.DEBUG)
  tlogger.setFormatter(logging.Formatter("makem4b: %(message)s"))
  log.addHandler(tlogger)

  slogger = logging.StreamHandler()
  slogger.setLevel(args.loglevel)
  slogger.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s: %(message)s"))
  log.addHandler(slogger)

  main()
