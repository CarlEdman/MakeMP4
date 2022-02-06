#!/usr/bin/env python
# -*- coding: utf-8 -*-

prog = "MakeMP4"
version = "7.2"
author = "Carl Edman (CarlEdman@gmail.com)"
desc = """
Extract all tracks from .mkv files;
convert video tracks to h264/265, audio tracks to aac;
then recombine all tracks into properly tagged .mp4
"""

import argparse
import glob
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import yaml

try:
  from yaml import CDumper as Dumper
  from yaml import CLoader as Loader
except ImportError:
  from yaml import Loader, Dumper

from cetools import *  # pylint: disable=unused-wildcard-import
from tagmp4 import *  # pylint: disable=unused-wildcard-import

parser = None
args = None
log = logging.getLogger()

iso6392BtoT = {
  "alb": "sqi",
  "arm": "hye",
  "baq": "eus",
  "bur": "mya",
  "chi": "zho",
  "cze": "ces",
  "dut": "nld",
  "fre": "fra",
  "geo": "kat",
  "ger": "deu",
  "gre": "ell",
  "ice": "isl",
  "mac": "mkd",
  "mao": "mri",
  "may": "msa",
  "per": "fas",
  "rum": "ron",
  "slo": "slk",
  "tib": "bod",
  "wel": "cym",
  "English": "eng",
  "Français": "fra",
  "Japanese": "jpn",
  "Español": "esp",
  "German": "deu",
  "Deutsch": "deu",
  "Svenska": "swe",
  "Latin": "lat",
  "Dutch": "nld",
  "Chinese": "zho",
}


def cfgload(fn):
  (_, ext) = os.path.splitext(fn)
  with open(fn, "r", encoding="utf-8") as f:
    if ext in (".yaml", ".yml"):
      return yaml.load(f)
    elif ext in (".json", ".cfg"):
      return json.load(f, object_hook=defdict)
    else:
      log.error(f"{fn} is not a config file, skipping.")


def cfgdump(cfg, fn):
  (_, ext) = os.path.splitext(fn)
  with open(fn, "w", encoding="utf-8") as f:
    if ext in (".yaml", ".yml"):
      yaml.dump(cfg, f, indent=2, allow_unicode=True, encoding="utf-8")
    elif ext in (".json", ".cfg"):
      json.dump(cfg, f, ensure_ascii=False, indent=2, sort_keys=True)
    else:
      log.error(f"{fn} is not a config file, skipping.")


def syncconfig(cfg):
  if cfg.modclear():
    cfgdump(cfg, cfg["cfgname"])

def serveconfig(fn):
  try:
    j = cfgload(fn)
    yield j
    syncconfig(j)
  except yaml.YAMLError:
    log.error(f"{fn} is not a YAML config file, skipping.")
  except json.JSONDecodeError:
    log.error(f"{fn} is not a JSON config file, skipping.")
  except TypeError:
    log.error(f"Type Error in {fn}, skipping.")


def configs(path="."):
  # TODO: Read all cfg file extensions
  for fn in glob.iglob(os.path.join(path, "*.json")):
    yield from serveconfig(fn)


def maketrack(cfg, tid=None):
  track = defdict()
  if not isinstance(tid, int):
    for tid in range(sys.maxsize):
      n = f"track{tid:02d}"
      if n not in cfg:
        track["id"] = tid
        cfg[n] = track
        return track


def tracks(cfg, typ=None):
  if not isinstance(cfg, dict):
    return
  for k in list(cfg):
    if not re.fullmatch(r"track\d+", k):
      continue
    track = cfg[k]
    if track["disable"]:
      continue
    if typ and track["type"] != typ:
      continue
    if (
      "language" in track
      and "languages" in cfg
      and track["language"] not in cfg("languages")
    ):
      continue
    yield track


def readytomake(file, *comps):
  for f in comps:
    if not os.path.exists(f) or not os.path.isfile(f) or os.path.getsize(f) == 0:
      return False
    fd = os.open(f, os.O_RDONLY | os.O_EXCL)
    if fd < 0:
      return False
    os.close(fd)
  if not os.path.exists(file):
    return True
  if os.path.getsize(file) == 0:
    return False
  #  fd=os.open(file,os.O_WRONLY|os.O_EXCL)
  #  if fd<0: return False
  #  os.close(fd)
  for f in comps:
    if f and os.path.getmtime(f) > os.path.getmtime(file):
      os.remove(file)
      return True
  return False


def work_lock_delete():
  for l in glob.iglob("*.working"):
    log.debug(f"Deleting worklock {l} and associated file.")
    os.remove(l)
    f = l[: -len(".working")]
    if os.path.exists(f):
      os.remove(f)


def do_call(cargs, outfile=None, infile=None):
  def cookout(s):
    s = re.sub(r"\s*\n\s*", r"\n", s)
    s = re.sub(r"[^\n]*", r"", s)
    s = re.sub(r"\n+", r"\n", s)
    s = re.sub(r"\n \*(.*?) \*", r"\n\1", s)
    return s.strip()

  cs = [[]]
  for a in cargs:
    if a == "|":
      cs.append([])
    else:
      cs[-1].append(str(a))
  cstr = " | ".join([subprocess.list2cmdline(c) for c in cs])
  log.debug("Executing: " + cstr)


  lockfile = None
  if outfile:
    lockfile = outfile + ".working"
    if os.path.exists(lockfile):
      log.warning(f"Lockfile {lockfile} already exists.")
    with open(lockfile, "w") as f:
      f.truncate(0)

  ps = []
  for c in cs:
    ps.append(
      subprocess.Popen(
        c,
        stdin=ps[-1].stdout if ps else infile,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
      )
    )
  outstr, errstr = ps[-1].communicate()

  # encname='cp1252'/ encname='utf-8'
  outstr = outstr.decode(errors="replace")
  errstr = errstr.decode(errors="replace")
  errstr += "".join(
    [p.stderr.read().decode(errors="replace") for p in ps if not p.stderr.closed]
  )
  outstr = cookout(outstr)
  errstr = cookout(errstr)
  if outstr:
    log.debug("Output: " + repr(outstr))
  if errstr:
    log.debug("Error: " + repr(errstr))
  errcode = ps[-1].poll()
  if errcode != 0:
    if args.ignore_error:
      log.warning("Error code (ignored) for " + repr(cstr) + ": " + str(errcode))
    else:
      log.error("Error code for " + repr(cstr) + ": " + str(errcode))
      if outfile:
        open(outfile, "w").truncate(0)

  if lockfile:
    os.remove(lockfile)

  return outstr + errstr


