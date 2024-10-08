#!/usr/bin/python3

import argparse
import collections
# import enzyme
import glob
import json
import logging
import mutagen
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
import xml.sax.saxutils as saxutils

from mutagen.mp4 import MP4, MP4Cover
from sanitize_filename import sanitize
from urllib.error import HTTPError
from urllib.parse import urlunparse, urlencode
from urllib.request import urlopen

from cetools import (
  add_to_list,
  alphabetize,
  defdict,
  dict_inverse,
  export,
  reglob,
  unparse_time,
  )

prog = "TagMP4"
version = "0.4"
author = "Carl Edman (CarlEdman@gmail.com)"
desc = """Update Metadata in MP4 files based on filenames and external sources"""

parser = None
args = None
log = logging.getLogger()

type2stik = {
  "music": 1,
  "audiobook": 2,
  "musicvideo": 6,
  "movie": 9,
  "tvshow": 10,
  "booklet": 11,
  "ringtone": 14,
}
stik2type = dict_inverse(type2stik)

rating2rtng = {}
rtng2rating = dict_inverse(rating2rtng)


def toint(s):
  if isinstance(s, int):
    return s
  if isinstance(s, str):
    try:
      return int(s)
    except ValueError:
      pass
  return None


def get_meta_local_tv(episode, ls):
  its = defdict()

  if not toint(episode):
    return its

  header = ls.pop(0).split("\t")

  header_norm = {
    "Total": "Series Episode",
    "Series number": "Series Episode",
    "Nº": "Series Episode",
    "No. overall": "Series Episode",
    "#": "Episode",
    "No.": "Episode",
    "No. in season": "Episode",
    "No. in Season": "Episode",
    "Episode number": "Episode",
    "Ep": "Episode",
    "Ep.": "Episode",
    "No. in series": "Episode",
    "No. in Series": "Episode",
    "Episode title": "Title",
    "Episode name": "Title",
    "Episode Title": "Title",
    "Episode Name": "Title",
    "Written by": "Writer",
    "Original Released": "Released",
    "Original air date": "Released",
    "Original airdate": "Released",
    "Original release date": "Released",
    "Release date": "Released",
    "Aired on": "Released",
    "Recorded on": "Released",
    "Released on": "Released",
    "Prod. code": "Production Code",
    "prod. code": "Production Code",
    "Prod.code": "Production Code",
    "PC": "Production Code",
    "Production number": "Production Code",
    "Directed by": "Director",
  }

  header = [header_norm[h] if h in header_norm else h for h in header]

  if "Episode" not in header:
    log.warning("TV series file contains no Episode header.")
    return its

  cur = dict()
  ld = dict()
  for l1 in ls:
    ds = l1.split("\t")
    if len(ds) == len(header):
      cur = {k: v for k, v in zip(header, ds)}
      if "Episode" in cur:
        ld[int(cur["Episode"])] = cur
        del cur["Episode"]
    elif cur:
      cur["Description"] = f'{cur["Description"]}  {l1}' if "Description" in cur else l1
    else:
      log.warning("TV series file does not start with a valid data line.")
      return its

  if episode not in ld:
    log.warning(f"TV series file does not contain episode {episode}.")
    return its

  for k, v in ld[episode].items():
    v = v.lstrip(".").strip()
    if v.startswith('"') and v.endswith('"'):
      v = v[1:-1]
    if k == "Title":
      its["song"] = v
    elif k == "Writer":
      its["writer"] = v
    elif k == "Production Code":
      its["episodeid"] = v
    elif k == "Released" and (m := re.search(r"\b([12]\d\d\d)\b", v)):
      its["year"] = int(m[0])
    elif k == "Description":
      its["description"] = v
    else:
      its["comment"] = add_to_list(its["comment"], f"{k}: {v}")

  return its


