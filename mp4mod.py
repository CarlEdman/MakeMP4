#!/usr/bin/python3

import argparse
import glob
import logging
import os
import os.path
import re
import subprocess

from cetools import *  # noqa: F403

prog = "MP4mod"
version = "0.3"
author = "Carl Edman (CarlEdman@gmail.com)"
desc = "Import, Export, and Swap MP4Meta Data."

parser = None
args = None
log = logging.getLogger()

tags = [
  ("-A", r"\s*Album:\s*(.+)"),  # -album       STR  Set the album title
  ("-a", r"\s*Artist:\s*(.+)"),  # -artist      STR  Set the artist information
  ("-b", r"\s*BPM:\s*(\d+)"),  # -tempo       NUM  Set the tempo (beats per minute)
  ("-c", r"\s*Comments:\s*(.+)"),  # -comment     STR  Set a general comment
  ("-C", r"\s*Copyright:\s*(.+)"),  # -copyright   STR  Set the copyright information
  ("-d", r"\s*Disk:\s*(\d+)\s*of\s*\d+"),  # -disk        NUM  Set the disk number
  ("-D", r"\s*Disk:\s*\d+\s*of\s*(\d+)"),  # -disks       NUM  Set the number of disks
  (
    "-e",
    r"\s*Encoded by:\s*(.+)",
  ),  # -encodedby   STR  Set the name of the person or company who encoded the file "
  (
    "-E",
    r"\s*Encoded with:\s*(.+)",
  ),  # , -tool        STR  Set the software used for encoding
  ("-g", r"\s*Genre:\s*(.+)"),  # -genre       STR  Set the genre name
  ("-G", r"\s*Grouping:\s*(.+)"),  # -grouping    STR  Set the grouping name
  ("-H", r"\s*HD Video:\s*(yes|no)"),  # -hdvideo     NUM  Set the HD flag (1\0)
  (
    "-i",
    r"\s*Media Type:\s*(.+)",
  ),  # -type        STR  Set the Media Type(tvshow, movie, music, ...)
  ("-I", r"\s*Content ID:\s*(\d+)"),  # -contentid   NUM  Set the content ID
  (
    "-j",
    r"\s*GenreType:\s*(\d+),\s*.+",
  ),  # -genreid     NUM  Set the genre ID # : 58, Comedy
  ("-l", r"\s*Long Description:\s*(.+)"),  # -longdesc    STR  Set the long description
  ("-l", r"\s*Description:\s*(.+)"),  # -longdesc    STR  Set the long description
  # ('-L', r'Lyrics:\s*(.+)'), # -lyrics      NUM  Set the lyrics # multiline
  (
    "-m",
    r"\s*Short Description:\s*(.{1,250}).*",
  ),  # -description STR  Set the short description
  (
    "-m",
    r"\s*Description:\s*(.{1,250}).*",
  ),  # -description STR  Set the short description
  ("-M", r"\s*TV Episode:\s*(\d+)"),  # -episode     NUM  Set the episode number
  ("-n", r"\s*TV Season:\s*(\d+)"),  # -season      NUM  Set the season number
  ("-N", r"\s*TV Network:\s*(.+)"),  # -network     STR  Set the TV network
  ("-o", r"\s*TV Episode Number:\s*(.+)"),  # -episodeid   STR  Set the TV episode ID
  ("-O", r"\s*Category:\s*(.+)"),  # -category    STR  Set the category
  ("-p", r"\s*Playlist ID:\s*(\d+)"),  # -playlistid  NUM  Set the playlist ID
  ("-B", r"\s*Podcast:\s*(\d+)"),  # -podcast     NUM  Set the podcast flag.
  ("-R", r"\s*Album Artist:\s*(.+)"),  # -albumartist STR  Set the album artist
  ("-s", r"\s*Name:\s*(.+)"),  # -song        STR  Set the song title
  ("-S", r"\s*TV Show:\s*(.+)"),  # -show        STR  Set the TV show
  ("-t", r"\s*Track:\s*(\d+)\s*of\s*\d+"),  # -track       NUM  Set the track number
  ("-T", r"\s*Track:\s*\d*\s*of\s*(\d+)"),  # -tracks      NUM  Set the number of tracks
  (
    "-x",
    r"\s*xid:\s*(.+)",
  ),  # -xid         STR  Set the globally-unique xid (vendor:scheme:id)
  # ('-X', r'\s*Content Rating:\s*(.+)'), # -rating      STR  Set the Rating(none, clean, explicit) # : UNDEFINED(255)
  ("-w", r"\s*Composer:\s*(.+)"),  # -writer      STR  Set the composer information
  ("-y", r"\s*Release Date:\s*(\d+)"),  # -year        NUM  Set the release date
  ("-z", r"\s*Artist ID:\s*(\d+)"),  # -artistid    NUM  Set the artist ID
  ("-Z", r"\s*Composer ID:\s*(\d+)"),  # -composerid  NUM  Set the composer ID
  # Sort Artist: Reynolds, Alastair
  # Sort Composer: Lee, John
  # Sort Album
  # Sort Name
  # Sort Album Artist
  # Part of Compilation: (yes|no)
  # Part of Gapless Album: (yes|no)
  # Keywords:
  # iTunes Account: %s
  # Purchase Date: %s
  # iTunes Store Country: %s
]