def make_srt(cfg, track):
  base = cfg["base"]
  srt = maketrack(cfg)
  srt["file"] = f'{base} T{srt["id"]:02d}.srt'
  if not os.path.exists(srt["file"]):
    do_call(["ccextractorwin", track["file"], "-o", srt["file"]], srt["file"])
  if os.path.exists(srt["file"]) and os.path.getsize(srt["file"]) == 0:
    os.remove(srt["file"])
  if not os.path.exists(srt["file"]):
    return False
  srt["file"] = srt["file"]
  srt["type"] = "subtitles"
  srt["delay"] = 0.0
  srt["elongation"] = 1.0
  srt["extension"] = "srt"
  srt["language"] = "eng"
  return True


def config_from_base(cfg, base):
  cfg["base"] = base
  cfg["show"] = base

  # cfg['languages'] = ['eng'] # Set if we want to keep only some languages
  if m := re.fullmatch(
    r"(?P<show>.*?)\s+(pt\.? *(?P<episode>\d+) *)?\((?P<year>\d*)\) *(?P<song>.*?)",
    base,
  ):
    cfg["type"] = "movie"
    cfg["show"] = m["show"]
    if m["episode"]:
      cfg["episode"] = int(m["episode"])
    if m["year"]:
      cfg["year"] = int(m["year"])
    cfg["song"] = m["song"]
  elif (
    m := re.fullmatch(r"(?P<show>.*?)\s+S(?P<season>\d+)E(?P<episode>\d+)$", base)
  ) or (
    m := re.fullmatch(
      r"(.*?) (Se\.\s*(?P<season>\d+)\s*)?Ep\.\s*(?P<episode>\d+)$", base
    )
  ):
    cfg["type"] = "tvshow"
    cfg["show"] = m["show"]
    if m["season"] and m["season"] != "0":
      cfg["season"] = int(m["season"])
    cfg["episode"] = int(m["episode"])
  elif (
    m := re.fullmatch(r"(?P<show>.*?)\s+S(?P<season>\d+) +(?P<song>.*?)", base)
  ) or (m := re.fullmatch(r"(.*) Se\. *(?P<season>\d+) *(?P<song>.*?)", base)):
    cfg["type"] = "tvshow"
    cfg["show"] = m["show"]
    cfg["season"] = int(m["season"])
    cfg["song"] = m["song"]
  elif m := re.fullmatch(
    r"(?P<show>.*?)\s+(S(?P<season>\d+))?(V|Vol\. )(?P<episode>\d+)", base
  ):
    cfg["type"] = "tvshow"
    cfg["show"] = m["show"]
    cfg["season"] = int(m["season"])
    cfg["episode"] = int(m["episode"])
  elif m := re.fullmatch(r"(?P<show>.*?)\s+S(?P<season>\d+)D\d+", base):
    cfg["type"] = "tvshow"
    cfg["show"] = m["show"]
    cfg["season"] = int(m["season"])


def prepare_avi(cfg, avifile):
  try:
    xmlroot = ET.fromstring(
      subprocess.check_output(["mediainfo", "--output=XML", avifile]).decode(
        errors="replace"
      )
    )
    for avitrack in xmlroot.iter("track"):
      avittype = avitrack.get("type")
      if avittype == "General":
        for k in avitrack.iter():
          cfg[
            "avi" + "".join(l for l in k.tag.casefold() if l.isalnum())
          ] = k.text
        pass
      elif avittype == "Video" or avittype == "Audio":
        track = maketrack(cfg)
        track["type"] = avittype.casefold()
        for k in avitrack.iter():
          track[
            "avi" + "".join(l for l in k.tag.casefold() if l.isalnum())
          ] = k.text
      else:
        log.warning(f"Unrecognized avi track type {avittype} in {avifile}")
  except ET.ParseError:
    return