def get_meta_local_movie(ls):
  its = defdict()

  beg_trans = {
    "Cast": "Actors",
    "Director": "Director",
    "Availability": "Availability",
    "Language": "Language",
    "Format": "Format",
    "Moods": "Moods",
  }

  genre_trans = {
    "Musicals": "Musical",
    "Animes": "Anime",
    "Operas": "Opera",
    "Westerns": "Western",
    "Classics": "Classics",
    "Thrillers": "Thriller",
    "Cartoons": "Animation",
    "Period Pieces": "History",
    "Dramas": "Drama",
    "Musical": "Musical",
    "Anime": "Anime",
    "Opera": "Opera",
    "Western": "Western",
    "Classic": "Classics",
    "Thriller": "Thriller",
    "Cartoon": "Animation",
    "Period Piece": "History",
    "Drama": "Drama",
    "Sci-Fi": "Science Fiction",
    "Fantasy": "Fantasy",
    "Horror": "Horror",
    "Documentary": "Documentary",
    "Documentaries": "Documentary",
    "Superhero": "Superhero",
    "Comedy": "Comedy",
    "Comedies": "Comedy",
    "Crime": "Crime",
    "Romantic": "Romance",
    "Animation": "Animation",
    "Action": "Action",
    "Adventure": "Adventure",
  }

  its["comment"] = list()
  for l1 in ls:
    if m := re.fullmatch(
      r"(?P<year>[12]\d\d\d)\s*(?P<rating>G|PG-13|PG|R|NC-17|UR|NR|TV-14|TV-MA)\s*(?:(?P<hours>\d+)h)?\s*(?:(?P<minutes>\d+)m)?\s*(?P<format>.*)",
      l1,
    ):
      its["year"] = int(m.group("year"))
      its["rating"] = m.group("rating")
      its["duration"] = (3600 * float(m.group("hours")) if m.group("hours") else 0) + (
        60 * float(m.group("minutes")) if m.group("minutes") else 0
      )
      if m.group("format"):
        its["comment"] = add_to_list(its["comment"], f'Format: {m.group("format")}')
    elif m := re.fullmatch(r"This movie is\s.*", l1):
      its["description"] += l1
    elif m := re.fullmatch(r"Genres?\s*:*\s*(.*)", l1):
      genres = [
        genre_trans[w.strip()] for w in m[1].split(",") if w.strip() in genre_trans
      ]
      if genres:
        its["genre"] = genres[0]
      else:
        its["genre"] = m[1]
    elif m := re.fullmatch(r"Writers?\s*:*\s*(.*)", l1):
      if "writer" in its:
        its["writer"] += f";{m[1]}"
      else:
        its["writer"] = m[1]
    elif (m := re.fullmatch(r"(\S*)\s*:*\s*(.*)", l1)) and m[1] in beg_trans:
      its["comment"] = add_to_list(its["comment"], f"{beg_trans[m[1]]}: {m[2]}")
    elif "description" in its:
      its["description"] += f"  {l1}"
    elif "title" in its:
      its["description"] = l1
    else:
      its["title"] = l1

  return its


@export
def get_meta_local(title, year, season, episode, descpath):
  try:
    with open(descpath, "rt", encoding="utf-8") as f:
      ls = []
      for l1 in f:
        l1 = re.sub(r"\[(\d+|[a-z])\]", "", l1)  # Strip footnotes
        l1 = re.sub(r"\s+-+\s+", r"—", l1)  # insert proper em-dashes
        l1 = re.sub(r"Add to Google Calendar", "", l1)  # Google calendar links
        l1 = re.sub(r"[\u200A]", "", l1)  # Remove hair space, ...
        l1 = l1.strip()  # Strip leading and trailing whitespace
        if l1 == "":
          continue
        if re.fullmatch(r"^(Rate [12345] stars)+(Rate not interested)?(Clear)?", l1):
          continue
        if re.fullmatch(r"[0-4]\.[0-9]|5\.0", l1):
          continue
        if re.fullmatch(r"Movie Details", l1):
          continue
        if re.fullmatch(r"Overview\s*Details(\s*Series)?", l1):
          continue
        if re.fullmatch(r"At Home", l1):
          continue
        if re.fullmatch(r"In Queue", l1):
          continue
        ls.append(l1)
  except OSError:
    ls = []

  if not ls:
    return defdict()
  return get_meta_local_tv(episode, ls) if season else get_meta_local_movie(ls)