media_t2n = {
  "oldmovie": "Movie",
  "normal": "Normal",
  "audiobook": "Audio Book",
  "musicvideo": "Music Video",
  "movie": "Movie",
  "tvshow": "TV Show",
  "booklet": "Booklet",
  "ringtone": "Ringtone",
}
media_n2t = dict_inverse(media_t2n)


def mp4_valid(f):
  valid_exts = [".mp4", ".m4a", ".m4b", ".m4v"]
  if not os.path.exists(f):
    log.error('file "' + f + '" does not exist')
    exit(-1)
  b, e = os.path.splitext(f)
  if e not in valid_exts:
    log.error(
      'file "'
      + f
      + '" does not have valid mp4 extension ('
      + ",".join(valid_exts)
      + ")"
    )
    exit(-1)
  return (b, e)


def mp4meta_export(f):
  b, e = mp4_valid(f)
  t = b + ".txt"
  if os.path.exists(t):
    if not args.force:
      log.error(
        'cannot export metadata from "' + f + '" because "' + t + '" already exists'
      )
      exit(-1)
    os.remove(t)
  cs = reglob(re.escape(b) + r"(\.cover)?(\.art\[\d+\])?\.(jpg|png|gif|bmp)")
  if cs:
    if not args.force:
      log.error(
        'cannot export metadata from "'
        + f
        + '" because "'
        + '","'.join(cs)
        + '" already exist(s)'
      )
      exit(-1)
    for c in cs:
      os.remove(c)
  subprocess.check_call(
    ["mp4info", f], stdout=open(t, "wt", encoding="utf-8", errors="replace")
  )
  subprocess.check_output(["mp4art", "--extract", f])