def prepare_mkv(cfg, mkvfile):
  try:
    cs = cfg["chapters"] = defdict(
      {
        "uid": [],
        "time": [],
        "hidden": [],
        "enabled": [],
        "name": [],
        "lang": [],
        "delay": 0.0,
        "elongation": 1.0,
      }
    )
    xmlroot = ET.fromstring(
      subprocess.check_output(["mkvextract", "chapters", mkvfile]).decode(
        errors="replace"
      )
    )
    for chap in xmlroot.iter("ChapterAtom"):
      cs["uid"].append(chap.find("ChapterUID").text)
      cs["time"].append(to_float(chap.find("ChapterTimeStart").text))
      cs["hidden"].append(chap.find("ChapterFlagHidden").text)
      cs["enabled"].append(chap.find("ChapterFlagEnabled").text)
      cs["name"].append(chap.find("ChapterDisplay").find("ChapterString").text)
      v = chap.find("ChapterDisplay").find("ChapterLanguage").text
      cs["lang"].append(iso6392BtoT.get(v, v))
  except ET.ParseError:
    del cfg["chapters"]

  j = json.loads(
    subprocess.check_output(["mkvmerge", "-J", mkvfile]).decode(errors="replace")
  )
  jc = j["container"]
  contain = cfg["mkvcontainer"] = defdict()
  contain["type"] = jc["type"]
  for k, v in jc["properties"].items():
    if k == "duration":
      cfg["duration"] = int(v) / 1000000000.0
    else:
      contain[k] = v

  skip_a_dts = False
  base = cfg["base"]
  for t in j["tracks"]:
    track = maketrack(cfg)
    tid = track["id"]
    track["mkvtrack"] = t["id"]
    track["type"] = t["type"]
    track["format"] = t["codec"]

    if track["format"] in {
      "V_MPEG2",
      "MPEG-1/2",
    }:
      track["extension"] = "mpg"
      track["file"] = f"{base} T{tid:02d}.mpg"
      track["dgifile"] = f"{base} T{tid:02d}.dgi"
    elif track["format"] in {
      "V_MPEG4/ISO/AVC",
      "MPEG-4p10/AVC/h.264",
      "AVC/H.264/MPEG-4p10",
    }:
      track["extension"] = "264"
      track["file"] = f"{base} T{tid:02d}.264"
      #        track['t2cfile'] = f'{base} T{tid:02d}.t2c'
      track["dgifile"] = f"{base} T{tid:02d}.dgi"
    elif track["format"] in {
      "V_MS/VFW/FOURCC, WVC1",
      "VC-1",
    }:
      track["extension"] = "wvc"
      track["file"] = f"{base} T{tid:02d}.wvc"
      #        track['t2cfile'] = f'{base} T{tid:02d}.t2c'
      track["dgifile"] = f"{base} T{tid:02d}.dgi"
    elif track["format"] in {
      "A_AC3",
      "A_EAC3",
      "AC3/EAC3",
      "AC-3/E-AC-3",
      "AC-3",
      "E-AC-3",
    }:
      track["extension"] = "ac3"
      track["file"] = f"{base} T{tid:02d}.ac3"
      track["quality"] = 60
    elif track["format"] in {"E-AC-3"}:
      log.warning(
        f'{cfg["base"]}: Track type {track["format"]} in {mkvfile} not supported, disabling.'
      )
      track["disable"] = True
      track["extension"] = "ac3"
      track["file"] = f"{base} T{tid:02d}.ac3"
      track["quality"] = 60
    elif track["format"] in {
      "TrueHD",
      "A_TRUEHD",
      "TrueHD Atmos",
    }:
      track["extension"] = "thd"
      track["file"] = f"{base} T{tid:02d}.thd"
      track["quality"] = 60
      skip_a_dts = True
    elif track["format"] in {
      "DTS-HD Master Audio",
    }:
      track["extension"] = "dts"
      track["file"] = f"{base} T{tid:02d}.dts"
      track["quality"] = 60
      skip_a_dts = True
    elif track["format"] in {
      "A_DTS",
      "DTS",
      "DTS-ES",
      "DTS-HD High Resolution",
      "DTS-HD High Resolution Audio",
    }:
      track["extension"] = "dts"
      track["file"] = f"{base} T{tid:02d}.dts"
      track["quality"] = 60
      if skip_a_dts:
        track["disable"] = True
        skip_a_dts = False
    elif track["format"] in {
      "A_PCM/INT/LIT",
      "PCM",
    }:
      track["extension"] = "pcm"
      track["file"] = f"{base} T{tid:02d}.pcm"
      track["quality"] = 60
    elif track["format"] in {
      "S_VOBSUB",
      "VobSub",
    }:
      track["extension"] = "idx"
      track["file"] = f"{base} T{tid:02d}.idx"
    elif track["format"] in {
      "S_HDMV/PGS",
      "HDMV PGS",
      "PGS",
    }:
      track["extension"] = "sup"
      track["file"] = f"{base} T{tid:02d}.sup"
    elif track["format"] in {
      "SubRip/SRT",
    }:
      track["extension"] = "srt"
      track["file"] = f"{base} T{tid:02d}.srt"
    elif track["format"] in {
      "A_MS/ACM",
    }:
      track["disable"] = True
    else:
      log.warning(
        f'{cfg["base"]}: Unrecognized track type {track["format"]} in {mkvfile}'
      )
      track["disable"] = True

    for k, v in t["properties"].items():
      if k == "language":
        track["language"] = iso6392BtoT.get(v, v)
      elif k == "display_dimensions":
        (w, h) = v.split("x")
        track["display_width"] = int(w)
        track["display_height"] = int(h)
      elif k == "pixel_dimensions":
        (w, h) = v.split("x")
        track["pixel_width"] = int(w)
        track["pixel_height"] = int(h)
      # elif k == 'default_track':
      #   track['defaulttrack'] = int(v)!=0
      elif k == "forced_track":
        track["forcedtrack"] = int(v) != 0
      elif k == "default_duration":
        track["frameduration"] = int(v) / 1000000000.0
      elif k == "track_name":
        track["trackname"] = v
      # elif k == 'minimum_timestamp':
      #   track['delay'] = int(v)/1000000000.0
      elif k == "audio_sampling_frequency":
        track["samplerate"] = v
      elif k == "audio_channels":
        track["channels"] = v
      # if int(v)>2: track['downmix'] =
      else:
        track[k] = v

  extract = []
  for track in tracks(cfg):
    file = track["file"]
    mkvtrack = track["mkvtrack"]
    if (args.keep_video_in_mkv and track["type"] == "video") or (
      args.keep_audio_in_mkv and track["type"] == "audio"
    ):
      track["extension"] = "mkv"
      track["file"] = mkvfile
    elif file and not os.path.exists(file) and mkvtrack:
      extract.append(f"{mkvtrack:d}:{file}")
  if extract:
    do_call(["mkvextract", "tracks", mkvfile] + extract)

  #  for track in tracks(cfg, 'video'):
  #    make_srt(cfg, track)

  tcs = []
  for track in tracks(cfg):
    if "t2cfile" not in track or "mkvtrack" not in track:
      continue
    if not os.path.exists(track["t2cfile"]) and track["mkvtrack"]:
      tcs.append(f'{track["mkvtrack"]}:{track["t2cfile"]}')
  if tcs:
    do_call(["mkvextract", "timecodes_v2", mkvfile] + tcs)

  for track in tracks(cfg):
    if track["extension"] != ".sub":
      continue
    try:
      with open(track["t2cfile"], "rt", encoding="utf-8") as fp:
        t2cl = [to_float(l) for l in fp]
    except ValueError:
      log.warning(f'Unrecognized line in {track["t2cfile"]}, skipping.')
    if len(t2cl) == 0:
      continue
    #    oframes = track['frames']
    #    frames = len(t2cl)-1
    #    if oframes>0 and frames != oframes:
    #      log.warning(f'Timecodes changed frames in "{file}" from {oframes:d} to {frames:d}')
    #    cfg.set('frames',frames)
    odur = track["duration"]
    track["duration"] = dur = t2cl[-1] / 1000.0
    if odur and odur > 0 and odur != dur:
      log.warning(
        f'Encoding changed duration in "{file}" from {odur:f} to {dur:f}'
      )

  for track in tracks(cfg, "subtitle"):
    if track["extension"] != ".sub":
      continue
    idxfile = os.path.splitext(track["file"])[0] + ".idx"
    track["timestamp"] = []
    with open(idxfile, "rt", encoding="utf-8", errors="replace").read() as fp:
      for l in fp:
        if re.fullmatch(r"\s*#.*", l):
          continue
        elif re.fullmatch(r"\s*", l):
          continue
        elif (
          m := re.fullmatch(
            r"\s*timestamp:\s*(?P<time>.*),\s*filepos:\s*(?P<pos>[0-9a-fA-F]+)\s*",
            l,
          )
        ) and (t := to_float(m["time"])):
          track["timestamp"].append(t)
          track["filepos"].append(m["pos"])
        elif m := re.fullmatch(r"\s*id\s*:\s*(\w+?)\s*, index:\s*(\d+)\s*", l):
          track["language"] = m[1]  # Convert to 3 character codes
          track["langindex"] = m[2]
        elif m := re.fullmatch(r"\s*(\w+)\s*:\s*(.*?)\s*", l):
          track[m[1]] = m[2]
        else:
          log.warning(
            f'{cfg["base"]}: Ignorning in {idxfile} uninterpretable line: {l}'
          )
    # remove idx file

  if args.delete_source:
    os.remove(mkvfile)