@export
def get_meta_imdb(
  title, year, season, episode, artpath, imdb_id, omdb_status, omdb_key
):
  LOG_YEAR_GUESS_WARNING = (
    None  # "Guessing IMDB series year by subtracing one for every\
  )
  # season year above 1; if this fails --ignore-year-imdb"
  its = defdict()
  if not omdb_key:
    return its
  if omdb_status and (200 <= omdb_status < 300 or 400 <= omdb_status < 500):
    return its

  q = {"plot": "full", "apikey": omdb_key}
  if imdb_id:
    q.update({"i": imdb_id})
  elif season:
    q.update({"t": title, "type": "series", "Season": str(season)})
    if year:
      if LOG_YEAR_GUESS_WARNING is not None:
        log.warning(LOG_YEAR_GUESS_WARNING)
      q["y"] = (str(year - season + 1),)
    if episode:
      q.update({"type": "episode", "Episode": str(episode)})
  else:
    q.update({"t": title, "y": str(year), "type": "movie"})

  u = urlunparse(["http", "www.omdbapi.com", "/", "", urlencode(q), ""])
  try:
    with urlopen(u) as f:
      its["omdb_status"] = f.getcode()
      j = json.loads(f.read().decode("utf-8"))
  except HTTPError as e:
    its["omdb_status"] = e.code
    j = None

  if not j:
    return

  genre_trans = {
    "Animation": "CGI",
    "Musical": "Musical",
    "Documentary": "Documentary",
    "Romance": "Romance",
    "Horror": "Horror",
    "Sci-Fi": "Science Fiction",
    "Fantasy": "Fantasy",
    "Western": "Western",
    "Mystery": "Mystery",
    "Crime": "Crime",
    "Family": "Children",
    "Adventure": "Adventure",
    "Action": "Action",
    "Thriller": "Thriller",
    "War": "History",
    "History": "History",
    "Biography": "History",
    "Drama": "Drama",
    "Music": "Opera",
    "Sitcom": "Comedy",
    "Comedy": "Comedy",
    "Film-Noir": "Thriller",
    "Game-Show": "Reality",
    "News": "Reality",
    "Reality-TV": "Reality",
    "Sport": "Reality",
    "Talk-Show": "Reality",
  }

  int_trans = {
    "Year": "year",
    "Episode": "episode",
    "Season": "season",
    "totalSeasons": "totalSeasons",
  }

  str_trans = {
    "Director": "director",
    "Writer": "writer",
    "Production": "network",
    "imdbID": "imdb_id",
    "seriesID": "imdb_series_id",
    "Rated": "rating",
  }

  desc_trans = {"Plot": ""}

  comment_trans = {
    "Country": "Country: ",
    "DVD": "DVD Release: ",
    "Awards": "Awards: ",
    "BoxOffice": "Boxoffice: ",
    "Language": "Language: ",
    "Metascore": "Metascore: ",
    "Rated": "Rating: ",
    "Released": "Released: ",
    "Runtime": "Runtime: ",  # To duration?
    "Website": "Web Site: ",
    "totalSeasons": "Total Seasons: ",
    "Actors": "Actors: ",
  }

  skip_trans = {"", "Episodes", "Response", "imdbRating", "imdbVotes", "Poster"}

  description = list()
  its["comment"] = list()

  for k, v in j.items():
    if v == "N/A":
      continue
    elif k == "Error":
      log.warning(f'{title}: IMDB Error "{v}"')
    elif k == "Type":  # "movie" or "episode"
      its["type"] = "movie" if v == "movie" else "tvshow"
    elif k == "Title":
      if season and episode:
        if v == f"Episode #{season}.{episode}":
          continue
      its["song"] = v
    elif k == "Genre":
      genres = set(
        genre_trans[w.strip()] for w in v.split(",") if w.strip() in genre_trans
      )
      if len(genres) > 0:
        its["genre"] = genres.pop()
        if len(genres) > 1:
          log.warning(
            f'{title}: Too many genres recognized in IMDB "{",".join(genres)}"'
          )
      else:
        log.warning(f'{title}: No genres recognized in IMDB "{v}"')
    elif k in skip_trans:
      pass
    elif k in int_trans:
      its[int_trans[k]] = int(v)
    elif k in str_trans:
      its[str_trans[k]] = str(v)
    elif k in desc_trans:
      if (d := desc_trans[k] + re.sub(r"\s+-+\s+", r"—", v)) in description:
        continue
      if desc_trans[k]:
        description.append(d)
      else:
        description.insert(0, d)
    elif k in comment_trans:
      its["comment"] = add_to_list(its["comment"], comment_trans[k] + v.rstrip("."))
    elif k == "Ratings":
      for r in v:
        its["comment"] = add_to_list(
          its["comment"], f'{r["Source"]} Rating: {r["Value"]}'
        )
    elif k == "Poster":
      pass  # imdb_poster = v
    else:
      log.warning(f'{title}: Unrecognized IMDB "{k}" = "{v}"')

  its["description"] = ".  ".join(d.rstrip(" .") for d in description)

  if not artpath or os.path.exists(artpath):
    return its

  if "Poster" in j:
    u = j["Poster"]
  elif "imdb_id" in its:
    q = {"h": "1000", "i": its["imdb_id"], "apikey": omdb_key}
    u = urlunparse(["http", "img.omdbapi.com", "/", "", urlencode(q), ""])
  else:
    return its

  try:
    with urlopen(u) as f, open(artpath, "wb") as g:
      its["omdb_status"] = f.getcode()
      shutil.copyfileobj(f, g)
  except HTTPError as e:
    its["omdb_status"] = e.code
  except ValueError:
    its["omdb_status"] = 400

  return its


