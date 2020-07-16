#!/usr/bin/python

prog='MakeMP4'
version='6.0'
author='Carl Edman (CarlEdman@gmail.com)'
desc='Extract all tracks from .mkv, .mpg, .TiVo, or .vob files; convert video tracks to h264, audio tracks to aac; then recombine all tracks into properly tagged .mp4'

import re
import os
import os.path
import sys
import argparse
import logging
import time
import math
import shutil
import tempfile
import json
import string
import glob
import subprocess
from fractions import Fraction

import regex
from AdvConfig import AdvConfig

from cetools import *
from tagmp4 import *

import xml.etree.ElementTree as ET

parser = None
args = None
log = logging.getLogger()

iso6392BtoT = {
  'alb':'sqi',
  'arm':'hye',
  'baq':'eus',
  'bur':'mya',
  'chi':'zho',
  'cze':'ces',
  'dut':'nld',
  'fre':'fra',
  'geo':'kat',
  'ger':'deu',
  'gre':'ell',
  'ice':'isl',
  'mac':'mkd',
  'mao':'mri',
  'may':'msa',
  'per':'fas',
  'rum':'ron',
  'slo':'slk',
  'tib':'bod',
  'wel':'cym',

  'English':'eng',
  'Français': 'fra',
  'Japanese':'jpn',
  'Español':'esp' ,
  'German':'deu',
  'Deutsch':'deu',
  'Svenska':'swe',
  'Latin':'lat',
  'Dutch':'nld',
  'Chinese':'zho'
  }

def readytomake(file,*comps):
  for f in comps:
    if not os.path.exists(f) or not os.path.isfile(f) or os.path.getsize(f)==0 or work_locked(f): return False
    fd=os.open(f,os.O_RDONLY|os.O_EXCL)
    if fd<0:
      return False
    os.close(fd)
  if not os.path.exists(file): return True
  if os.path.getsize(file)==0:
    return False
#  fd=os.open(file,os.O_WRONLY|os.O_EXCL)
#  if fd<0: return False
#  os.close(fd)
  for f in comps:
    if f and os.path.getmtime(f)>os.path.getmtime(file):
      os.remove(file)
      return True
  return False