def build_indices(cfg, track):
  file = track["file"]
  dgifile = track["dgifile"]
  logfile = os.path.splitext(file)[0] + ".log"

  if not dgifile or os.path.exists(dgifile):
    return False
  if dgifile.endswith(".dgi"):
    do_call(["DGIndexNV", "-i", file, "-o", dgifile, "-h", "-e"], dgifile)
  elif dgifile.endswith(".d2v"):
    do_call(
      [
        "dgindex",
        "-i",
        file,
        "-o",
        os.path.splitext(dgifile)[0],
        "-fo",
        "0",
        "-ia",
        "3",
        "-om",
        "2",
        "-hide",
        "-exit",
      ],
      dgifile,
    )
  else:
    return False

  dg = track["dg"] = defdict()
  while True:
    time.sleep(1)
    if not os.path.exists(logfile):
      continue
    with open(logfile, "rt", encoding="utf-8", errors="replace") as fp:
      for l in fp:
        l = l.strip()
        if m := re.fullmatch("([^:]*):(.*)", l):
          k = "".join(i for i in m[1].casefold() if i.isalnum())
          v = m[2].strip()
          if not v:
            continue
          if dg[k] == v:
            continue
          elif dg[k]:
            dg[k] += f";{v}"
          else:
            dg[k] = v
        else:
          log.warning(f"Unrecognized DGIndex log line: {repr(l)}")
    if dg["info"] == "Finished!":
      break
  os.remove(logfile)

  track["type"] = "video"
  # track['outformat'] = 'h264'
  track["outformat"] = "h265"
  track["avc_profile"] = "high"
  track["x265_preset"] = "slow"
  # track['x265_tune'] = 'animation'
  # track['x265_output_depth'] = '8'

  track["crop"] = "auto"
  #   = str(arf)

  with open(track["dgifile"], "rt", encoding="utf-8", errors="replace") as fp:
    dgip = fp.read().split("\n\n")
  if len(dgip) != 4:
    log.error(f'Malformed index file {track["dgifile"]}')
    return False

  if re.match("DG(AVC|MPG|VC1)IndexFileNV(14|15|16)", dgip[0]):
    if m := re.search(r"\bSIZ *(?P<sizex>\d+) *x *(?P<sizey>\d+)", dgip[3]):
      track["picture_width"] = int(m["sizex"])
      track["picture_height"] = int(m["sizey"])
    else:
      log.error(f'No SIZ in {track["dgifile"]}')
      return False

    if m := re.search(
      r"\bCLIP\ *(?P<left>\d+) *(?P<right>\d+) *(?P<top>\d+) *(?P<bottom>\d+)",
      dgip[2],
    ):
      w = track["picture_width"] - int(m["left"]) - int(m["right"])
      h = track["picture_height"] - int(m["top"]) - int(m["bottom"])
      track["macroblocks"] = int(math.ceil(w / 16.0)) * int(math.ceil(h / 16.0))
    else:
      log.error(f'No CLIP in {track["dgifile"]}')

    if "sar" in dg:
      track["sample_aspect_ratio"] = to_float(dg["sar"])
    elif (
      "display_width" in track
      and "display_height" in track
      and "pixel_width" in track
      and "pixel_height" in track
    ):
      dratio = track["display_width"] / track["display_height"]
      pratio = track["pixel_width"] / track["pixel_height"]
      track["sample_aspect_ratio"] = dratio / pratio
    else:
      log.warning(f'Guessing 1:1 SAR for {track["dgifile"]}')
      track["sample_aspect_ratio"] = 1.0

    if m := re.search(r"\bORDER *(?P<order>\d+)", dgip[3]):
      track["field_operation"] = int(m["order"])
    else:
      log.error(f'No ORDER in {track["dgifile"]}')
      return False

    if m := re.search(r"\bFPS *(?P<num>\d+) */ *(?P<denom>\d+) *", dgip[3]):
      track["frame_rate_ratio"] = int(m["num"]) / int(m["denom"])
    else:
      log.error(f'No FPS in {track["dgifile"]}')
      return False

    if m := re.search(r"\b(?P<ipercent>\d*(\.\d*)?%) *FILM", dgip[3]):
      track["interlace_fraction"] = to_float(m["ipercent"])
    else:
      log.error(f'No FILM in {track["dgifile"]}')
      return False

    if track["field_operation"] == 0:
      track["interlace_type"] = "PROGRESSIVE"
    elif track["interlace_fraction"] > 0.5:
      track["interlace_type"] = "FILM"
    else:
      track["interlace_type"] = "INTERLACE"

    # ALSO 'CODED' FRAMES
    if m := re.search(r"\bPLAYBACK *(?P<playback>\d+)", dgip[3]):
      track["frames"] = int(m["playback"])
    else:
      log.error(f'No PLAYBACK in {track["dgifile"]}')
      return False
  else:
    log.error(f'Unrecognize index file {track["dgifile"]}')
    return False

  if track["macroblocks"] <= 1620:  # 480p@30fps; 576p@25fps
    track["avc_level"] = 3.0
    track["x264_rate_factor"] = 16.0
    track["x265_rate_factor"] = 17.0
  elif track["macroblocks"] <= 3600:  # 720p@30fps
    track["avc_level"] = 3.1
    track["x264_rate_factor"] = 18.0
    track["x265_rate_factor"] = 19.0
  elif track["macroblocks"] <= 8192:  # 1080p@30fps
    track["avc_level"] = 4.0
    track["x264_rate_factor"] = 19.0
    track["x265_rate_factor"] = 20.0
    cfg["hdvideo"] = True
  elif track["macroblocks"] <= 22080:  # 1080p@72fps; 1920p@30fps
    track["avc_level"] = 5.0
    track["x264_rate_factor"] = 20.0
    track["x265_rate_factor"] = 21.0
    cfg["hdvideo"] = True
  else:  # 1080p@120fps; 2048@30fps
    track["avc_level"] = 5.1
    track["x264_rate_factor"] = 21.0
    track["x265_rate_factor"] = 22.0
    cfg["hdvideo"] = True

  return True