@export
def get_meta_mp4info(f):
  its = defdict()

  compproc = subprocess.run(["mp4info", f], text=True, capture_output=True)
  if not isinstance(compproc.stdout, str):
    log.warning(f'mp4info "{f}" produced no output.')
    return its
  for l1 in compproc.stdout.splitlines():
    if m := re.fullmatch(r"\s+(.+?)\s*:\s*(.+?)\s*", l1):
      its[m[1]] = m[2]
    elif m := re.fullmatch(r"(\d+)\s+(\w+)\s*(.*)", l1):
      its["TrackType" + m[1]] = m[2]
      its["TrackInfo" + m[1]] = m[3]
    elif re.fullmatch("mp4info version .*", l1):
      continue
    elif re.fullmatch(re.escape(f) + ":", l1):
      continue
    elif re.fullmatch("Track\s+Type\s+Info", l1):
      continue
    else:
      log.warning(f'mp4info "{f}" has invalid line "{l1}"')

  return its


@export
def get_meta_mutagen(f):
  its = defdict()

  mutmp4 = MP4(f)
  if not mutmp4.tags:
    return its
  t = mutmp4.tags

  mp2its = {
    "©too": "tool",
    "©gen": "genre",
    "©cmt": "comment",
    "tvsn": "season",
    "tves": "episode",
    "tven": "episodeid",
    "©ART": "artist",
    "©wrt": "writer",
    "tvnn": "network",
    "©day": "year",
    "desc": "description",
    "ldes": "description",
    "©nam": "name",
    "tvsh": "show",
    "song": "song",
  }

  for k, v in mp2its.items():
    if k in t and t[k]:
      w = ";".join(str(x) for x in t[k])
      try:
        its[v] = int(w)
      except ValueError:
        if v not in its or len(w) > len(its[v]):
          its[v] = w

  if "hdvd" in t and t["hdvd"]:
    its["hdvideo"] = True
  if "stik" in t and (w := t["stik"]):
    its["type"] = ";".join(stik2type[x] for x in w if x in stik2type)
  if "rtng" in t and (w := t["rtng"]):
    its["rating"] = ";".join(rtng2rating[x] for x in w if x in rtng2rating)

  return its


@export
def get_meta_enzyme(f):
  its = defdict()
  # with open(f, "rb") as file:
  #   mkv = enzyme.MKV(file)

  return its


@export
def get_meta_filename(f):
  its = defdict()

  filename = os.path.split(f)[1]
  name = os.path.splitext(filename)[0]

  if m := re.fullmatch(r"(.*\s)\(([12]\d\d\d)?\)(\s.*)?", name):
    its["type"] = "movie"
    its["title"] = m[1].strip()
    if m[2]:
      its["year"] = m[2]
    if m[3]:
      its["song"] = m[3].strip()
    return its

  if m := re.fullmatch(r"(.*\s)S0*([1-9]\d*)(E\d+)?(\s.*)?", name):
    its["type"] = "tvshow"
    its["show"] = m[1].strip()
    its["season"] = int(m[2])
    if m[3]:
      its["episode"] = int(m[3][1:])
    if m[4]:
      its["song"] = m[4].strip()
    return its

  return None


