#!/usr/bin/python

import argparse
import glob
import logging
import logging.handlers

# import subprocess
import pathlib
import sys
import requests

prog = "episodify"
version = "0.1"
author = "Carl Edman (CarlEdman@gmail.com)"
desc = "Retrieve episode names for TV Shows."

parser = None
args = None
log = logging.getLogger()


def episodify(p: pathlib.Path):
  url = "https://api.themoviedb.org/3/authentication"

  headers = {
    "accept": "application/json",
    "Authorization": args.authorization,
  }

  response = requests.get(url, headers=headers)

  print(response.text)
  print(url)
  print(headers)
  response = requests.get(url, headers=headers)
  print(response.text)

  # url = f"https://api.themoviedb.org/3/account/${args.accountid}/lists?page=1",
  # headers = {
  #     "accept": "application/json",
  #     "Authorization": authorization,
  # }

  # response = requests.get(url, headers=headers)
  # print(response.text)

  # url = f"https://api.themoviedb.org/3/account/${args.accountid}/watchlist/movies?language=en-US&page=1&sort_by=created_at.asc"

  # headers = {
  #     "accept": "application/json",
  #     "Authorization": authorization,
  # }

  # response = requests.get(url, headers=headers)

  # print(response.text)


if __name__ == "__main__":
  print(sys.argv)
  parser = argparse.ArgumentParser(
    prog=prog, epilog=f"Written by: ${author}"
  )  # fromfile_prefix_chars='@',
  parser.add_argument("--version", action="version", version=f"${prog} ${version}")
  parser.add_argument(
    "--dryrun",
    dest="dryrun",
    action="store_true",
    help="do not perform operations, but only print them.",
  )
  parser.add_argument(
    "--authorization",
    dest="authorization",
    nargs=1,
    help="obtained from themoviedb.org Access Token Auth",
  )
  parser.add_argument(
    "--api_key",
    dest="api_key",
    nargs=1,
    help="obtained from themoviedb.org API Key Auth",
  )
  parser.add_argument(
    "--accountid",
    dest="accountid",
    type=int,
    nargs=1,
    help="obtained from themoviedb.org account_id",
  )
  parser.add_argument(
    "-v", "--verbose", dest="loglevel", action="store_const", const=logging.INFO
  )
  parser.add_argument(
    "-d", "--debug", dest="loglevel", action="store_const", const=logging.DEBUG
  )
  parser.add_argument("-l", "--log", dest="logfile", action="store")
  parser.add_argument(
    "paths", nargs="+", help="paths to be operated on; may include wildcards"
  )
  parser.set_defaults(loglevel=logging.WARN)

  inifile = pathlib.Path(sys.argv[0]).with_suffix(".ini")
  print(inifile, sys.argv)
  if inifile.exists():
    sys.argv.insert(1, f"@{inifile}")
  print(inifile, sys.argv)

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
    for gd in args.paths
    for d in glob.iglob(gd)
    if pathlib.Path(d).is_file()
  ]
  if len(ig) == 0:
    log.warning(f"No paths matching {args.dirs}, skipping.")
  else:
    for d in ig:
      episodify(d)