def build_subtitle(cfg, track):
  infile = track["file"]
  inext = track["extension"]
  delay = track["delay"] or 0.0
  elong = track["elongation"] or 1.0

  if inext == "sup":
    track["outfile"] = outfile = os.path.splitext(infile)[0] + ".idx"
    if os.path.exists(outfile):
      return  # Should be not readytomake(outfile,)
    call = ["bdsup2sub++", "--resolution", "keep"]
    if delay != 0.0:
      call += ["--delay", delay]

    fps = track["frame_rate_ratio_out"] or cfg["track00"]["frame_rate_ratio_out"]
    fps2target = {
      24.0: "24p",
      24000 / 1001: "24p",
      25.0: "25p",
      25000 / 1001: "25p",
      30.0: "30p",
      30000 / 1001: "30p",
    }
    if fps in fps2target:
      call += ["--fps-target", fps2target[fps]]

    call += ["--output", outfile, infile]
    do_call(call, outfile)  # '--fix-invisible',
    if (
      not os.path.exists(outfile)
      or not os.path.isfile(outfile)
      or os.path.getsize(outfile) == 0
    ):
      log.error(f"Subtitle {outfile} empty and disabled.")
      track["disable"] = True
  elif inext == "srt":
    track["outfile"] = outfile = os.path.splitext(infile)[0] + ".ttxt"
    if os.path.exists(outfile):
      return False  # Should be not readytomake(outfile,)
    with open(infile, "rt", encoding="utf-8", errors="replace") as i, open(
      "temp.srt", "wt", encoding="utf-8", errors="replace"
    ) as o:
      for l in i.read().split("\n\n"):
        if l.startswith("\ufeff"):
          l = l[1:]
        if not l.strip():
          continue
        elif (
          (
            m := re.fullmatch(
              r"(?s)(?P<beg>\s*\d*\s*)(?P<time1>[0-9,.:]*)(?P<mid> --> )(?P<time2>[0-9,.:]*)(?P<end>.*)",
              l,
            )
          )
          and (t1 := to_float(m["time1"]))
          and (t2 := to_float(m["time2"]))
          and (s1 := t1 * elong + delay) >= 0
          and (s2 := t2 * elong + delay) >= 0
        ):
          o.write(
            f'{m["beg"]}{unparse_time(s1)}{m["mid"]}{unparse_time(s2)}{m["end"]}\n\n'
          )
        else:
          log.warning(f"Unrecognized line in {infile}: {repr(l)}")

    do_call(["mp4box", "-ttxt", "temp.srt"], outfile)
    if os.path.exists("temp.ttxt"):
      os.rename("temp.ttxt", outfile)
    if os.path.exists("temp.srt"):
      os.remove("temp.srt")
  elif False:  # inext=='idx':
    track["outfile"] = outfile = os.path.splitext(infile)[0] + ".adj.idx"
    subfile = os.path.splitext(infile)[0] + ".adj.sub"
    if not os.path.exists(subfile):
      shutil.copy(os.path.splitext(infile)[0] + ".sub", subfile)
    if os.path.exists(outfile):
      return  # Should be not readytomake(outfile,)
    with open(infile, "rt", encoding="utf-8", errors="replace") as i, open(
      outfile, "wt", encoding="utf-8", errors="replace"
    ) as o:
      for l in i:
        print(l)
        if (
          (
            m := re.fullmatch(
              r"(?s)(?P<beg>\s*timestamp:\s*)\b(?P<time>.*\d)\b(?P<end>.*)",
              l,
            )
          )
          and (t := to_float(m["time"]))
          and ((s := t * elong + delay) >= 0)
        ):
          l = f'{m["beg"]}{unparse_time(s)}{m["end"]}'
        o.write(l)
  else:
    if elong != 1.0 or delay != 0.0:
      log.warning(
        f'Delay and elongation not implemented for subtitles type "{infile}"'
      )
    track["outfile"] = outfile = infile

  if not os.path.exists(track["outfile"]):
    track["disable"] = True
    return False
  return True


def build_audio(cfg, track):
  # pylint: disable=used-before-assignment
  track["outfile"] = track["outfile"] or f'{cfg["base"]} T{track["id"]:02d}.m4a'
  if not readytomake(track["outfile"], track["file"]):
    return False

  if track["extension"] in ():  # ('dts', 'thd'):
    call = ["dcadec", "-6", track["file"], "-"]
  else:
    if track["elongation"] and track["elongation"] != 1.0:
      log.warning(f"Audio elongation not implemented")
    if track["downmix"] not in (2, 6, None):
      log.warning(f'Invalid downmix "{track["downmix"]}"')
    call = [
      "eac3to",
      track["file"],
      f'{track["mkvtrack"]+1}:' if track["extension"] == "mkv" else None,
      "stdout.wav"
      #      , '-no2ndpass'
      ,
      "-log=nul",
      f'{track["delay"]*1000.0:+.0f}ms' if track["delay"] else None
      #      , '-0,1,2,3,5,6,4' if track['channels']==7 else None
      ,
      "-down6" if track["downmix"] == 6 else None,
      "-downDpl" if track["downmix"] == 2 else None,
      "-normalize" if track["normalize"] else None,
      "|",
      "qaac64",
      "--threading",
      "--ignorelength",
      "--no-optimize",
      "--tvbr",
      track["quality"] or 60,
      "--quality",
      "2",
      "-",
      "-o",
      track["outfile"],
    ]

  res = do_call((c for c in call if c), track["outfile"])
  if res and (m := re.match(r"\bwrote (\d+\.?\d*) seconds\b", res)):
    track["duration"] = to_float(m[1])
  if (
    (dur := track["duration"])
    and (mdur := cfg["duration"])
    and abs(dur - mdur) > 0.5
  ):
    log.warning(
      f'Audio track "{track["file"]}" duration differs (elongation={mdur/dur})'
    )
  return True