@export
def set_meta_mutagen(outfile, its):
  mutmp4 = MP4(outfile)
  if not mutmp4.tags:
    mutmp4.add_tags()
  t = mutmp4.tags

  if p := its["tool"]:
    t["©too"] = [p]
  else:
    log.warning(f'"{outfile}" has no tool')
  if (p := its["type"]) in type2stik:
    t["stik"] = [type2stik[p]]
  else:
    log.warning(f'"{outfile}" has no type')
  if p := its["genre"]:
    t["©gen"] = p.split(";")
  else:
    log.warning(f'"{outfile}" has no genre')
  if p := toint(its["year"]):
    t["©day"] = [str(p)]
  else:
    log.warning(f'"{outfile}" has no year')
  if p := toint(its["season"]):
    t["tvsn"] = [p]
  if p := toint(its["episode"]):
    t["tves"] = [p]
  if p := its["episodeid"]:
    t["tven"] = [p]
  if p := its["artist"]:
    t["©ART"] = [p]
  if p := its["writer"]:
    t["©wrt"] = [p]
  if p := its["network"]:
    t["tvnn"] = [p]
  if its["hdvideo"]:
    t["hdvd"] = [1]
  if its["comment"]:
    t["©cmt"] = ";".join(its["comment"])

  rating2rtng = {}
  if p := its["rating"]:
    t["rtng"] = [rating2rtng[q] for q in p.split(";") if q in rating2rtng]

  if p := its["description"]:
    t["desc"] = [p[:255]]
    if len(p) > 255:
      t["ldes"] = [p]
  else:
    log.warning(f'"{outfile}" has no description')

  title = its["title"] or its["show"]
  t["tvsh"] = [title]
  song = its["song"]

  if its["type"] == "tvshow" and song:
    t["©nam"] = [song]
  elif title and song:
    t["©nam"] = [f"{title}: {song}"]
  elif title:
    t["©nam"] = [title]
  elif song:
    t["©nam"] = [song]

  ext2format = {
    ".jpg": MP4Cover.FORMAT_JPEG,
    ".jpeg": MP4Cover.FORMAT_JPEG,
    ".png": MP4Cover.FORMAT_PNG,
  }
  if ca := its["coverart"]:
    t["covr"] = []
    for fn in ca if isinstance(ca, list) else ca.split(";"):
      ext = os.path.splitext(fn)[1].casefold()
      if ext in ext2format:
        with open(fn, "rb") as f:
          t["covr"].append(MP4Cover(f.read(), ext2format[ext]))
      else:
        log.warning(f'Cover "{fn}" for {outfile}" has invalid extension')
  else:
    log.warning(f'"{outfile}" has no cover art')

  try:
    mutmp4.save()
  except mutagen.MutagenError:
    log.error(f'Saving "{outfile}" metadata with mutagen failed.')


@export
def set_chapters_mutagen(outfile, its):
  cts = its["chapter_time"]
  if not cts:
    return
  elif isinstance(cts, list):
    pass
  elif isinstance(cts, float):
    cts = [cts]
  else:
    return

  cns = its["chapter_name"]
  if isinstance(cns, list):
    pass
  elif isinstance(cns, str):
    cns = cns.split(";")
  else:
    return

  # MP4Chapters(Chapter(start, title) for (start,title) in zip (cts, cns))
  log.warning(f'Chapter import for "{outfile}" not yet supported.')


@export
def set_meta_cmd(outfile, its):
  call = ["mp4tags", outfile]

  if p := its["tool"]:
    call += ["-tool", p]
  else:
    log.warning(f'"{outfile}" has no tool')

  if p := its["type"]:
    call += ["-type", p]
  else:
    log.warning(f'"{outfile}" has no type')

  if p := its["genre"]:
    call += ["-genre", p]
  else:
    log.warning(f'"{outfile}" has no genre')

  if p := toint(its["year"]):
    call += ["-year", str(p)]
  else:
    log.warning(f'"{outfile}" has no year')

  if p := its["comment"]:
    call += ["-comment", ";".join(p)]
  if p := toint(its["season"]):
    call += ["-season", str(p)]
  if p := toint(its["episode"]):
    call += ["-episode", str(p)]
  if p := its["episodeid"]:
    call += ["-episodeid", p]
  if p := its["artist"]:
    call += ["-artist", p]
  if p := its["writer"]:
    call += ["-writer", p]
  if p := its["network"]:
    call += ["-network", p]
  # if (p := its['rating']): call += [ '-rating' , p ]
  if its["hdvideo"]:
    call += ["-hdvideo", "1"]
  if p := its["description"]:
    call += ["-desc", p[:255]]
    if len(p) > 255:
      call += ["-longdesc", p]
  else:
    log.warning(f'"{outfile}" has no description')

  if not (title := its["title"]):
    title = None
  if not (song := its["song"]):
    song = None
  if not (show := its["show"]):
    show = None

  if title:
    call += ["-show", title]
  elif show:
    call += ["-show", show]

  if its["type"] == "tvshow" and song:
    call += ["-song", song]
  elif title and song:
    call += ["-song", f"{title}: {song}"]
  elif title:
    call += ["-song", title]
  elif song:
    call += ["-song", song]

  try:
    subprocess.run(call, check=True, capture_output=True)
  except subprocess.CalledProcessError as cpe:
    with open(outfile, "w") as f:
      f.truncate(0)
    log.error(
      f"Error code for {cpe.cmd}: {cpe.returncode} : {cpe.stdout} : {cpe.stderr}"
    )

  if ca := its["coverart"]:
    call = ["mp4art", outfile]
    for i in ca if isinstance(ca, list) else ca.split(";"):
      call += ["--add", i]
    call += [outfile]
    try:
      subprocess.run(call, check=True, capture_output=True)
    except subprocess.CalledProcessError as cpe:
      with open(outfile, "w") as f:
        f.truncate(0)
      log.error(
        f"Error code for {cpe.cmd}: {cpe.returncode} : {cpe.stdout} : {cpe.stderr}"
      )
  else:
    log.warning(f'"{outfile}" has no cover art')


