#!/usr/bin/python3

import argparse
import logging
import os
import os.path
import re
import subprocess

prog = "mp4killcomments"
version = "2.1"
author = "Carl Edman (CarlEdman@gmail.com)"
desc = "Disable commentary (and other multi-language tracks) on all mp4 files in directory (and subdirectories)."

parser = None
args = None
log = logging.getLogger()


def main():
  for root, dirs, files in os.walk(args.directory):
    for file in sorted(files):
      if os.path.splitext(file)[1] not in [".mp4"]:
        continue
      f = os.path.join(root, file)
      ts = []
      inp = subprocess.check_output(["mp4track", "--list", f])
      for l in inp.split(r"track"):
        if not (m := re.fullmatch(r"^\[(\d+)\]((.|\s)*)", l)):
          continue
        if len(ts) != int(m[0]):
          log.error(f"Track number {int(m[0]):d} inconsistent in {f}")
          exit(-1)
        ts.append(
          dict(
            [
              (kv.split("=", 1)[0].strip(), kv.split("=", 1)[1].strip())
              for kv in m[1].splitlines()
            ]
          )
        )
        ts[-1]["index"] = m[0]
      ats = 0
      for t in ts:
        if t["type"] != "audio":
          continue
        if ats == 0:
          log.info(f'Enabling track id {t['id']} in {f}')
          subprocess.call(["mp4track", f, "--track-id", t["id"], "--enabled", "true"])
        else:
          log.info(f'Disabling track id {t['id']} in {f}')
          subprocess.call(["mp4track", f, "--track-id", t["id"], "--enabled", "false"])
        ats += 1


if __name__ == "__main__":
  parser = argparse.ArgumentParser(
    fromfile_prefix_chars="@", prog=prog, epilog="Written by: " + author
  )
  parser.add_argument("--version", action="version", version="%(prog)s 1.0")
  parser.add_argument(
    "--debug", action="store_true", default=False, help="output debugging messages"
  )
  parser.add_argument(
    "directory",
    nargs="?",
    default=".",
    help="Directory to collect from (default: current)",
  )

  args = parser.parse_args()

  log = logging.getLogger()
  log.setLevel(0)

  slogger = logging.StreamHandler()
  slogger.setLevel(args.loglevel)
  slogger.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s: %(message)s"))
  log.addHandler(slogger)

  main()