def build_video(cfg, track):
  infile = track["file"]
  dgifile = track["dgifile"]

  outfile = track["outfile"]
  fmt2ext = {"h264": ".264", "h265": ".265"}
  if outfile == None:
    if track["outformat"] not in fmt2ext:
      log.error(f'{infile}: Unrecognized output format: {track["outformat"]}')
      return False
    track[
      "outfile"
    ] = outfile = f'{cfg["base"]} T{track["id"]:02d}{fmt2ext[track["outformat"]]}'

  track["avsfile"] = track["avsfile"] or (
    os.path.splitext(os.path.basename(infile))[0] + ".avs"
  )

  if not readytomake(outfile, infile, dgifile):
    return False

  procs = track["processors"] or 8
  avs = [
    f"SetMTMode(5,{procs:d})" if procs != 1 else None,
    "SetMemoryMax(1024)",
    f'DGDecode_mpeg2source("{os.path.abspath(dgifile)}", info=3, idct=4, cpu=3)'
    if dgifile.endswith(".d2v")
    else None,
    f'DGSource("{os.path.abspath(dgifile)}", deinterlace={1 if track["interlace_type"] in ["VIDEO", "INTERLACE"] else 0:d})\n'
    if dgifile.endswith(".dgi")
    else None
    #    , 'ColorMatrix(hints = true, interlaced=false)'
    ,
    "unblock(cartoon=true)"
    if track["unblock"] == "cartoon"
    or (track["unblock"] == True and track["x264_tune"] == "animation")
    else None,
    "unblock(photo=true)"
    if track["unblock"] == "photo"
    or (track["unblock"] == True and track["x264_tune"])
    else None,
    "unblock()"
    if track["unblock"] == "normal" or track["unblock"] == True
    else None,
    "tfm().tdecimate(hybrid=1)" if track["interlace_type"] in {"FILM"} else None,
  ]

  if track["interlace_type"] in {"FILM"}:
    track["frame_rate_ratio_out"] = track["frame_rate_ratio"] * 0.8
  #    track['frames']=math.ceil(track['frames']*5.0/4.0))
  #    avs+=f'tfm().tdecimate(hybrid=1,d2v="{os.path.abspath(dgifile)}")\n'
  #    avs+=f'Telecide(post={0 if lp>0.99 else 2:d},guide=0,blend=True)'
  #    avs+=f'Decimate(mode={0 if lp>0.99 else 3:d},cycle=5)'
  #  elif track['interlace_type'] in ['VIDEO', 'INTERLACE']:
  #    track["frame_rate_ratio_out"] = track['frame_rate_ratio']
  #    avs+=f'Bob()\n'
  #    avs+=f'TomsMoComp(1,5,1)\n'
  #    avs+=f'LeakKernelDeint()\n'
  #    avs+=f'TDeint(mode=2, type={3 if track['x264_tune']'animation' if track['genre']section='MAIN') in ['Anime', 'Animation'] else 'film')=='animation' else 2:d}, tryWeave=True, full=False)\n'
  else:
    track["frame_rate_ratio_out"] = track["frame_rate_ratio"]

  if "crop" in track:
    if m := re.fullmatch(
      r"\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*$", track["crop"]
    ):
      cl, cr, ct, cb = [int(m[i]) for i in range(1, 5)]
      px = track["picture_width"]
      py = track["picture_height"]
      if (px - cl - cr) % 2 != 0:
        cr += 1
      if (py - ct - cb) % 2 != 0:
        cb += 1
      if cl or cr or ct or cb:
        avs += [f"crop({cl:d},{ct:d},{-cr:d},{-cb:d},align=true)"]
    elif track["crop"] == "auto":
      avs += ["autocrop(threshold=30,wMultOf=2, hMultOf=2,samples=51, mode=0)"]

  if procs != 1:
    avs += ["SetMTMode(2)"]

  blocksize = 16 if track["macroblocks"] > 1620 else 8
  degrain = track["degrain"] or 3
  if degrain >= 1:  # or track['interlace_type'] in ['VIDEO', 'INTERLACE']
    avs += [
      "super = MSuper(planar=true)",
      f"bv1 = MAnalyse(super, isb = true,  delta = 1, blksize={blocksize:d}, overlap={blocksize//2:d})",
      f"fv1 = MAnalyse(super, isb = false, delta = 1, blksize={blocksize:d}, overlap={blocksize//2:d})",
    ]
  if degrain >= 2:
    avs += [
      f"bv2 = MAnalyse(super, isb = true,  delta = 2, blksize={blocksize:d}, overlap={blocksize//2:d})",
      f"fv2 = MAnalyse(super, isb = false, delta = 2, blksize={blocksize:d}, overlap={blocksize//2:d})",
    ]
  if degrain >= 3:
    avs += [
      f"bv3 = MAnalyse(super, isb = true,  delta = 3, blksize={blocksize:d}, overlap={blocksize//2:d})",
      f"fv3 = MAnalyse(super, isb = false, delta = 3, blksize={blocksize:d}, overlap={blocksize//2:d})",
    ]

  if degrain > 0:
    avs += [
      f'MDegrain{degrain:d}(super,thSAD=400,planar=true,{",".join([f"bv{i:d},fv{i:d}" for i in range(1, degrain+1)])})'
    ]

  avs += ["Distributor()" if procs != 1 else None]

  if not os.path.exists(track["avsfile"]) or os.path.getmtime(
    infile
  ) > os.path.getmtime(track["avsfile"]):
    with open(track["avsfile"], "wt", encoding="utf-8", errors="replace") as fp:
      fp.write("\n".join(a for a in avs if a))
    log.debug(f"Created AVS file: {repr(avs)}")

  call = ["avs2pipemod", "-y4mp", track["avsfile"], "|"]

  if track["outformat"] == "h264":
    call += [
      "x264",
      "--demuxer",
      "y4m",
      "-",
      "--preset",
      track["x264_preset"] or "veryslow",
      "--tune",
      track["x264_tune"] or "film",
      "--crf",
      track["x264_rate_factor"] or 20.0,
      "--profile" if "avc_profile" in track else None,
      track["avc_profile"] if "avc_profile" in track else None,
      "--level" if "avc_level" in track else None,
      track["avc_level"] if "avc_level" in track else None,
      "--non-deterministic" if not track["x264_deterministic"] else None,
      "--no-fast-pskip" if not track["x264_fast_pskip"] else None,
      "--no-dct-decimate" if not track["x264_dct_decimate"] else None,
    ]
    # if 't2cfile' in track: call += ['--timebase', '1000', '--tcfile-in', track['t2cfile']]
    # if not track['deinterlace'] and 'frames' in track: call += ['--frames', track['frames']]
  elif track["outformat"] == "h265":
    call += [
      "x265",
      "--input",
      "-",
      "--y4m",
      "--preset",
      track["x265_preset"] or "slow",
      "--crf",
      track["x265_rate_factor"] or 22.0,
      "--pmode",
      "--pme",
      "--tune" if "x265_tune" in track else None,
      track["x265_tune"] if "x265_tune" in track else None,
      "--output-depth" if "x265_bit_depth" in track else None,
      track["x265_bit_depth"] if "x265_bit_depth" in track else None,
      "--output",
      outfile,
    ]
    # --display-window <left,top,right,bottom> Instead of crop?
  else:
    log.error(f'{outfile}: Unrecognized output format "{track["outformat"]}"')
    return False

  call += [
    "--fps",
    to_ratio_string(track["frame_rate_ratio_out"]),
    "--sar",
    to_ratio_string(track["sample_aspect_ratio"], sep=":"),
  ]

  res = do_call((c for c in call if c), outfile)
  if res and (m := re.match(r"\bencoded (\d+) frames\b", res)):
    nframes = int(m[1])
    oframes = int(
      track["frame_rate_ratio_out"] / track["frame_rate_ratio"] * track["frames"]
    )
    # Adjust oframes for difference between frame-rate-in and frame-rate-out
    if "frames" in track and abs(nframes - oframes) > 2:
      log.warning(
        f'Encoding changed frames in "{infile}" from {oframes:d} to {nframes:d}'
      )
    track["frames"] = nframes
    track["duration"] = nframes / track["frame_rate_ratio_out"]
    mdur = track["duration"] or cfg["duration"]
    if abs(track["duration"] - mdur) > 5.0:
      log.warning(
        f'Video track "{infile}" duration differs (elongation={track["duration"]/mdur:f})'
      )
  return True