@export
def set_chapters_cmd(outfile, its):
  tmpfile = tempfile.mktemp(suffix=".mp4", prefix="tmp")
  tmpchapterfile = os.path.splitext(tmpfile)[0] + ".chapters.txt"

  if os.path.exists(chapterfile := os.path.splitext(outfile)[0] + ".chapters.txt"):
    log.info(f'Adding chapters from existing config file "{chapterfile}"')
    shutil.copyfile(chapterfile, tmpchapterfile)
  elif chap := its["chapters"]:
    delay = chap["delay"] or 0.0
    elong = chap["elongation"] or 1.0
    with open(tmpchapterfile, "wt", encoding="utf-8") as f:
      for ct, cn in zip(chap["time"], chap["name"]):
        ct = ct * elong + delay
        if ct < 0:
          continue
        f.write(f"{unparse_time(ct)} {cn} ({int (ct/60.0):d}m {int (ct)%60:d}s)\n")
  else:
    return

  if os.path.getsize(tmpchapterfile) == 0:
    return

  try:
    os.rename(outfile, tmpfile)
    subprocess.run(["mp4chaps", "--import", tmpfile], check=True, capture_output=True)
  except subprocess.CalledProcessError as cpe:
    with open(outfile, "w") as f:
      f.truncate(0)
    log.error(
      f"Error code for {cpe.cmd}: {cpe.returncode} : {cpe.stdout} : {cpe.stderr}"
    )
  finally:
    os.remove(tmpchapterfile)
    os.rename(tmpfile, outfile)


@export
def set_meta_mkvxml(its):
  """Generate and return an xml corresponding to the metadata in the argument."""

  xmlprologue = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE Tags SYSTEM "matroskatags.dtd">
"""
  xml = ET.XML(
    xmlprologue
    + """
<Tags>
  <Tag>
  </Tag>
