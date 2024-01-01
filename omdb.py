#!/usr/bin/python

import argparse
import json

from urllib.request import urlopen
from urllib.parse import urlunparse, urlencode

prog = "OMDB"
version = "0.1"
author = "Carl Edman (CarlEdman@gmail.com)"

parser = argparse.ArgumentParser(description="Request IMDB data through OMDB API.")
parser.add_argument("--version", action="version", version="%(prog)s " + version)
# parser.add_argument('-v','--verbose',dest='loglevel',action='store_const', const=logging.INFO)
# parser.add_argument('-d','--debug',dest='loglevel',action='store_const', const=logging.DEBUG)
# parser.set_defaults(loglevel=logging.WARN)
parser.add_argument("title", nargs="?", type=str, default=None, help="show name")
parser.add_argument("--season", "-s", type=int, help="show season")
parser.add_argument("--episode", "-e", type=int, help="show episode")
parser.add_argument("--year", "-y", type=int, help="show year")
parser.add_argument(
    "--type", "-t", type=str, choices=["movie", "series", "episode"], help="show type"
)
parser.add_argument("--imdbid", "-i", type=str, help="IMDB ID")
args = parser.parse_args()

print(args)

q = {"plot": "full", "tomatoes": "true", "r": "json"}

if args.title:
    q["t"] = args.title
if args.imdbid:
    q["i"] = args.imdbid
if args.year:
    q["y"] = str(args.year)
if args.season:
    q["Season"] = str(args.season)
if args.episode:
    q["Episode"] = str(args.episode)
if args.type:
    q["type"] = args.type
elif args.episode:
    q["type"] = "episode"
elif args.season:
    q["type"] = "series"

u = urlunparse(["http", "www.omdbapi.com", "/", "", urlencode(q), ""])
with urlopen(u) as f:
    j = {k: v for k, v in json.loads(f.read().decode("utf-8")).items() if v != "N/A"}
    print(f.getcode())

print(json.dumps(j, sort_keys=True, indent=2))