def build_result(cfg):
  base = cfg["base"]
  for track in tracks(cfg):
    outfile = track["outfile"]
    trackid = track["id"]
    if not outfile:
      log.warning(f"Unable to build {base} because {trackid}:outfile not defined")
      return False
    if not os.path.exists(outfile):
      log.warning(
        f"Unable to build {base} because {trackid}:{outfile} does not exist"
      )
      return False
    if os.path.getsize(outfile) == 0:
      log.warning(f"Unable to build {base} because {trackid}:{outfile} is empty")
      return False

  outfile = make_filename(cfg)
  if not outfile:
    log.error(f"Unable to generate filename for {cfg}.")
    return False
  if args.outdir:
    outfile = os.path.join(args.outdir, outfile)

  infiles = [cfg["cfgname"]]
  coverfiles = []
  for c in cfg["coverart"] or []:
    if os.path.dirname(c) == None and args.artdir:
      c = os.path.join(args.artdir, c)
    if os.path.exists(c):
      coverfiles.append(c)
  infiles += coverfiles

  call = ["mp4box", "-new", outfile]
  trcnt = {}
  mdur = cfg["duration"]

  for track in tracks(cfg):
    of = track["outfile"]
    dur = track["duration"]
    if mdur and dur:
      if abs(mdur - dur) > 0.5 and abs(mdur - dur) * 200 > mdur:
        log.warning(
          f'Duration of "{base}" ({mdur:f}s) deviates from track {of} duration({dur:f}s).'
        )

    call += ["-add", of]
    infiles.append(of)

    if name := track["name"] or track["trackname"]:
      call[-1] += ":name=" + name

    if lang := track["language"]:
      call[-1] += ":lang=" + lang
    if fps := track["frame_rate_ratio_out"]:
      call[-1] += ":fps=" + str(fps)
    if mdur or dur:
      call[-1] += ":dur=" + str(mdur or dur)
    # if sar := track['sample_aspect_ratio']:
    #   (n,d) = Fraction.from_float(sar).limit_denominator(1000).as_integer_ratio()
    #   call[-1] += f':par={n}:{d}'

    if track["type"] in trcnt:
      trcnt[track["type"]] += 1
    else:
      trcnt[track["type"]] = 1

    if track["type"] == "audio" and not track["default_track"]:
      call[-1] += ":disable"

  if not readytomake(outfile, *infiles):
    return False

  if sum(trcnt.values()) > 18:
    log.warning(f'Result for "{base}" has more than 18 tracks.')

  cfg["tool"] = f'{prog} {version} on {time.strftime("%A, %B %d, %Y, at %X")}'
  syncconfig(cfg)
  do_call(call, outfile)
  set_meta_mutagen(outfile, cfg)
  set_chapters_cmd(outfile, cfg)
  return True


