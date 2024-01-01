#!/usr/bin/python

prog = "mp4tomkv"
version = "0.1"
author = "Carl Edman (CarlEdman@gmail.com)"
desc = '''Convert all mp4 files within directory to mkv, perserving meta-data.'''

import argparse
import logging
import logging.handlers
import os
import os.path
import shlex
import sys
import subprocess

from cetools import *
from tagmp4 import *  # pylint: disable=unused-wildcard-import

parser = None
args = None
log = logging.getLogger()


def main():
  for root, _, files in os.walk(args.directory):
    for file in sorted(files):

      f = os.path.join(root, file)
      if not os.path.isfile(f):
        log.warning(f"{f} is not a regular file: skipping")
        continue

      base, ext = os.path.splitext(f)
      if ext not in set([".mp4"]):
        continue

      log.info(f'Processing "{f}"')
      meta = get_meta_mutagen(f)
      if meta["type"] not in ["tvshow", "movie"]:
        log.warning(f'Type of "{f}"={meta["type"]} not recognized: skipping')
        continue

      xml = set_meta_mkvxml(meta)
      log.debug(f'XML: {xml}')
      xmlfile = f"{base}.xml"

      a = [ "mkvmerge", "--output", f"{base}.mkv", "--global-tags", xmlfile, "=", f ]
      log.info(shlex.join(a))
      if not args.dryrun:
        try:
          with open(xmlfile, mode='wt', encoding="utf-8") as tf: tf.write(xml)
          ret = subprocess.run(a, check=False, capture_output=True, encoding="utf-8")
        finally:
          os.remove(xmlfile)
        if ret.returncode != 0:
          log.warning(f"Converting {f} to mkv failed, skipping: {repr(ret.stderr or ret.stdout)}")
          continue

      log.info(f'Deleting "{f}"')
      if not args.dryrun:
        pass
        # os.remove(f)


if __name__ == "__main__":
  parser = argparse.ArgumentParser(fromfile_prefix_chars="@", prog=prog, epilog="Written by: " + author)
  parser.set_defaults(loglevel=logging.WARN)
  parser.add_argument("--version", action="version", version="%(prog)s " + version)
  parser.add_argument("-v", "--verbose", dest="loglevel", action="store_const", const=logging.INFO)
  parser.add_argument("-d", "--debug", dest="loglevel", action="store_const", const=logging.DEBUG)
  parser.add_argument("--dryrun", action="store_true", help="do not perform operations, but only print them.")
  parser.add_argument("directory", nargs="?", default=".", help="Directory to convert in (default: current)")

  args = parser.parse_args()
  if args.dryrun and args.loglevel > logging.INFO:
    args.loglevel = logging.INFO

  log = logging.getLogger()
  log.setLevel(0)

  slogger = logging.StreamHandler()
  slogger.setLevel(args.loglevel)
  slogger.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s: %(message)s"))
  log.addHandler(slogger)

  sys.stdout.reconfigure(encoding="utf-8")
  main()
