#!/usr/bin/python

import argparse
import logging
import logging.handlers
import os
import os.path
import sys
import csv

from cetools import * # noqa: F403
from tagmp4 import * # noqa: F403

prog = "mp4infos"
version = "2.1"
author = "Carl Edman (CarlEdman@gmail.com)"
desc = "Tabular list of mp4 metadata in directory and all subdirectories."

parser = None
args = None
log = logging.getLogger()


def main():
  vals = []
  for root, _, files in os.walk(args.directory):
    for file in sorted(files):
      if os.path.splitext(file)[1] not in [".m4a", ".mp4", ".m4r", ".m4b"]:
        continue
      f = os.path.join(root, file)
      log.info(f'Processing "{f}"')
      ret = get_meta_mutagen(f)
      ret["Filename"] = f
      vals.append(ret)

  cats = set(k for v in vals for k in v.keys())
  if len(cats) == 0:
    log.warning("No valid mp4info produced.")
    return
  writer = csv.DictWriter(sys.stdout, fieldnames=cats, lineterminator="\n")
  writer.writeheader()
  writer.writerows(vals)


if __name__ == "__main__":
  parser = argparse.ArgumentParser(
    fromfile_prefix_chars="@", prog=prog, epilog="Written by: " + author
  )
  parser.add_argument("--version", action="version", version="%(prog)s " + version)
  parser.add_argument(
    "-v", "--verbose", dest="loglevel", action="store_const", const=logging.INFO
  )
  parser.add_argument(
    "-d", "--debug", dest="loglevel", action="store_const", const=logging.DEBUG
  )
  parser.set_defaults(loglevel=logging.WARN)
  parser.add_argument(
    "directory",
    nargs="?",
    default=".",
    help="Directory to collect from (default: current)",
  )

  args = parser.parse_args()

  log.setLevel(0)
  slogger = logging.StreamHandler()
  slogger.setLevel(args.loglevel)
  slogger.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s: %(message)s"))
  log.addHandler(slogger)

  sys.stdout.reconfigure(encoding="utf-8")
  main()