def build_meta(cfg):
  def upd(i):
    if not i:
      return
    for k, v in i.items():
      if not v:
        continue
      elif k == "comment":
        for c in v:
          cfg["comment"] = add_to_list(cfg["comment"], c)
      elif cfg[k] is None:
        cfg[k] = v
      elif (
        type(cfg[k]) is str
        and len(cfg[k]) > 0
        and cfg[k][0] == "_"
        and cfg[k][-1] == "_"
      ):
        cfg[k] = v

  title = cfg["title"] or cfg["show"] or cfg["base"]
  season = cfg["season"]
  fn = f'{cfg["show"] or ""}{" S" + str(season) if season else ""}'
  ufn = "".join(c.upper() for c in fn if c.isalnum())

  descpath = os.path.join(args.descdir, f"{fn}.txt")
  artfn = os.path.join(args.artdir, f"{fn}.jpg")
  upd(get_meta_local(title, cfg["year"], cfg["season"], cfg["episode"], descpath))

  imdb_info = get_meta_imdb(
    title,
    None if args.ignore_year_imdb else cfg["year"],
    cfg["season"],
    cfg["episode"],
    artfn,
    cfg["imdb_id"],
    None if args.reset_imdb else cfg["omdb_status"],
    args.omdbkey,
  )
  if args.reset_imdb:
    for i in imdb_info:
      del cfg[i]
  upd(imdb_info)

  upd(
    {
      "year": f"_{ufn}YEAR_",
      "genre": f"_{ufn}GENRE_",
      "description": f"_{ufn}DESC_",
      "coverart": reglob(rf"{fn}(\s*P\d+)?(.jpg|.jpeg|.png)", args.artdir),
    }
  )

  return True


def main():
  #    if os.path.getmtime(sys.argv[0])>progmodtime:
  #      exec(compile(open(sys.argv[0]).read(), sys.argv[0], 'exec')) # execfile(sys.argv[0])

  preparers = {
    ".mkv": prepare_mkv,
    ".avi": prepare_avi
    # , '.tivo': prepare_tivo
    # , '.mpg': prepare_mpg
  }
  for d in sources:
    for f in sorted(os.listdir(d)):
      qf = os.path.join(d, f)
      if not os.path.isfile(qf):
        continue
      (base, ext) = os.path.splitext(f)
      fn = f"{base}.{args.config_format}"
      if args.outdir:
        fn = os.path.join(args.outdir, fn)
      if os.path.exists(fn):
        continue

      cfgdump(defdict({"cfgname": fn}), fn)

      if ext.casefold() not in preparers:
        log.warning(f"Source file type not recognized {qf}")
        continue
      for cfg in serveconfig(fn):
        config_from_base(cfg, base)
        preparers[ext.casefold()](cfg, qf)

  for cfg in configs():
    build_meta(cfg)

  for cfg in configs():
    build_result(cfg)

  for cfg in configs():
    for track in tracks(cfg, "video"):
      build_indices(cfg, track)

  for cfg in configs():
    for track in tracks(cfg, "subtitles"):
      build_subtitle(cfg, track)

  for cfg in configs():
    for track in tracks(cfg, "audio"):
      build_audio(cfg, track)

  for cfg in configs():
    for track in tracks(cfg, "video"):
      build_video(cfg, track)


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
    "-n", "--nice", dest="niceness", action="store", type=int, default=0
  )
  parser.add_argument("-l", "--log", dest="logfile", action="store")
  parser.add_argument(
    "sourcedirs",
    nargs="*",
    metavar="DIR",
    help="directories to search for source files",
  )
  parser.add_argument(
    "--outdir",
    dest="outdir",
    action="store",
    help="directory for finalized .mp4 files; if unspecified use working directory",
  )
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
    "--mak",
    dest="mak",
    action="store",
    help="your TiVo MAK key to decrypt .TiVo files to .mpg",
  )
  parser.add_argument(
    "--omdbkey",
    dest="omdbkey",
    action="store",
    help="your OMDB key to automatically retrieve posters",
  )
  parser.add_argument(
    "--move-source",
    action="store_true",
    default=False,
    help="move source files to working directory before extraction",
  )
  parser.add_argument(
    "--delete-source",
    action="store_true",
    default=False,
    help="delete source file after successful extraction",
  )
  parser.add_argument(
    "--keep-video-in-mkv",
    action="store_true",
    default=False,
    help="do not attempt to extract video tracks from MKV source, but instead use MKV file directly",
  )
  parser.add_argument(
    "--keep-audio-in-mkv",
    action="store_true",
    default=False,
    help="do not attempt to extract audio tracks from MKV source, but instead use MKV file directly",
  )
  parser.add_argument(
    "--ignore-year-imdb",
    action="store_true",
    default=False,
    help="do not use year information, if any, in omdb queries",
  )
  parser.add_argument(
    "--reset-imdb",
    action="store_true",
    default=False,
    help="overwrite information with new IMDB data",
  )
  parser.add_argument(
    "--ignore-error",
    action="store_true",
    default=False,
    help="ignore errors in external utilities",
  )

  parser.add_argument(
    "--config-format",
    choices=["json", "yaml"],
    default="json",
    help="format for new config files",
  )

  for inifile in [
    f"{os.path.splitext(sys.argv[0])[0]}.ini",
    prog + ".ini",
    "..\\" + prog + ".ini",
  ]:
    if os.path.exists(inifile):
      sys.argv.insert(1, "@" + inifile)
  args = parser.parse_args()

  log.setLevel(0)

  if args.logfile:
    flogger = logging.handlers.WatchedFileHandler(args.logfile, "a", "utf-8")
    flogger.setLevel(logging.DEBUG)
    flogger.setFormatter(
      logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s")
    )
    log.addHandler(flogger)

  tlogger = TitleHandler()
  tlogger.setLevel(logging.DEBUG)
  tlogger.setFormatter(logging.Formatter("makemp4: %(message)s"))
  log.addHandler(tlogger)

  slogger = logging.StreamHandler()
  slogger.setLevel(args.loglevel)
  slogger.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s: %(message)s"))
  log.addHandler(slogger)

  log.info(prog + " " + version + " starting up.")
  nice(args.niceness)
  progmodtime = os.path.getmtime(sys.argv[0])

  sources = []
  for d in args.sourcedirs:
    if not os.path.exists(d):
      log.warning(f'Source directory "{d}" does not exist')
    elif not os.path.isdir(d):
      log.warning(f'Source directory "{d}" is not a directory')
    #  elif not isreadable(d):
    #    log.warning(f'Source directory "{d}" is not readable')
    else:
      sources.append(d)

  work_lock_delete()
  sleep_state = None
  while True:
    sleep_state = sleep_change_directories(["."] + sources, sleep_state)
    main()
    log.debug("Sleeping.")