def mp4meta_import(f):
  b, e = mp4_valid(f)
  if args.loglevel <= logging.DEBUG:
    log.debug(
      "Before import info:\n"
      + subprocess.check_output(["mp4info", f]).decode(
        encoding="utf-8", errors="replace"
      )
    )
  t = b + ".txt"
  if not os.path.exists(t):
    log.error(
      'cannot extract metadata from "' + f + '" because "' + t + '" does not exist'
    )
    exit(-1)
  ts = []
  with open(t, "rt", encoding="utf-8", errors="replace") as td:
    for line in td:
      line = line.rstrip()
      if re.fullmatch(r"mp4info version.*", line):
        continue
      if re.fullmatch(re.escape(f) + ":", line):
        continue
      if re.fullmatch(r"Track\s+Type\s+Info\s*", line):
        continue
      if re.fullmatch(r"\d+\s+(video|audio|subp|text).*", line):
        continue
      if re.fullmatch(r"\s*", line):
        continue
      if re.fullmatch(r"\s*Cover Art pieces:\s*\d+", line):
        continue
      foundit = False
      for arg, pat in tags:
        if m := re.fullmatch(pat, line):
          foundit = True
          ts.append(arg)
          if arg[1] in "i":
            ts.append(media_n2t[m[1]])
          elif arg[1] in "HB":
            ts.append("1" if m[0] == "yes" else "0")
          else:
            ts.append(m[1])
      if foundit:
        continue
      log.warning('Could not interpret "' + line + '" for "' + f + '"')

  ak = [k[1:] for k, _ in tags if k[0] == "-"]
  subprocess.check_output(["mp4tags", "--remove", "".join(ak), f])
  if args.loglevel <= logging.DEBUG:
    log.debug(
      "After tags remove info:\n"
      + subprocess.check_output(["mp4info", f]).decode(encoding="cp1252")
    )
  if ts:
    subprocess.check_output(["mp4tags"] + ts + [f])
  if not args.nocleanup:
    os.remove(t)

  subprocess.call(["mp4art", "--art-any", "--remove", f])
  if args.loglevel <= logging.DEBUG:
    log.debug(
      "After art remove info:\n"
      + subprocess.check_output(["mp4info", f]).decode(encoding="cp1252")
    )
  cs = reglob(re.escape(b) + r"(\.cover)?(\.art\[\d+\])?\.(jpg|png|gif|bmp)")
  if cs:
    call = ["mp4art"]
    if not args.nooptimize:
      call.append("--optimize")
    for c in cs:
      call += ["--add", c]
    call += [f]
    subprocess.check_output(call)
    if not args.nocleanup:
      for c in cs:
        os.remove(c)
  else:
    if not args.nooptimize:
      subprocess.check_output(["mp4file", "--optimize", f])
  if args.loglevel <= logging.DEBUG:
    log.debug(
      "Final info:\n"
      + subprocess.check_output(["mp4info", f]).decode(encoding="cp1252")
    )


def mp4meta_swap(f1, f2):
  mp4meta_export(f1)
  mp4meta_export(f2)
  os.rename(f1, "temp")
  os.rename(f2, f1)
  os.rename("temp", f2)
  mp4meta_import(f1)
  mp4meta_import(f2)


if __name__ == "__main__":
  ops = ["export", "import", "swap"]

  parser = argparse.ArgumentParser(
    description="Export, import, and swap mp4 meta data."
  )
  parser.add_argument("--version", action="version", version="%(prog)s " + version)
  parser.add_argument("operation", choices=ops, help="operation to be performed")
  parser.add_argument("files", nargs="+", help="files to be operated on")
  parser.add_argument(
    "-f",
    "--force",
    dest="force",
    action="store_true",
    help="overwrite existing metadata and image files",
  )
  parser.add_argument(
    "-o",
    "--no-optimize",
    dest="nooptimize",
    action="store_true",
    help="optimize mp4 file after operation",
  )
  parser.add_argument(
    "-c",
    "--no-cleanup",
    dest="nocleanup",
    action="store_true",
    help="remove imported tag and image files",
  )
  parser.add_argument(
    "-v", "--verbose", dest="loglevel", action="store_const", const=logging.INFO
  )
  parser.add_argument(
    "-d", "--debug", dest="loglevel", action="store_const", const=logging.DEBUG
  )
  parser.set_defaults(loglevel=logging.WARN)
  parser.add_argument("-l", "--log", dest="logfile", action="store")
  args = parser.parse_args()
  logging.basicConfig(
    level=args.loglevel,
    filename=args.logfile,
    format="%(asctime)s [%(levelname)s]: %(message)s",
  )

  if args.operation == "export":
    for g in args.files:
      fs = glob.glob(g)
      if len(fs) == 0:
        log.error(f'"{g}" does not match any files')
      for f in fs:
        mp4meta_export(f)
  elif args.operation == "import":
    for g in args.files:
      fs = glob.glob(g)
      if len(fs) == 0:
        log.error(f'"{g}" does not match any files')
      for f in fs:
        mp4meta_import(f)
  elif args.operation == "swap":
    if len(args.files) != 2:
      log.error("swap operation requires exactly two arguments")
    mp4meta_swap(args.files[0], args.files[1])
  else:
    log.error("unknown operation {args.operation}")