</Tags>
"""
  )
  tag = xml.find("Tag")

  def keyvaltoxml(key, val):
    return ET.fromstring(
      f"<Simple><Name>{saxutils.escape(key)}</Name><String>{saxutils.escape(val)}</String></Simple>\n"
    )

  comments = its["comment"]
  its["comment"] = None
  if isinstance(comments, str):
    comments = comments.split(";")
  if isinstance(comments, list):
    for c in comments:
      if ":" in c:
        k, v = c.split(":", 1)
      else:
        k, v = c, ""
      k = k.strip()
      v = v.strip()
      if k in its and its[k]:
        its[k] = its[k] + ", " + v
      else:
        its[k] = v

  beg = r"(?P<beg>.*)\b"
  end = r"(  |\.+|\Z)\s*(?P<end>.*)"
  if (d := its["description"]) and d:
    if m := re.fullmatch(beg + r"This movie is:\s+(?P<moods>[^.]*?)" + end, d):
      d = m.group("beg") + m.group("end")
      its["This movie is"] = m.group("moods")
    if m := re.fullmatch(beg + r"Format:\s+(?P<formats>[^.]*?)" + end, d):
      d = m.group("beg") + m.group("end")
      its["Format"] = m.group("formats")
    if m := re.fullmatch(
      beg + r"Our best guess for you: (?P<stars>[0-9.]+ stars)" + end, d
    ):
      d = m.group("beg") + m.group("end")
      its["Our best guess for you"] = m.group("stars")
    if m := re.fullmatch(
      beg + r"Average of (?P<count>\d+) ratings: (?P<stars>[0-9.]+ stars)" + end, d
    ):
      d = m.group("beg") + m.group("end")
      its[f'Average of {m.group("count")} ratings'] = f'{m.group("stars")}'
    if m := re.fullmatch(beg + r"Average rating: (?P<stars>[0-9.]+)" + end, d):
      d = m.group("beg") + m.group("end")
      its["Average rating"] = m.group("stars")
    if m := re.fullmatch(beg + r"Report a problem" + end, d):
      d = m.group("beg") + m.group("end")
    if m := re.fullmatch(beg + r"\+ Add to Queue" + end, d):
      d = m.group("beg") + m.group("end")
    if m := re.fullmatch(
      beg + r"(Blu-ray disc|DVD) shipped to you on (?P<date>[0-9/]+)" + end, d
    ):
      d = m.group("beg") + m.group("end")
      its["shipped"] = m.group("date")
    while m := re.fullmatch(beg + r"(Cast|Actors?):\s+(?P<actors>[^.]*?)" + end, d):
      d = m.group("beg") + m.group("end")
      if "Actors" in its and its["Actors"]:
        its["Actors"] += ", " + m.group("actors")
      else:
        its["Actors"] = m.group("actors")
    if m := re.fullmatch(beg + r"Director:\s+(?P<director>[^.]*?)" + end, d):
      d = m.group("beg") + m.group("end")
      its["Director"] = m.group("director")
    if m := re.fullmatch(beg + r"Genres?:\s+(?P<genres>[^.]*?)" + end, d):
      d = m.group("beg") + m.group("end")
      its["Genres"] = m.group("genres")
    its["description"] = d

  for key, val in its.items():
    val = str(val).strip()
    tag.append(keyvaltoxml(key, val))
    if len(val) < 50 and (sval := alphabetize(val)) != val:
      tag[-1][0].append(keyvaltoxml("SORT_WITH", sval))

  return xmlprologue + ET.canonicalize(
    ET.tostring(xml, encoding="unicode", xml_declaration=True)
  )


# COLLECTION
# SEASON
# MOVIE
# EPISODE
# TOTAL_PARTS Total number of parts defined at the first lower level. (e.g., if TargetType is ALBUM, the total number of tracks of an audio CD)
# PART_NUMBER Number of the current part of the current level. (e.g., if TargetType is TRACK, the track number of an audio CD)
# PART_OFFSET A number to add to PART_NUMBER, when the parts at that level don’t start at 1. (e.g., if TargetType is TRACK, the track number of the second audio CD)
# TITLE The title of this item. For example, for music you might label this “Canon in D”, or for video’s audio track you might use “English 5.1” This is akin to the “TIT2” tag in [@!ID3v2].
# SUBTITLE Sub Title of the entity.
# DIRECTOR
# ACTOR
# WRITTEN_BY
# SCREENPLAY_BY
# PUBLISHER
# GENRE
# CONTENT_TYPE The type of the item. e.g., Documentary, Feature Film, Cartoon, Music Video, Music, Sound FX, …
# DESCRIPTION A short description of the content, such as “Two birds flying.”
# KEYWORDS Keywords to the item separated by a comma, used for searching.
# SYNOPSIS A description of the story line of the item.
# LAW_RATING Depending on the COUNTRY it’s the format of the rating of a movie (P, R, X in the USA, an age in other countries or a URI defining a logo).
# DATE_RELEASED The time that the item was originally released. This is akin to the “TDRL” tag in [@!ID3v2].
# COMMENT Any comment related to the content.
# ENCODER The software or hardware used to encode this item. (“LAME” or “XviD”)
# IMDB Internet Movie Database [@!IMDb] identifier. “tt” followed by at least 7 digits for Movies, TV Shows, and Episodes.


@export
def make_filename(its):
  title = its["title"] or its["show"]
  title = alphabetize(title) if title else None
  if its["type"] == "movie":
    if i := toint(its["episode"]):
      episode = f"- pt{i:d}"
    else:
      episode = ""
    year = f" ({i:04d})" if (i := toint(its["year"])) else ""
    song = " " + alphabetize(i) if (i := its["song"]) else ""
    plexname = f'{title}{episode}{year}{song}.{args.output_type if args else "notype"}'
  elif its["type"] == "tvshow":
    season = toint(its["season"])
    episode = toint(its["episode"])
    if season and episode:
      seaepi = f" S{season:d}E{episode:02d}"
    elif season:
      seaepi = f" S{season:d}"
    elif episode:
      seaepi = f" S1E{episode:02d}"
    else:
      seaepi = ""
    song = " " + alphabetize(i) if (i := its["song"]) else ""
    plexname = f'{title}{seaepi}{song}.{args.output_type if args else "notype"}'
  else:
    return None
  return pathlib.Path(sanitize(plexname))


def retag(f):
  def upd(i):
    if not i:
      return
    for k, v in i.items():
      if not v:
        continue
      elif k == "comment":
        its["comment"] = add_to_list(its["comment"], v)
      else:
        its.setdefault(k, v)

  (dirname, filename) = os.path.split(f)
  ext = os.path.splitext(filename)[1]
  if ext not in {".mp4"}:
    log.warning(f"{f} has invalid extension, skipping.")
    return

  its = collections.defaultdict(lambda: None)
  upd(get_meta_filename(f))
  upd(get_meta_mutagen(f))

  title = its["title"] or its["show"] or its["base"]
  fn = f'{its["show"] or ""}{" S"+str(its["season"]) if its["season"] else ""}'

  if args.descdir:
    upd(
      get_meta_local(
        title,
        its["year"],
        its["season"],
        its["episode"],
        os.path.join(args.descdir, f"{fn}.txt"),
      )
    )

  if args.omdbkey and args.artdir:
    upd(
      get_meta_imdb(
        title,
        its["year"],
        its["season"],
        its["episode"],
        os.path.join(args.artdir, f"{fn}.jpg"),
        its["imdb_id"],
        its["omdb_status"],
        args.omdbkey,
      )
    )

  upd(
    {
      "coverart": reglob(fn + r"(\s*P\d+)?(.jpg|.jpeg|.png)", args.artdir),
      "tool": f'{prog} {version} on {time.strftime("%A, %B %d, %Y, at %X")}',
    }
  )

  log.info(f'Updating "{f}" metadata keys {", ".join(its.keys())}.')
  if not args.dryrun:
    set_meta_mutagen(f, its)

  if not (plexname := make_filename(its)):
    log.warning(f"Generating filename for {f} failed, skipping.")
    return

  if (p := os.path.join(dirname, plexname)) == f:
    return
  if os.path.exists(p):
    log.warning(f"Renaming {f} to {plexname}, target exists, skipping.")
    return

  log.info(f'Renaming "{f}" to "{plexname}".')
  if not args.dryrun:
    os.rename(f, plexname)


if __name__ == "__main__":
  parser = argparse.ArgumentParser(
    description=desc,
    fromfile_prefix_chars="@",
    prog=prog,
    epilog="Written by: " + author,
  )

  parser.add_argument("--version", action="version", version="%(prog)s " + version)
  parser.add_argument(
    "-v", "--verbose", dest="loglevel", action="store_const", const=logging.INFO
  )
  parser.add_argument(
    "-d", "--debug", dest="loglevel", action="store_const", const=logging.DEBUG
  )
  parser.set_defaults(loglevel=logging.WARN)
  parser.add_argument("-l", "--log", dest="logfile", action="store")
  parser.add_argument("files", nargs="*", metavar="FILES", help="files to update")
  parser.add_argument(
    "--descdir",
    dest="descdir",
    action="store",
    help="directory for .txt files with descriptive data",
  )
  parser.add_argument(
    "--artdir",
    dest="artdir",
    action="store",
    help="directory for .jpg and .png cover art",
  )
  parser.add_argument(
    "--omdbkey",
    dest="omdbkey",
    action="store",
    help="your OMDB key to automatically retrieve IMDb metadata and posters",
  )
  parser.add_argument(
    "--output-type",
    choices=set(["mp4", "mkv"]),
    default="mp4",
    help="container type for final result",
  )
  parser.add_argument(
    "--dryrun",
    action="store_true",
    default=False,
    help="only print updates, but do not execute them",
  )

  for inifile in [
    f"{os.path.splitext(sys.argv[0])[0]}.ini",
    prog + ".ini",
    "..\\" + prog + ".ini",
  ]:
    if os.path.exists(inifile):
      sys.argv.insert(1, "@" + inifile)
  args = parser.parse_args()
  if args.dryrun and args.loglevel > logging.INFO:
    args.loglevel = logging.INFO

  log.setLevel(0)
  logformat = logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s")

  slogger = logging.StreamHandler()
  slogger.setLevel(args.loglevel)
  slogger.setFormatter(logformat)
  log.addHandler(slogger)

  if not args.files:
    args.files = ["*.mp4", "*.m4r", "*.m4b", "*.m4a"]
  infiles = []
  for f in args.files:
    infiles.extend(glob.glob(f))
  if not infiles:
    log.error("No input files.")
    exit(1)

  for f in infiles:
    retag(f)