def do_call(args,outfile=None,infile=None):
  def cookout(s):
    s=re.sub(r'\s*\n\s*',r'\n',s)
    s=re.sub(r'[^\n]*',r'',s)
    s=re.sub(r'\n+',r'\n',s)
    s=re.sub(r'\n \*(.*?) \*',r'\n\1',s)
    return s.strip()

  cs=[[]]
  for a in args:
    if a=='|':
      cs.append([])
    else:
      cs[-1].append(str(a))
  cstr = ' | '.join([subprocess.list2cmdline(c) for c in cs])
  log.debug('Executing: '+ cstr)
  work_lock(outfile)
  ps=[]
  for c in cs:
    ps.append(subprocess.Popen(c, stdin=ps[-1].stdout if ps else infile, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
  outstr, errstr = ps[-1].communicate()

  work_unlock(outfile)
  # encname='cp1252'/ encname='utf-8'
  outstr = outstr.decode(errors='replace')
  errstr = errstr.decode(errors='replace')
  errstr += "".join([p.stderr.read().decode(errors='replace') for p in ps if not p.stderr.closed])
  outstr=cookout(outstr)
  errstr=cookout(errstr)
  if outstr: log.debug('Output: '+repr(outstr))
  if errstr: log.debug('Error: '+repr(errstr))
  errcode = ps[-1].poll()
  if errcode!=0:
    log.error('Error code for ' + repr(cstr) + ': ' + str(errcode))
    if outfile: open(outfile,'w').truncate(0)
  return outstr+errstr

def make_srt(cfg,track,files):
  return True
  base=cfg.get('base',section='MAIN')
  srtfile=f'{base} T{track:02d}.srt'
  if not os.path.exists(srtfile): do_call(['ccextractorwin'] + files + ['-o', srtfile],srtfile)
  if os.path.exists(srtfile) and os.path.getsize(srtfile)==0: os.remove(srtfile)
  if not os.path.exists(srtfile): return False
  cfg.setsection(f'TRACK{track:02d}')
  cfg.set('file',srtfile)
  cfg.set('type','subtitles')
  cfg.set('delay',0.0)
  cfg.set('elongation',1.0)
  cfg.set('extension','srt')
  cfg.set('language','eng')
  cfg.sync()
  return True

def config_from_base(cfg,base):
  cfg.setsection('MAIN')
  cfg.set('base',base)
  cfg.set('show',base)
  cfg.set('type','')

  #cfg.set('audio_languages','eng') # Set if we want to keep only some languages
  r=regex.RegEx()
  if r(r'^(?P<show>.*?) (pt\.? *(?P<episode>\d+) *)?\((?P<year>\d*)\) *(?P<song>.*?)$',base):
    cfg.set('type','movie')
    cfg.set('show',r.show)
    if r.episode: cfg.set('episode',int(r.episode))
    cfg.set('year',r.year)
    cfg.set('song',r.song)
  elif r(r'^(?P<show>.*?) S(?P<season>\d+)E(?P<episode>\d+)$') or r(r'^(.*?) (Se\.\s*(?P<season>\d+)\s*)?Ep\.\s*(?P<episode>\d+)$'):
    cfg.set('type','tvshow')
    cfg.set('show',r.show)
    if r.season and r.season!='0': cfg.set('season',int(r.season))
    cfg.set('episode',int(r.episode))
  elif r(r'^(?P<show>.*) S(?P<season>\d+) +(?P<song>.*?)$') or r(r'^(.*) Se\. *(?P<season>\d+) *(?P<song>.*?)$'):
    cfg.set('type','tvshow')
    cfg.set('show',r.show)
    cfg.set('season',int(r.season))
    cfg.set('song',r.song)
  elif r(r'^(?P<show>.*) (S(?P<season>\d+))?(V|Vol\. )(?P<episode>\d+)$'):
    cfg.set('type','tvshow')
    cfg.set('show',r.show)
    cfg.set('season',int(r.season))
    cfg.set('episode',int(r.episode))
  elif r(r'^(?P<show>.*) S(?P<season>\d+)D\d+$'):
    cfg.set('type','tvshow')
    cfg.set('show',r.show)
    cfg.set('season',int(r.season))
    cfg.set('episode','')
  cfg.sync()


def config_from_idxfile(cfg,idxfile):
  with open(idxfile, 'rt', encoding='utf-8-sig', errors='replace').read() as fp: idx=fp.read()
  timestamp=[]
  filepos=[]
  for l in idx.splitlines():
    if re.fullmatch(r'\s*#.*',l):
      continue
    elif re.fullmatch(r'\s*$',l):
      continue
    elif (m := re.fullmatch(r'\s*timestamp:\s*(?P<time>.*),\s*filepos:\s*(?P<pos>[0-9a-fA-F]+)\s*',l)) and (t := parse_time(m['time'])):
      timestamp.append(str(t))
      filepos.append(m['pos'])
    elif m := re.fullmatch(r'\s*id\s*:\s*(\w+?)\s*, index:\s*(\d+)\s*$',l):
      cfg.set('language' ,m[1]) # Convert to 3 character codes
      cfg.set('langindex',m[2])
    elif m := re.fullmatch(r'\s*(\w+)\s*:\s*(.*?)\s*',l):
      cfg.set(m[1],r[2])
    else:
      log.warning(f'{cfg.get("base","NOBASE","MAIN")}: Ignorning in {idxfile} uninterpretable line: {l}')
  cfg.set('timestamp',','.join(timestamp))
  cfg.set('filepos',','.join(filepos))
  cfg.sync()


def prepare_tivo(tivofile):
  if os.path.exists(tivofile+'.header'): return False
  if os.path.exists(tivofile+'.error'): return False
  mpgfile = tivofile[:-5]+'.mpg'
  if not readytomake(mpgfile,tivofile): return False

  if args.mak:
    do_call(['tivodecode','--mak',args.mak,'--out',mpgfile,tivofile],mpgfile)
    if os.path.exists(mpgfile) and os.path.getsize(mpgfile)>0: os.remove(tivofile)


def prepare_mpg(mpgfile):
  base = os.path.splitext(os.path.basename(mpgfile))[0]
  cfgfile=base+'.cfg'
  if not readytomake(cfgfile,mpgfile): return False
  cfg=AdvConfig(cfgfile)
  config_from_base(cfg,base)
  work_lock(cfgfile)

  track=1
  dgifile=f'{base} T{track:02d}.d2v'
  if not os.path.exists(dgifile):
    do_call(['dgindex', '-i', mpgfile, '-o', os.path.splitext(base)[0], '-fo', '0', '-ia', '3', '-om', '2', '-hide', '-exit'],base+'.d2v')
#    do_call(['DGIndexNV', '-i', mpgfile, '-a', '-o', dgifile, '-h', '-e'],dgifile)
  if not os.path.exists(dgifile): return
  cfg.setsection(f'TRACK{track:02d}')
  cfg.set('file',mpgfile)
  cfg.sync()
  config_from_dgifile(cfg,dgifile)

  r=regex.RegEx()
  for file in glob.iglob(f'{base} *'):
    m = re.fullmatch(re.escape(base)+r'\s+T[0-9a-fA-F][0-9a-fA-F]\s+(.*)\.(ac3|dts|mpa|mp2|wav|pcm)',file)
    if not m: continue
    feat=m[1]
    ext=m[2]
    track+=1
    cfg.setsection(f'TRACK{track:02d}')
    nf=f'{base} T{track:02d}.{ext}'
    os.rename(file,nf)
    cfg.set('file',nf)
    cfg.set('type','audio')
    cfg.set('extension',ext)
    cfg.set('quality',55)
    cfg.set('delay',0.0)
#    cfg.set('elongation',1.0)
#    cfg.set('normalize',False)
    cfg.set('features',feat)
    if r(r'\bDELAY (-?\d+)ms\b',feat): cfg.set('delay',float(r[0])/1000.0)
    if r(r'([_0-9]+)ch\b',feat):
      cfg.set('channels',r[0])
#      if r[0]=="3_2": cfg.set('downmix',2)
    if r(r'\b([\d.]+)(K|Kbps|bps)\b',feat):
      bps=int(r[0])
      if r[1][0]=="K": bps=bps*1000
      cfg.set('bit_rate',bps)
    if r(r'\b([0-9]+)bit\b',feat): cfg.set('bit_depth',r[0])
    if r(r'\b([0-9]+)rate\b',feat): cfg.set('sample_rate',r[0])
    if r(r'\b([a-z]{3})-lang\b',feat):  cfg.set('language',r[0])
    cfg.sync()

  if make_srt(cfg,track+1,[mpgfile]): track+=1

  if args.delete_source:
    os.remove(mpgfile)

  cfg.sync()
  work_unlock(cfgfile)

def prepare_mkv(mkvfile):
  base=os.path.splitext(os.path.basename(mkvfile))[0]
  cfgfile=base+'.cfg'
  if not readytomake(cfgfile,mkvfile): return False
  cfg=AdvConfig(cfgfile)
  config_from_base(cfg,base)
  work_lock(cfgfile)

  cfg.setsection('MAIN')

  try:
    chaps = ET.fromstring(subprocess.check_output(['mkvextract','chapters',mkvfile]).decode(errors='replace'))
    chap_uid=[]
    chap_time=[]
    chap_hidden=[]
    chap_enabled=[]
    chap_name=[]
    chap_lang=[]
    for chap in chaps.iter('ChapterAtom'):
      chap_uid.append(chap.find('ChapterUID').text)
      chap_time.append(str(parse_time(chap.find('ChapterTimeStart').text)))
      chap_hidden.append(chap.find('ChapterFlagHidden').text)
      chap_enabled.append(chap.find('ChapterFlagEnabled').text)
      chap_name.append(chap.find('ChapterDisplay').find('ChapterString').text)
      v = chap.find('ChapterDisplay').find('ChapterLanguage').text
      chap_lang.append(iso6392BtoT.get(v, v))
    cfg.set('chapter_delay',0.0)
    cfg.set('chapter_elongation',1.0)
    cfg.set('chapter_uid',';'.join(chap_uid))
    if chap_time: cfg.set('chapter_time',';'.join(chap_time))
    if chap_hidden: cfg.set('chapter_hidden',';'.join(chap_hidden))
    if chap_enabled: cfg.set('chapter_enabled',';'.join(chap_enabled))
    if chap_name: cfg.set('chapter_name',';'.join(chap_name))
    if chap_lang: cfg.set('chapter_language', ';'.join(chap_lang))
    cfg.sync()
  except ET.ParseError:
    log.warning(f'No valid XML chapters for {mkvfile}.')

  j = json.loads(subprocess.check_output(['mkvmerge','-J',mkvfile]).decode(errors='replace'))
  cont = j['container']
  cfg.set('container_type', cont['type'])

  for k,v in cont['properties'].items():
    if k=='duration':
      cfg.set('duration',int(v)/1000000000.0)
    else:
      cfg.set('container_property_'+k, v)

  skip_a_dts = False
  for track in j['tracks']:
    tid = track['id']+1
    cfg.setsection(f'TRACK{tid:02d}')
    cfg.set('mkvtrack',track['id'])
    cfg.set('type',track['type'])

    codec = track['codec']
    cfg.set('format', codec)

    if codec in ('V_MPEG2','MPEG-1/2',):
      cfg.set('extension','mpg')
      cfg.set('file',f'{base} T{tid:02d}.mpg')
      cfg.set('dgi_file',f'{base} T{tid:02d}.dgi')
    elif codec in ('V_MPEG4/ISO/AVC','MPEG-4p10/AVC/h.264',):
      cfg.set('extension','264')
      cfg.set('file',f'{base} T{tid:02d}.264')
#        cfg.set('t2c_file',f'{base} T{tid:02d}.t2c')
      cfg.set('dgi_file',f'{base} T{tid:02d}.dgi')
    elif codec in ('V_MS/VFW/FOURCC, WVC1','VC-1',):
      cfg.set('extension','wvc')
      cfg.set('file',f'{base} T{tid:02d}.wvc')
#        cfg.set('t2c_file',f'{base} T{tid:02d}.t2c')
      cfg.set('dgi_file',f'{base} T{tid:02d}.dgi')
    elif codec in ('A_AC3','A_EAC3','AC3/EAC3','AC-3/E-AC-3', 'AC-3','E-AC-3'):
      cfg.set('extension','ac3')
      cfg.set('file',f'{base} T{tid:02d}.ac3')
      cfg.set('quality',60)
      cfg.set('delay',0.0)
    elif codec in ('TrueHD','A_TRUEHD','TrueHD Atmos',):
      cfg.set('extension','thd')
      cfg.set('file',f'{base} T{tid:02d}.thd')
      cfg.set('quality',60)
      cfg.set('delay',0.0)
      skip_a_dts = True
    elif codec in ('DTS-HD Master Audio',):
      cfg.set('extension','dts')
      cfg.set('file',f'{base} T{tid:02d}.dts')
      cfg.set('quality',60)
      cfg.set('delay',0.0)
      skip_a_dts = True
    elif codec in ('A_DTS', 'DTS', 'DTS-ES', 'DTS-HD High Resolution', 'DTS-HD High Resolution Audio',):
      cfg.set('extension','dts')
      cfg.set('file',f'{base} T{tid:02d}.dts')
      cfg.set('quality',60)
      cfg.set('delay',0.0)
      if skip_a_dts:
        cfg.set('disable', True)
        skip_a_dts = False
    elif codec in ('A_PCM/INT/LIT','PCM',):
      cfg.set('extension','pcm')
      cfg.set('file',f'{base} T{tid:02d}.pcm')
      cfg.set('quality',60)
      cfg.set('delay',0.0)
    elif codec in ('S_VOBSUB','VobSub',):
      cfg.set('extension','idx')
      cfg.set('file',f'{base} T{tid:02d}.idx')
      cfg.set('delay',0.0)
      cfg.set('elongation',1.0)
    elif codec in ('S_HDMV/PGS','HDMV PGS','PGS',):
      cfg.set('extension','sup')
      cfg.set('file',f'{base} T{tid:02d}.sup')
      cfg.set('delay',0.0)
      cfg.set('elongation',1.0)
    elif codec in ('SubRip/SRT',):
      cfg.set('extension','srt')
      cfg.set('file',f'{base} T{tid:02d}.srt')
      cfg.set('delay',0.0)
      cfg.set('elongation',1.0)
    elif codec in ('A_MS/ACM',):
      cfg.set('disable',True)
    else:
      log.warning(f'{cfg.get("base","NOBASE","MAIN")}: Unrecognized track type {codec} in {mkvfile}')
      cfg.set('disable',True)


    for k,v in track['properties'].items():
      if k == 'language':
        cfg.set('language', iso6392BtoT.get(v, v))
      elif k == 'display_dimensions':
        s = v.split('x')
        cfg.set('display_width',int(s[0]))
        cfg.set('display_height',int(s[1]))
      elif k == 'pixel_dimensions':
        s = v.split('x')
        cfg.set('pixel_width',int(s[0]))
        cfg.set('pixel_height',int(s[1]))
      # elif k == 'default_track':
      #   cfg.set('defaulttrack', int(v)!=0)
      elif k == 'forced_track':
        cfg.set('forcedtrack', int(v)!=0)
      elif k == 'default_duration':
        cfg.set('frameduration',int(v)/1000000000.0)
      elif k == 'track_name':
        cfg.set('trackname',v)
      # elif k == 'minimum_timestamp':
      #   cfg.set('delay',int(v)/1000000000.0)
      elif k == 'audio_sampling_frequency':
        cfg.set('samplerate',int(v))
      elif k == 'audio_channels':
        cfg.set('channels',int(v))
        # if int(v)>2: cfg.set('downmix',2)
      else:
        cfg.set('property_' + k, v)

  cfg.sync()

  call=[]
  for vt in sorted([t for t in cfg.sections() if t.startswith('TRACK') and not cfg.get('disable',section=t)]):
    cfg.setsection(vt)
    file=cfg.get('file',None)
    mkvtrack=cfg.get('mkvtrack',-1)
    if args.keep_video_in_mkv and cfg.get('type',None)=='video':
      cfg.set('extension','mkv')
      cfg.set('file',mkvfile)
      continue
    if args.keep_audio_in_mkv and cfg.get('type',None)=='audio':
      cfg.set('extension','mkv')
      cfg.set('file',mkvfile)
      continue
    if file and not os.path.exists(file) and mkvtrack>=0:
      call.append(f'{mkvtrack:d}:{file}')
  if call: do_call(['mkvextract', 'tracks', mkvfile] + call)
  cfg.sync()

  for vt in sorted([t for t in cfg.sections() if t.startswith('TRACK') and not cfg.get('disable',section=t) and cfg.get('type',section=t)=='video']):
    cfg.setsection(vt)
    file=cfg.get('file')
    if make_srt(cfg,tid+1,[file]): tid+=1
  cfg.sync()

  call=[]
  for vt in sorted([t for t in cfg.sections() if t.startswith('TRACK') and not cfg.get('disable',section=t)]):
    cfg.setsection(vt)
    t2cfile=cfg.get('t2c_file',None)
    mkvtrack=cfg.get('mkvtrack',-1)
    if t2cfile and not os.path.exists(t2cfile) and mkvtrack>=0: call.append(f'{mkvtrack:d}:{t2cfile}')
  if call: do_call(['mkvextract', 'timecodes_v2', mkvfile] + call)
  cfg.sync()

  work_unlock(cfgfile)

  for vt in sorted([t for t in cfg.sections() if t.startswith('TRACK') and not cfg.get('disable',section=t)]):
    cfg.setsection(vt)
    t2cfile=cfg.get('t2c_file',None)
    if not t2cfile: continue
    with open(t2cfile,'rt', encoding='utf-8-sig', errors='replace') as fp:
      t2cl = [float(l) for l in fp.readlines() if l.strip(string.whitespace).strip(string.digits) in ['','.']]
    if len(t2cl)==0: continue
#    oframes = cfg.get('frames',-1)
#    frames = len(t2cl)-1
#    if oframes>0 and frames != oframes:
#      log.warning(f'Timecodes changed frames in "{file}" from {oframes:d} to {frames:d}')
#    cfg.set('frames',frames)
    duration=t2cl[-1]/1000.0
    oduration=cfg.get('duration',-1.0)
    if oduration>0 and oduration!=duration:
      log.warning(f'Encoding changed duration in "{file}" from {oduration:f} to {duration:f}')
    cfg.set('duration',duration)
    cfg.sync()

  for vt in sorted([t for t in cfg.sections() if t.startswith('TRACK') and not cfg.get('disable',section=t) and cfg.get('type',section=t)=='subtitles']):
    cfg.setsection(vt)
    file=cfg.get('file')
    ext=cfg.get('extension')
    if ext=='.sub':
      config_from_idxfile(cfg,os.path.splitext(file)[0]+'.idx')
      # remove idx file

  if args.delete_source:
    os.remove(mkvfile)

def prepare_vob(vobfile):
  base=os.path.splitext(os.path.basename(vobfile))[0]
  r=regex.RegEx()
  if r(r'^(.*)_(\d+)$',base):
    if int(r[1])!=1: return
    base=r[0]
  cfgfile=base+'.cfg'
  if not readytomake(cfgfile,vobfile): return False
  cfg=AdvConfig(cfgfile)
  config_from_base(cfg,base)
  work_lock(cfgfile)

#  TODO
#  dgindex & rename

#  vob -> idx, sub
#  basefile=myjoin(root, file[:-6])
#  idxfile=basefile+".idx"
#  avsfile=basefile+".video.avs"
#  if os.path.exists(idxfile): continue
#  ifofile=basefile+"_0.ifo"
#  if os.path.exists(ifofile) and os.path.getsize(ifofile)>0:
#    pgc=1
#    trueifofile=ifofile
#  elif ifofile[-13:-8] == "_PGC_" and os.path.exists(ifofile[:-13]+"_0.ifo"):
#    pgc=int(ifofile[-8:-6])
#    trueifofile=ifofile[:-13]+"_0.ifo"
#  else:
#    continue
#
#  vobsubfile=r'C:\Windows\Temp\vobsub'
#  log.info('Generating "%(vobfile)s" -> "%(idxfile)s"' % locals())
#  open(vobsubfile,'wt').write('%(ifofile)s\n%(basefile)s\n%(pgc)d\n0\nALL\nCLOSE\n' % locals())
#  if trueifofile!=ifofile: copyfile(trueifofile,ifofile)
#  do_call([r'C:\Windows\SysWOW64\rundll32.exe','vobsub.dll,Configure',vobsubfile],vobsubfile)
#  if trueifofile!=ifofile: os.remove(ifofile)
##  if not os.path.exists(idxfile): open(idxfile,'wt').truncate(0)

#  if make_srt(cfg,track+1,vobfiles): track+=1

#  chapter txt -> cfg
  cfg.sync()
  work_unlock(cfgfile)
#  if args.delete_source:
#    os.remove(vobfile)

def config_from_dgifile(cfg):
  file = cfg.get('file', None)
  dgifile = cfg.get('dgi_file', None)
  if not file or not dgifile: return
  logfile = os.path.splitext(file)[0]+'.log'
  r=regex.RegEx()

  trans = str.maketrans(string.ascii_uppercase,string.ascii_lowercase,string.whitespace)
  while True:
    time.sleep(1)
    if not os.path.exists(logfile): continue
    with open(logfile,'rt', encoding='utf-8-sig', errors='replace') as fp: log = fp.read()
    for l in log.splitlines():
      if not r('^([^:]*):(.*)$',l):
        log.warning(f'Unrecognized DGIndex log line: "{repr(l)}"')
        continue
      k='dg'+r[0].translate(trans)
      v=r[1].strip()
      if not v: continue
      cfg.set(k, cfg.get(k) + ";" + v if cfg.has(k) else v)
    if cfg.get('dginfo')=='Finished!': break
  os.remove(logfile)
  cfg.sync()

  with open(dgifile, 'rt', encoding='utf-8-sig', errors='replace') as fp: dgi=fp.read()
  dgip=dgi.split('\n\n')
  if len(dgip)!=4:
    log.error('Malformed index file ' + dgifile)
    open(dgifile,'w').truncate(0)
    return
  r=regex.RegEx()
  if r(r'^DG(AVC|MPG|VC1)IndexFileNV(14|15|16)',dgip[0]):
    if not r(r'\bCLIP\ *(?P<left>\d+) *(?P<right>\d+) *(?P<top>\d+) *(?P<bottom>\d+)',dgip[2]):
      log.error('No CLIP in ' + dgifile)
      open(dgifile,'w').truncate(0)
      return
    cl=int(r.left)
    cr=int(r.right)
    ct=int(r.top)
    cb=int(r.bottom)
    cl=cr=ct=cb=0
    if not r(r'\bSIZ *(?P<sizex>\d+) *x *(?P<sizey>\d+)',dgip[3]):
      log.error('No SIZ in ' + dgifile)
      open(dgifile,'w').truncate(0)
      return
    psx=int(r.sizex)
    psy=int(r.sizey)

    if cfg.has('dgsar'):
      sarf=cfg.get('dgsar')
    elif cfg.has('display_width') and cfg.has('display_height') and cfg.has('pixel_width') and cfg.has('pixel_height'):
      sarf=Fraction(cfg.get('display_width')*cfg.get('pixel_height'),cfg.get('display_height')*cfg.get('pixel_width'))
#    elif r(r'^\s*(\d+)\s*x\s*(\d+)\s*XXX\s*(\d+)\s*:(\d+)',cfg.get('dgdisplaysize','')+'XXX'+cfg.get('dgaspectratio','')):
#      sarf=Fraction(int(r[1])*int(r[2]),int(r[0])*int(r[3]))
#    elif r(r'^\s*(\d+)\s*x\s*(\d+)\s*XXX\s*(\d+)\s*:(\d+)',cfg.get('dgcodedsize','')+'XXX'+cfg.get('dgaspectratio','')):
#      sarf=Fraction(int(r[1])*int(r[2]),int(r[0])*int(r[3]))
#    elif cfg.has('display_width') and cfg.has('display_height') and r(r'^\s*(\d+)\s*x\s*(\d+)\s*$',cfg.get('picture_size','')):
#      sarf=Fraction(cfg.get('display_width')*int(r[0]),cfg.get('display_height')*int(r[1]))
    else:
      log.warning(f'Guessing 1:1 SAR for {dgifile}')
      sarf=Fraction(1,1)

    if not r(r'\bORDER *(?P<order>\d+)',dgip[3]):
      log.error('No ORDER in ' + dgifile)
      open(dgifile,'w').truncate(0)
      return
    fio=int(r.order)
    if not r(r'\bFPS *(?P<num>\d+) */ *(?P<denom>\d+) *',dgip[3]):
      log.error('No FPS in ' + dgifile)
      open(dgifile,'w').truncate(0)
      return
    frf=Fraction(int(r.num),int(r.denom))
    if not r(r'\b(?P<ipercent>\d*\.\d*)% *FILM',dgip[3]):
      log.error('No FILM in ' + dgifile)
      open(dgifile,'w').truncate(0)
      return
    ilp = float(r.ipercent)/100.0

    if fio == 0:
      ilt = 'PROGRESSIVE'
    elif ilp>0.5:
      ilt = 'FILM'
    else:
      ilt = 'INTERLACE'

    if not r(r'\bPLAYBACK *(?P<playback>\d+)',dgip[3]): # ALSO 'CODED' FRAMES
      log.error('No PLAYBACK in ' + dgifile)
      open(dgifile,'w').truncate(0)
      return
    frames = int(r.playback)
  elif r(r'^DGIndexProjectFile16',dgip[0]):
    if not r(r'^FINISHED\s+([0-9.]+)%\s+(.*?)\s*$',dgip[3]): return False
    ilp=float(r[0])/100.0
    ilt=r[1]
    if not r(r'\bAspect_Ratio=(\d+):(\d+)',dgip[1]): return False
    arf=Fraction(int(r[0]),int(r[1]))
    if not r(r'\bClipping=\ *(\d+) *, *(\d+) *, *(\d+) *, *(\d+)',dgip[1]): return False
    cl,cr,ct,cb=[int(r[i]) for i in range(4)]
    if not r(r'\bPicture_Size= *(\d+)x(\d+)',dgip[1]): return False
    psx,psy=[int(r[i]) for i in range(2)]
    sarf=arf/Fraction(psx,psy)
    if not r(r'\bField_Operation= *(\d+)',dgip[1]): return False
    fio=int(r[0])
    if not r(r'\bFrame_Rate= *(\d+) *\((\d+)/(\d+)\)',dgip[1]): return False
    frm=float(r[0])/1000.0
    frf=Fraction(int(r[1]),int(r[2]))

    frames=0
    for l in dgip[2].splitlines():
      if r(r'^([0-9a-f]+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(?P<flags>([0-9a-f]+ +)*[0-9a-f]+)\s*$',l):
        frames += len(r[7].split())
  else:
    log.error('Unrecognize index file ' + dgifile)
    open(dgifile,'w').truncate(0)
    return

  cfg.set('type', 'video')
#  cfg.set('file', dgip[1].splitlines()[0])
  cfg.set('dgi_file', dgifile)
  cfg.set('interlace_type', ilt)
  cfg.set('interlace_type_fraction', ilp)
  cfg.set('field_operation', fio)
  cfg.set('frame_rate_ratio', str(frf))

  #cfg.set('out_format', 'h264')
  cfg.set('out_format', 'h265')

  cfg.set('crop', 'auto' if cl==cr==ct==cb==0 else '0,0,0,0')
#  cfg.set('aspect_ratio',str(arf))
  cfg.set('picture_size', f"{psx:d}x{psy:d}")

  cfg.set('sample_aspect_ratio',str(sarf))
  mbs = int(math.ceil((psx-cl-cr)/16.0))*int(math.ceil((psy-ct-cb)/16.0))
  cfg.set('macroblocks',mbs)
  cfg.set('avc_profile', 'high')
  cfg.set('x265_preset', 'slow')
  #cfg.set('x265_tune', 'animation')
  #cfg.set('x265_output_depth', '8')
  if mbs<=1620: # 480p@30fps; 576p@25fps
    cfg.set('avc_level',3.0)
    cfg.set('x264_rate_factor',16.0)
    cfg.set('x265_rate_factor',18.0)
  elif mbs<=3600: # 720p@30fps
    cfg.set('avc_level',3.1)
    cfg.set('x264_rate_factor',18.0)
    cfg.set('x265_rate_factor',20.0)
  elif mbs<=8192: # 1080p@30fps
    cfg.set('avc_level',4.0)
    cfg.set('x264_rate_factor',19.0)
    cfg.set('x265_rate_factor',21.0)
  elif mbs<=22080: # 1080p@72fps; 1920p@30fps
    cfg.set('avc_level',5.0)
    cfg.set('x264_rate_factor',20.0)
    cfg.set('x265_rate_factor',22.0)
  else: # 1080p@120fps; 2048@30fps
    cfg.set('avc_level',5.1)
    cfg.set('x264_rate_factor',21.0)
    cfg.set('x265_rate_factor',24.0)

  if frames!=0:
    cfg.set('frames', frames)
  cfg.sync()
  return True


def build_indices(cfg):
  for vt in sorted([t for t in cfg.sections() if t.startswith('TRACK') and not cfg.get('disable',section=t) and cfg.get('type',section=t)=='video']):
    cfg.setsection(vt)
    file=cfg.get('file')
    dgifile=cfg.get('dgi_file', None)
    if not dgifile or os.path.exists(dgifile): continue
    if dgifile.endswith('.dgi'):
      do_call(['DGIndexNV', '-i', cfg.get('file'), '-o', dgifile, '-h', '-e'],dgifile)
    elif dgifile.endswith('.d2v'):
      do_call(['dgindex', '-i', cfg.get('file'), '-o', os.path.splitext(dgifile)[0], '-fo', '0', '-ia', '3', '-om', '2', '-hide', '-exit'],dgifile)
    else:
      continue

    config_from_dgifile(cfg)

def build_subtitle(cfg):
  infile = cfg.get('file')
  inext = cfg.get('extension')
  d=cfg.get('delay',0.0)
  e=cfg.get('elongation',1.0)

  if os.path.getsize(infile)==0:
    pass
  elif inext=='srt':
    outfile = os.path.splitext(infile)[0]+'.ttxt'
    cfg.set('out_file', outfile)
    if os.path.exists(outfile): return # Should be not readytomake(outfile,)
    with open(infile, 'rt', encoding='utf-8-sig', errors='replace') as i, open('temp.srt', 'wt', encoding='utf-8', errors='replace') as o:
      inp=i.read()

      for l in inp.split('\n\n'):
        if not l.strip():
          continue
        elif (m := re.fullmatch(r'(?s)(?P<beg>\s*\d*\s*)(?P<time1>.*)(?P<mid> --> )(?P<time2>.*)',l)) and (t1 := parse_time(m['time1'])) and (t2 := parse_time(m['time2'])) and (s1 := t1*e+d)>=0 and (s2 := t2*e+d)>=0:
          o.write(f'{m["beg"]}{unparse_time(s1)}{m["mid"]}{unparse_time(s2)}{m["end"]}\n\n')
        else:
          log.warning(f'Unrecognized line in {infile}: {repr(l)}')

    do_call(['mp4box','-ttxt','temp.srt'],outfile)
    if os.path.exists('temp.ttxt'): os.rename('temp.ttxt',outfile)
    if os.path.exists('temp.srt'): os.remove('temp.srt')
  elif inext=='sup' and os.path.getsize(infile)<1024:
    outfile = os.path.splitext(infile)[0]+'.idx'
  elif inext=='sup':
    outfile = os.path.splitext(infile)[0]+'.idx'
    cfg.set('out_file', outfile)
    if os.path.exists(outfile): return  # Should be not readytomake(outfile,)
    call = ['bdsup2sub++']
    call += ['--resolution','keep']
    if d!=0: call += ['--delay',str(d*1000.0)]
    fps = cfg.get('frame_rate_ratio_out',cfg.get('frame_rate_ratio',section='TRACK01'),section='TRACK01')
    if fps in [24, 24.0, Fraction(24000,1001)]:
      call += [ '--fps-target', '24p' ]
    elif fps in [25, 25.0, Fraction(25000,1001)]:
      call += [ '--fps-target', '25p' ]
    elif fps in [30, 30.0, Fraction(30000,1001)]:
      call += [ '--fps-target', '30p' ]
    call += ['--output',outfile,infile]
    do_call(call,outfile) # '--fix-invisible',
  elif (d!=0.0 or e!=1.0) and inext=='idx':
    outfile = os.path.splitext(infile)[0]+'.adj'+os.path.splitext(infile)[1]
    cfg.set('out_file', outfile)
    if not os.path.exists(os.path.splitext(infile)[0]+'.adj.sub'):
      shutil.copy(os.path.splitext(infile)[0]+'.sub',os.path.splitext(infile)[0]+'.adj.sub')
    if os.path.exists(outfile): return  # Should be not readytomake(outfile,)
    with open(infile, 'rt', encoding='utf-8', errors='replace') as i, open(outfile, 'wt', encoding='utf-8', errors='replace') as o:
      for l in i:
        if (m := re.fullmatch(r'(?s)(?P<beg>\s*timestamp:\s*)\b(?P<time>.*\d)\b(?P<end>.*)',l)) and (t := parse_time(m['time'])):
          s = t*e+d
          if s >= 0: o.write(f'{m["beg"]}{unparse_time(s)}{m["end"]}')
        else:
          o.write(l)
  elif (d!=0.0 or e!=1.0):
    outfile = infile
    cfg.set('out_file', outfile)
    log.warning(f'Delay and elongation not implemented for subtitles type "{infile}"')
  else:
    outfile = infile
    cfg.set('out_file', outfile)

  if os.path.getsize(infile)==0 or not os.path.exists(outfile):
    cfg.set('disable',True)
  cfg.sync()


def build_audio(cfg):
  infile = cfg.get('file')
  inext = cfg.get('extension')
  outfile = cfg.get('out_file',f'{cfg.get("base",section="MAIN")} T{cfg.getsection()[5:]}.m4a')
  cfg.set('out_file',outfile)
  cfg.sync()
  if not readytomake(outfile,infile): return False

  r=regex.RegEx()

  if inext in (): # ('dts', 'thd'):
    call = [ 'dcadec', '-6', infile, '-']
  else:
    call = [ 'eac3to', infile]
    if inext=='mkv': call.append(f"{cfg.get('mkvtrack')+1}:")
    call.append('stdout.wav')
    # call.append('-no2ndpass')
    call.append('-log=nul')
    if cfg.get('delay',0.0)!=0.0: call.append(f'{cfg.get("delay")*1000.0:+.0f}ms')
    if cfg.get('elongation',1.0)!=1.0: log.warning(f'Audio elongation not implemented')
    # if cfg.get('channels')==7: call.append('-0,1,2,3,5,6,4')

    if cfg.get('downmix')==6: call.append('-down6')
    elif cfg.get('downmix')==2: call.append('-downDpl')
    elif cfg.has('downmix'): log.warning(f'Invalid downmix "{cfg.get("downmix"):d}"')

    if cfg.get('normalize',False): call.append('-normalize')

  call += [ '|', 'qaac64', '--threading', '--ignorelength', '--no-optimize', '--tvbr', str(cfg.get('quality',60)), '--quality', '2', '-', '-o', outfile]

  res=do_call(call, outfile)
  if res and r(r'\bwrote (\d+\.?\d*) seconds\b',res):
    cfg.set('duration',float(r[0]))
  if cfg.has('duration') and cfg.has('duration',section='MAIN') and abs(cfg.get('duration')-cfg.get('duration',section='MAIN'))>0.5:
    log.warning(f'Audio track "{infile}" duration differs (elongation={cfg.get("duration")/cfg.get("duration",section="MAIN"):f})')
  cfg.sync()
  return True


def build_video(cfg):
  infile = cfg.get('file')
  inext = cfg.get('extension')
  dgifile = cfg.get('dgi_file', None)

  outfile = cfg.get('out_file')
  if outfile == None:
    baseout = f'{cfg.get("base",section="MAIN")} T{cfg.getsection()[5:]}'
    if cfg.get('out_format') == 'h264':
      outext = '264'
    elif cfg.get('out_format') == 'h265':
      outext = '265'
    else:
      log.error(f'{infile}: Unrecognized output format: {cfg.get("out_format", "UNSPECIFIED")}')
      return False
    outfile = baseout + '.' + outext
    cfg.set('out_file',outfile)
  avsfile = cfg.get('avs_file',os.path.splitext(os.path.basename(infile))[0] +'.avs' )
  cfg.set('avs_file',avsfile)
  cfg.sync()

  if not readytomake(outfile,infile,dgifile): return False

  r=regex.RegEx()
  avs=''

  ilt=cfg.get('interlace_type')
  fri=cfg.get('frame_rate_ratio')

  procs=cfg.get('processors',6)
  if procs!=1: avs += f'SetMTMode(5,{procs:d})\n'
  avs += 'SetMemoryMax(1024)\n'
  if dgifile.endswith('.d2v'):
    avs+=f'DGDecode_mpeg2source("{os.path.abspath(dgifile)}", info=3, idct=4, cpu=3)\n'
  elif dgifile.endswith('.dgi'):
    deint = 1 if ilt in ['VIDEO', 'INTERLACE'] else 0
    avs+=f'DGSource("{os.path.abspath(dgifile)}", deinterlace={deint:d})\n'
  else:
    log.warning(f'No valid video index file from "{infile}"')
    return False

#  avs+=f'ColorMatrix(hints = true, interlaced=false)\n'

  unblock=cfg.get('unblock',None)
  if unblock == 'cartoon' or (unblock==True and cfg.get('x264_tune', None)=='animation'):
    avs += 'unblock(cartoon=true)'
  elif unblock == 'photo' or (unblock==True and cfg.has('x264_tune')):
    avs += 'unblock(photo=true)'
  elif unblock == 'normal' or unblock==True:
    avs += 'unblock()'

  if ilt in ['FILM']:
    fro=fri*Fraction(4,5)
#    cfg.set('frames',math.ceil(cfg.get('frames')*5.0/4.0))
    avs+='tfm().tdecimate(hybrid=1)\n'
#    avs+=f'tfm().tdecimate(hybrid=1,d2v="{os.path.abspath(dgifile)}")\n'
#    avs+=f'Telecide(post={0 if lp>0.99 else 2:d},guide=0,blend=True)'
#    avs+=f'Decimate(mode={0 if lp>0.99 else 3:d},cycle=5)'
#  elif ilt in ['VIDEO', 'INTERLACE']:
#    fro = fri
#    avs+=f'Bob()\n'
#    avs+=f'TomsMoComp(1,5,1)\n'
#    avs+=f'LeakKernelDeint()\n'
#    avs+=f'TDeint(mode=2, type={3 if cfg.get('x264_tune','animation' if cfg.get('genre',section='MAIN') in ['Anime', 'Animation'] else 'film')=='animation' else 2:d}, tryWeave=True, full=False)\n'
  else:
    fro = fri
  cfg.set('frame_rate_ratio_out',fro)

  if cfg.has('crop'):
    if r(r'^\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*$',cfg.get('crop')):
      cl,cr,ct,cb=[int(r[i]) for i in range(4)]
      if r(r'^\s*(\d+)\s*x\s*(\d+)\s*$',cfg.get('picture_size','')):
        px, py=[int(r[i]) for i in range(2)]
        if (px-cl-cr) % 2!=0: cr+=1
        if (py-ct-cb) % 2!=0: cb+=1
      if cl or cr or ct or cb:
        avs+=f'crop({cl:d},{ct:d},{-cr:d},{-cb:d},align=true)\n'
    elif cfg.get('crop')=='auto':
      avs+='autocrop(threshold=30,wMultOf=2, hMultOf=2,samples=51, mode=0)\n'

  blocksize=16 if cfg.get('macroblocks',0)>1620 else 8
  if procs!=1: avs+='SetMTMode(2)\n'

  degrain=cfg.get('degrain',3)
  if degrain>=1: # or ilt in ['VIDEO', 'INTERLACE']
    avs+='super = MSuper(planar=true)\n'
    avs+=f'bv1 = MAnalyse(super, isb = true,  delta = 1, blksize={blocksize:d}, overlap={blocksize//2:d})\n'
    avs+=f'fv1 = MAnalyse(super, isb = false, delta = 1, blksize={blocksize:d}, overlap={blocksize//2:d})\n'
  if degrain>=2:
    avs+=f'bv2 = MAnalyse(super, isb = true,  delta = 2, blksize={blocksize:d}, overlap={blocksize//2:d})\n'
    avs+=f'fv2 = MAnalyse(super, isb = false, delta = 2, blksize={blocksize:d}, overlap={blocksize//2:d})\n'
  if degrain>=3:
    avs+=f'bv3 = MAnalyse(super, isb = true,  delta = 3, blksize={blocksize:d}, overlap={blocksize//2:d})\n'
    avs+=f'fv3 = MAnalyse(super, isb = false, delta = 3, blksize={blocksize:d}, overlap={blocksize//2:d})\n'
  if degrain>0:
    arg = ",".join([f"bv{i:d},fv{i:d}" for i in range(1, degrain+1)])
    avs+=f'MDegrain{degrain:d}(super,thSAD=400,planar=true,{arg})\n'
#  if ilt in ['VIDEO', 'INTERLACE']:
#    avs+=f'MFlowFps(super, bv1, fv1, num={fro.numerator:d}, den={fro.denominator:d}, ml=100)\n'
  if procs!=1: avs+='Distributor()\n'

  if not os.path.exists(avsfile) or os.path.getmtime(cfg.filename)>os.path.getmtime(avsfile):
    with open(avsfile, 'wt', encoding='utf-8', errors='replace') as fp: fp.write(avs)
    log.debug(f'Created AVS file: {repr(avs)}')

  call = ['avs2pipemod', '-y4mp', avsfile, '|' ]

  if cfg.get('out_format') == 'h264':
    call += [ 'x264', '--demuxer', 'y4m', '-']
    call += ['--preset', cfg.get('x264_preset', 'veryslow')]
    call += ['--tune', cfg.get('x264_tune', 'film')]
    call += ['--crf', cfg.get('x264_rate_factor', 20.0)]
    if cfg.has('avc_profile'): call += ['--profile', cfg.get('avc_profile')]
    if cfg.has('avc_level'): call += ['--level', cfg.get('avc_level')]
    if not cfg.get('x264_deterministic',False): call += ['--non-deterministic']
    if not cfg.get('x264_fast_pskip',False): call += ['--no-fast-pskip']
    if not cfg.get('x264_dct_decimate',False): call += ['--no-dct-decimate']
    # if cfg.has('t2cfile'): call += ['--timebase', '1000', '--tcfile-in', cfg.get('t2cfile')]
    # if cfg.get('deinterlace','none')=='none' and cfg.has('frames'): call += ['--frames', cfg.get('frames')]
  elif cfg.get('out_format') == 'h265':
    call += ['x265', '--input', '-', '--y4m']
    call += ['--preset', cfg.get('x265_preset', 'slow')]
    call += ['--crf', cfg.get('x265_rate_factor', 24.0)]
    call += ['--pmode', '--pme']
    if cfg.has('x265_tune'): call += ['--tune', cfg.get('x265_tune')]
    if cfg.has('x265_bit_depth'): call += ['--output-depth', cfg.get('x265_output_depth')]
    # --display-window <left,top,right,bottom> Instead of crop?
  else:
    log.error(f'{file}: Unrecognized output format "{cfg.get("out_format", "UNSPECIFIED")}"')
    return False

  call += ['--fps', str(fro)]
  sarf=cfg.get('sample_aspect_ratio')
  if isinstance(sarf,Fraction): call += ['--sar', f'{sarf.numerator:d}:{sarf.denominator:d}']
  call += [ '--output', outfile ]

  cfg.sync()
  res=do_call(call,outfile)
  if res and r(r'\bencoded (\d+) frames\b',res):
    cfg.sync()
    frames=int(r[0])
    oframes = int(fro/fri*cfg.get('frames')) # Adjust oframes for difference between frame-rate-in and frame-rate-out
    if cfg.has('frames') and abs(frames-oframes)>2:
      log.warning(f'Encoding changed frames in "{infile}" from {oframes:d} to {frames:d}')
    cfg.set('frames',frames)
    cfg.set('duration',float(int(r[0])/fro))
    mdur=cfg.get('duration',cfg.get('duration'),section='MAIN')
    if abs(cfg.get('duration')-mdur)>60.0:
      log.warning(f'Video track "{infile}" duration differs (elongation={cfg.get("duration")/mdur:f})')
  cfg.sync()
  return True


def build_result(cfg):
  r=regex.RegEx()
  for track in sorted([t for t in cfg.sections() if t.startswith('TRACK') and not cfg.get('disable',section=t)]):
    cfg.setsection(track)
    if cfg.get('type')=='audio' and cfg.has('language') and cfg.has('audio_languages',section='MAIN') and cfg.get('language') not in cfg.get('audio_languages',section='MAIN').split(";"): continue
    if cfg.get('type')=='video' and cfg.has('macroblocks'):
      cfg.set('hdvideo', cfg.has('macroblocks') >= 3600, section='MAIN')

    file=cfg.get('file')
    outfile=cfg.get('out_file',None)
    if not outfile: return False
    if not os.path.exists(outfile): return False
    if os.path.getsize(outfile)==0: return False

  cfg.setsection('MAIN')
  base=cfg.get('base')

  outfile = make_filename(cfg.items())
  if not outfile:
    log.error(f"Unable to generate filename for {cfg.items()}.")
    return
  if args.outdir: outfile = os.path.join(args.outdir,outfile + ".mp4")

  infiles=[cfg.filename]
  coverfiles=[]
  if cfg.has('coverart'):
    for c in cfg.get('coverart','').split(';'):
      if os.path.dirname(c)==None and args.artdir:
        c = os.path.join(args.artdir,c)
      if os.path.exists(c):
        coverfiles.append(c)
      cfg.set('coverart',';'.join(coverfiles))
  infiles+=coverfiles

  call=['mp4box', '-new', outfile]
  vts=0
  ats=0
  sts=0
  mdur=cfg.get('duration',None,section='MAIN')
  for track in sorted([t for t in cfg.sections() if t.startswith('TRACK') and not cfg.get('disable',section=t)]):
    cfg.setsection(track)
    if cfg.get('type')=='audio' and cfg.has('language') and cfg.has('audio_languages',section='MAIN') and cfg.get('language') not in cfg.get('audio_languages',section='MAIN').split(";"): continue
    if cfg.hasno('out_file'): continue
    of = cfg.get('out_file')
    dur = cfg.get('duration')
    if mdur and dur:
      if abs(mdur-dur)>0.5 and abs(mdur-dur)*200>mdur:
        log.warning(f'Duration of "{base}" ({mdur:f}s) deviates from track {of} duration({dur:f}s).')

    call+=['-add',of]
    infiles.append(of)

    name = cfg.get('name', cfg.get('trackname'))
    if name: call[-1]+=':name='+name

    if cfg.has('language'): call[-1]+=':lang='+cfg.get('language')
    if cfg.get('frame_rate_ratio_out'): call[-1] += ':fps=' + str(float(cfg.get('frame_rate_ratio_out')))
    if mdur: call[-1] += ':dur=' + str(float(mdur))
    if cfg.get('type')=='audio':
      ats += 1
      if not cfg.get('defaulttrack',ats==1): call[-1]+=':disable'

    if cfg.get('type')=='video':
      vts += 1
#      if not cfg.get('defaulttrack',vts==1): call[-1]+=':disable'
    if cfg.get('type')=='subtitle':
      sts += 1
#      if not cfg.get('defaulttrack',sts==1): call[-1]+=':disable'

  if not readytomake(outfile,*infiles): return False

  if vts+ats+sts>18:
    log.warning(f'Result for "{base}" has {tracks:d} tracks.')

  cfg.setsection('MAIN')
  cfg.set('tool', f'{prog} {version} on {time.strftime("%A, %B %d, %Y, at %X")}')
  cfg.sync()
  do_call(call,outfile)

  its = { k:cfg.get(k) for k in cfg.items() }
  set_meta_mutagen(outfile, its)
  set_chapters_cmd(outfile, its)
  cfg.sync()
  return True

def main():
#    if os.path.getmtime(sys.argv[0])>progmodtime:
#      exec(compile(open(sys.argv[0]).read(), sys.argv[0], 'exec')) # execfile(sys.argv[0])

  for d in sources:
    for f in sorted(os.listdir(d)):
      if not os.path.isfile(os.path.join(d,f)):
        continue
      elif f.endswith(('.TIVO','.tivo','.TiVo')):
        prepare_tivo(os.path.join(d,f))
      elif f.endswith(('.MPG','.MPEG','.mpg','.mpeg')):
        prepare_mpg(os.path.join(d,f))
      elif f.endswith(('.VOB','.vob')):
        prepare_vob(os.path.join(d,f))
      elif f.endswith(('.MKV','.mkv')):
        prepare_mkv(os.path.join(d,f))
      else:
        log.warning(f'Source file type not recognized "{os.path.join(d,f)}"')

  for f in glob.iglob('*.cfg'):
    cfg = AdvConfig(f)
    if not cfg: continue
    cfg.setsection("MAIN")

    title = cfg.get('title',cfg.get('show', cfg.get('base')))

    season = cfg.get('season')
    season = f' S{season:d}' if isinstance(season, int) else ""

    fn = f'{cfg.get("show") or ""}{season}'

    descpath = os.path.join(args.descdir, f'{fn}.txt')
    its = get_meta_local(title, cfg.get('season'), cfg.get('episode'), descpath)
    if 'comment' in its:
      cfg.set('comment',semicolon_join(cfg.get('comment',None), its['comment']))
      del its['comment']
    cfg.item_defs(its)

    its = get_meta_omdb(title, cfg.get('season'), cfg.get('episode'),
      os.path.join(args.artdir, f'{fn}.jpg'),
      cfg.get('omdb_id'), cfg.get('omdb_status'), args.omdbkey)
    if 'comment' in its:
      cfg.set('comment',semicolon_join(cfg.get('comment',None), its['comment']))
      del its['comment']
    cfg.item_defs(its)

    coverfiles = (i for i in glob.iglob(os.path.join(args.artdir, f'{fn}*')) if os.path.splitext(i)[1].casefold() in { '.jpg', '.jpeg', '.png'} )
    ufn = ''.join([c for c in fn.strip().upper() if c.isalnum()])
    its = { 'year': f'_{ufn}YEAR_'
          , 'genre': f'_{ufn}GENRE_'
          , 'description': f'_{ufn}DESC_'
          , 'coverart': ';'.join(coverfiles) }
    cfg.item_defs(its)

    cfg.sync()
    build_result(cfg)

  for f in glob.iglob('*.cfg'):
    cfg = AdvConfig(f)
    if not cfg: continue
    for track in sorted([t for t in cfg.sections() if t.startswith('TRACK')]):
      cfg.setsection(track)
      if cfg.get('type')!='video': continue
      if cfg.get('disable',False): continue
      build_indices(cfg)

  for f in glob.iglob('*.cfg'):
    cfg = AdvConfig(f)
    if not cfg: continue
    for track in sorted([t for t in cfg.sections() if t.startswith('TRACK')]):
      cfg.setsection(track)
      if cfg.get('type')!='subtitles': continue
      if cfg.get('disable',False): continue
      build_subtitle(cfg)

  for f in glob.iglob('*.cfg'):
    cfg = AdvConfig(f)
    if not cfg: continue
    for track in sorted([t for t in cfg.sections() if t.startswith('TRACK')]):
      cfg.setsection(track)
      if cfg.get('type')!='audio': continue
      if cfg.get('disable',False): continue
      if cfg.has('language') and cfg.has('audio_languages',section='MAIN') and cfg.get('language') not in cfg.get('audio_languages',section='MAIN').split(";"): continue
      build_audio(cfg)

  for f in glob.iglob('*.cfg'):
    cfg = AdvConfig(f)
    if not cfg: continue
    for track in sorted([t for t in cfg.sections() if t.startswith('TRACK')]):
      cfg.setsection(track)
      if cfg.get('type')!='video': continue
      if cfg.get('disable',False): continue
      build_video(cfg)

  parser = argparse.ArgumentParser(fromfile_prefix_chars='@',prog=prog,epilog='Written by: '+author)

  parser.add_argument('--version', action='version', version='%(prog)s '+version)
  parser.add_argument('-v','--verbose',dest='loglevel',action='store_const', const=logging.INFO)
  parser.add_argument('-d','--debug',dest='loglevel',action='store_const', const=logging.DEBUG)
  parser.set_defaults(loglevel=logging.WARN)
  parser.add_argument('-n','--nice',dest='niceness',action='store', type=int, default=0)
  parser.add_argument('-l','--log',dest='logfile',action='store')
  parser.add_argument('sourcedirs', nargs='*', metavar='DIR', help='directories to search for source files')
  parser.add_argument('--outdir',dest='outdir',action='store',help='directory for finalized .mp4 files; if unspecified use working directory')
  parser.add_argument('--descdir',dest='descdir',action='store',help='directory for .txt files with descriptive data')
  parser.add_argument('--artdir',dest='artdir',action='store',help='directory for .jpg and .png cover art')
  parser.add_argument('--mak',dest='mak',action='store',help='your TiVo MAK key to decrypt .TiVo files to .mpg')
  parser.add_argument('--omdbkey',dest='omdbkey',action='store',help='your OMDB key to automatically retrieve posters')
  parser.add_argument('--move-source',action='store_true', default=False, help='move source files to working directory before extraction')
  parser.add_argument('--delete-source',action='store_true', default=False, help='delete source file after successful extraction')
  parser.add_argument('--keep-video-in-mkv',action='store_true', default=False, help='do not attempt to extract video tracks from MKV source, but instead use MKV file directly')
  parser.add_argument('--keep-audio-in-mkv',action='store_true', default=False, help='do not attempt to extract audio tracks from MKV source, but instead use MKV file directly')

  for inifile in [ f'{os.path.splitext(sys.argv[0])[0]}.ini', prog + '.ini', '..\\' + prog + '.ini' ]:
    if os.path.exists(inifile): sys.argv.insert(1,'@'+inifile)
  args = parser.parse_args()

  log.setLevel(0)

  if args.logfile:
    flogger=logging.handlers.WatchedFileHandler(args.logfile, 'a', 'utf-8')
    flogger.setLevel(logging.DEBUG)
    flogger.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s]: %(message)s'))
    log.addHandler(flogger)

  tlogger=TitleHandler()
  tlogger.setLevel(logging.DEBUG)
  tlogger.setFormatter(logging.Formatter('makemp4: %(message)s'))
  log.addHandler(tlogger)

  slogger=logging.StreamHandler()
  slogger.setLevel(args.loglevel)
  slogger.setFormatter(logging.Formatter('[%(levelname)s] %(asctime)s: %(message)s'))
  log.addHandler(slogger)

  log.info(prog + ' ' + version + ' starting up.')
  nice(args.niceness)
  progmodtime=os.path.getmtime(sys.argv[0])

  sources=[]
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
    sleep_state = sleep_change_directories(['.'] + sources, sleep_state)
    main()
    log.debug('Sleeping.')

