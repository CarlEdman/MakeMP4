#!/usr/bin/python
# A Python frontend to various audio/video tools to automatically convert to MP4/H264/H265/AAC-LC and tag the results

prog='MakeMP4'
version='5.0'
author='Carl Edman (CarlEdman@gmail.com)'

import string, re, os, sys, argparse, logging, time, math, shutil, tempfile, json
from subprocess import call, check_call, check_output, CalledProcessError, Popen, PIPE, STDOUT, list2cmdline
from os.path import exists, isfile, isdir, getmtime, getsize, join, basename, splitext, abspath, dirname
from fractions import Fraction
from urllib.request import urlopen
from urllib.parse import urlparse, urlunparse, urlencode
from urllib.error import HTTPError
from AdvConfig import AdvConfig
from cetools import *

import regex
import json
import xml.etree.ElementTree as ET

def iso6392BtoT(l):
  d = { 'alb':'sqi', 'arm':'hye', 'baq':'eus', 'bur':'mya', 'chi':'zho', 'cze':'ces', 'dut':'nld', 'fre':'fra', 'geo':'kat', 'ger':'deu', 'gre':'ell', 'ice':'isl', 'mac':'mkd', 'mao':'mri', 'may':'msa', 'per':'fas', 'rum':'ron', 'slo':'slk', 'tib':'bod', 'wel':'cym' }
  if l in d: return d[l]

  e = { 'English':'eng', 'Français': 'fra', 'Japanese':'jpn', 'Español':'esp' , 'German':'deu', 'Deutsch':'deu', 'Svenska':'swe', 'Latin':'lat', 'Dutch':'nld', 'Chinese':'zho' }
  if l in e: return e[l]
  return l

def parse_time(s):
  r = regex.RegEx(regex=r'(?P<hrs>\d+):(?P<mins>\d+):(?P<secs>\d+(\.\d*)?)')
  r(text=s)
  return float(r.hrs)*3600.0+float(r.mins)*60.0+float(r.secs)

def readytomake(file,*comps):
  for f in comps:
    if not exists(f) or not isfile(f) or getsize(f)==0 or work_locked(f): return False
    fd=os.open(f,os.O_RDONLY|os.O_EXCL)
    if fd<0:
      return False
    os.close(fd)
  if not exists(file): return True
  if getsize(file)==0:
    return False
#  fd=os.open(file,os.O_WRONLY|os.O_EXCL)
#  if fd<0: return False
#  os.close(fd)
  for f in comps:
    if f and getmtime(f)>getmtime(file):
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
  cstr = ' | '.join([list2cmdline(c) for c in cs])
  debug('Executing: '+ cstr)
  work_lock(outfile)
  ps=[]
  for c in cs:
    ps.append(Popen(c, stdin=ps[-1].stdout if ps else infile, stdout=PIPE, stderr=PIPE))
  outstr, errstr = ps[-1].communicate()

  work_unlock(outfile)
  # encname='cp1252'/ encname='utf-8'
  outstr = outstr.decode(errors='replace')
  errstr = errstr.decode(errors='replace')
  errstr += "".join([p.stderr.read().decode(errors='replace') for p in ps if not p.stderr.closed])
  outstr=cookout(outstr)
  errstr=cookout(errstr)
  if outstr: debug('Output: '+repr(outstr))
  if errstr: debug('Error: '+repr(errstr))
  errcode = ps[-1].poll()
  if errcode!=0:
    error('Error code for ' + repr(cstr) + ': ' + str(errcode))
    if outfile: open(outfile,'w').truncate(0)
  return outstr+errstr

def make_srt(cfg,track,files):
  return True
  base=cfg.get('base',section='MAIN')
  srtfile='{} T{:02d}.srt'.format(base,track)
  if not exists(srtfile): do_call(['ccextractorwin'] + files + ['-o', srtfile],srtfile)
  if exists(srtfile) and getsize(srtfile)==0: os.remove(srtfile)
  if not exists(srtfile): return False
  cfg.setsection('TRACK{:02d}'.format(track))
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
  r=regex.RegEx()
  for l in idx.splitlines():
    if r(r'^\s*#',l):
      continue
    if r(r'^\s*$',l):
      continue
    elif r(r'^\s*timestamp:\s*(\d+):(\d+):(\d+):(\d+):(\d+),\s*filepos:\s*0*([0-9a-fA-F]+?)\s*$',l):
      timestamp.append(str(float(r[0])*3600+float(r[1])*60+float(r[2])+float(r[3])/1000.0))
      filepos.append(r[4])
    elif r(r'^\s*id\s*:\s*(\w+?)\s*, index:\s*(\d+)\s*$',l):
      cfg.set('language',r[0]) # Convert to 3 character codes
      cfg.set('langindex',r[1])
    elif r(r'^\s*(\w+)\s*:\s*(.*?)\s*$',l):
      cfg.set(r[0],r[1])
    else:
      warning('{}: Ignorning in {} uninterpretable line: {}'.format(cfg.get('base','NOBASE','MAIN'),idxfile,l))
  cfg.set('timestamp',','.join(timestamp))
  cfg.set('filepos',','.join(filepos))
  cfg.sync()


def prepare_tivo(tivofile):
  if exists(tivofile+'.header'): return False
  if exists(tivofile+'.error'): return False
  mpgfile = tivofile[:-5]+'.mpg'
  if not readytomake(mpgfile,tivofile): return False

  if args.mak:
    do_call(['tivodecode','--mak',args.mak,'--out',mpgfile,tivofile],mpgfile)
    if exists(mpgfile) and getsize(mpgfile)>0: os.remove(tivofile)


def prepare_mpg(mpgfile):
  base, ext=splitext(basename(mpgfile))
  cfgfile=base+'.cfg'
  if not readytomake(cfgfile,mpgfile): return False
  cfg=AdvConfig(cfgfile)
  config_from_base(cfg,base)
  work_lock(cfgfile)

  track=1
  dgifile='{} T{:02d}.d2v'.format(base,track)
  if not exists(dgifile):
    do_call(['dgindex', '-i', mpgfile, '-o', splitext(base)[0], '-fo', '0', '-ia', '3', '-om', '2', '-hide', '-exit'],base+'.d2v')
#    do_call(['DGIndexNV', '-i', mpgfile, '-a', '-o', dgifile, '-h', '-e'],dgifile)
  if not exists(dgifile): return
  cfg.setsection('TRACK{:02d}'.format(track))
  cfg.set('file',mpgfile)
  cfg.sync()
  config_from_dgifile(cfg,dgifile)

  r=regex.RegEx()
  for file in regex.reglob(re.escape(base) +r'\s+T[0-9a-fA-F][0-9a-fA-F]\s+(.*)\.(ac3|dts|mpa|mp2|wav|pcm)'):
    if not r('^'+re.escape(base)+r'\s+T[0-9a-fA-F][0-9a-fA-F]\s+(.*)\.(ac3|dts|mpa|mp2|wav|pcm)$',file): continue
    feat=r[0]
    ext=r[1]
    track+=1
    cfg.setsection('TRACK{:02d}'.format(track))
    nf='{} T{:02d}.{}'.format(base,track,ext)
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
  base=splitext(basename(mkvfile))[0]
  cfgfile=base+'.cfg'
  if not readytomake(cfgfile,mkvfile): return False
  cfg=AdvConfig(cfgfile)
  config_from_base(cfg,base)
  work_lock(cfgfile)

  cfg.setsection('MAIN')

  try:
    chaps = ET.fromstring(check_output(['mkvextract','chapters',mkvfile]).decode(errors='replace'))
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
      chap_lang.append(iso6392BtoT(chap.find('ChapterDisplay').find('ChapterLanguage').text))
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
    warning("No valid XML chapters for " + mkvfile + ".")

  j = json.loads(check_output(['mkvmerge','-J',mkvfile]).decode(errors='replace'))
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
    cfg.setsection('TRACK{:02d}'.format(tid))
    cfg.set('mkvtrack',track['id'])
    cfg.set('type',track['type'])

    codec = track['codec']
    cfg.set('format', codec)

    if codec in ('V_MPEG2','MPEG-1/2',):
      cfg.set('extension','mpg')
      cfg.set('file','{} T{:02d}.mpg'.format(base,tid))
      cfg.set('dgi_file','{} T{:02d}.dgi'.format(base,tid))
    elif codec in ('V_MPEG4/ISO/AVC','MPEG-4p10/AVC/h.264',):
      cfg.set('extension','264')
      cfg.set('file','{} T{:02d}.264'.format(base,tid))
#        cfg.set('t2c_file','{} T{:02d}.t2c'.format(base,tid))
      cfg.set('dgi_file','{} T{:02d}.dgi'.format(base,tid))
    elif codec in ('V_MS/VFW/FOURCC, WVC1','VC-1',):
      cfg.set('extension','wvc')
      cfg.set('file','{} T{:02d}.wvc'.format(base,tid))
#        cfg.set('t2c_file','{} T{:02d}.t2c'.format(base,tid))
      cfg.set('dgi_file','{} T{:02d}.dgi'.format(base,tid))
    elif codec in ('A_AC3','A_EAC3','AC3/EAC3','AC-3/E-AC-3', 'AC-3','E-AC-3'):
      cfg.set('extension','ac3')
      cfg.set('file','{} T{:02d}.ac3'.format(base,tid))
      cfg.set('quality',60)
      cfg.set('delay',0.0)
    elif codec in ('TrueHD','A_TRUEHD','TrueHD Atmos',):
      cfg.set('extension','thd')
      cfg.set('file','{} T{:02d}.thd'.format(base,tid))
      cfg.set('quality',60)
      cfg.set('delay',0.0)
      skip_a_dts = True
    elif codec in ('DTS-HD Master Audio',):
      cfg.set('extension','dts')
      cfg.set('file','{} T{:02d}.dts'.format(base,tid))
      cfg.set('quality',60)
      cfg.set('delay',0.0)
      skip_a_dts = True
    elif codec in ('A_DTS', 'DTS', 'DTS-ES', 'DTS-HD High Resolution', 'DTS-HD High Resolution Audio',):
      cfg.set('extension','dts')
      cfg.set('file','{} T{:02d}.dts'.format(base,tid))
      cfg.set('quality',60)
      cfg.set('delay',0.0)
      if skip_a_dts:
        cfg.set('disable', True)
        skip_a_dts = False
    elif codec in ('A_PCM/INT/LIT','PCM',):
      cfg.set('extension','pcm')
      cfg.set('file','{} T{:02d}.pcm'.format(base,tid))
      cfg.set('quality',60)
      cfg.set('delay',0.0)
    elif codec in ('S_VOBSUB','VobSub',):
      cfg.set('extension','idx')
      cfg.set('file','{} T{:02d}.idx'.format(base,tid))
      cfg.set('delay',0.0)
      cfg.set('elongation',1.0)
    elif codec in ('S_HDMV/PGS','HDMV PGS','PGS',):
      cfg.set('extension','sup')
      cfg.set('file','{} T{:02d}.sup'.format(base,tid))
      cfg.set('delay',0.0)
      cfg.set('elongation',1.0)
    elif codec in ('SubRip/SRT',):
      cfg.set('extension','srt')
      cfg.set('file','{} T{:02d}.srt'.format(base,tid))
      cfg.set('delay',0.0)
      cfg.set('elongation',1.0)
    elif codec in ('A_MS/ACM',):
      cfg.set('disable',True)
    else:
      warning('{}: Unrecognized track type {} in {}'.format(cfg.get('base','NOBASE','MAIN'),codec,mkvfile))
      cfg.set('disable',True)


    for k,v in track['properties'].items():
      if k == 'language':
        cfg.set('language', iso6392BtoT(v))
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
    if file and not exists(file) and mkvtrack>=0:
      call.append('{:d}:{}'.format(mkvtrack,file))
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
    if t2cfile and not exists(t2cfile) and mkvtrack>=0: call.append('{:d}:{}'.format(mkvtrack,t2cfile))
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
#      warning('Timecodes changed frames in "{}" from {:d} to {:d}'.format(file,oframes,frames))
#    cfg.set('frames',frames)
    duration=t2cl[-1]/1000.0
    oduration=cfg.get('duration',-1.0)
    if oduration>0 and oduration!=duration:
      warning('Encoding changed duration in "{}" from {:f} to {:f}'.format(file,oduration,duration))
    cfg.set('duration',duration)
    cfg.sync()

  for vt in sorted([t for t in cfg.sections() if t.startswith('TRACK') and not cfg.get('disable',section=t) and cfg.get('type',section=t)=='subtitles']):
    cfg.setsection(vt)
    file=cfg.get('file')
    ext=cfg.get('extension')
    if ext=='.sub':
      config_from_idxfile(cfg,splitext(file)[0]+'.idx')
      # remove idx file

  if args.delete_source:
    os.remove(mkvfile)

def prepare_vob(vobfile):
  base=splitext(basename(vobfile))[0]
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
#  if exists(idxfile): continue
#  ifofile=basefile+"_0.ifo"
#  if exists(ifofile) and getsize(ifofile)>0:
#    pgc=1
#    trueifofile=ifofile
#  elif ifofile[-13:-8] == "_PGC_" and exists(ifofile[:-13]+"_0.ifo"):
#    pgc=int(ifofile[-8:-6])
#    trueifofile=ifofile[:-13]+"_0.ifo"
#  else:
#    continue
#
#  vobsubfile=r'C:\Windows\Temp\vobsub'
#  info('Generating "%(vobfile)s" -> "%(idxfile)s"' % locals())
#  open(vobsubfile,'wt').write('%(ifofile)s\n%(basefile)s\n%(pgc)d\n0\nALL\nCLOSE\n' % locals())
#  if trueifofile!=ifofile: copyfile(trueifofile,ifofile)
#  do_call([r'C:\Windows\SysWOW64\rundll32.exe','vobsub.dll,Configure',vobsubfile],vobsubfile)
#  if trueifofile!=ifofile: os.remove(ifofile)
##  if not exists(idxfile): open(idxfile,'wt').truncate(0)

#  if make_srt(cfg,track+1,vobfiles): track+=1

#  chapter txt -> cfg
  cfg.sync()
  work_unlock(cfgfile)
#  if args.delete_source:
#    os.remove(vobfile)


# TODO: episode images from both files and omdb
def update_coverart(cfg):
  cfg.setsection('MAIN')
  if cfg.has('coverart'): return

  base   = cfg.get('base')
  show   = cfg.get('show')
  season = cfg.get('season',-1)
  episode= cfg.get('episode',-1)

  artregex = ''.join([
    re.escape(show.strip().translate(str.maketrans('','',r':"/\:*?<>|'))),
    ' S'+str(season) if season>0 else '',
    r'(\s+P[\d+])?\.(jpg|jpeg|png)'])

  artfiles = regex.reglob(artregex,args.artdir or None)
  if artfiles:
    cfg.set('coverart', ';'.join(artfiles))
    cfg.sync()
    return

  artfile = join(args.artdir or '',''.join([show, ' S'+str(season) if season>0 else '', r'.jpg']))
  if not args.omdbkey: return
  if exists(artfile): return
  if cfg.hasno('imdb_id'): return
  ops = cfg.get('omdb_poster_status', 0)
  if 200<=ops<300 or 400<=ops<500: return

  q = { 'h':'1000', 'i':cfg.get('imdb_id'), 'apikey': args.omdbkey }
  u = urlunparse(['http','img.omdbapi.com', '/', '', urlencode(q), ''])

  try:
    with urlopen(u) as f:
      cfg.set('omdb_poster_status', f.getcode())
      p = f.read()
  except HTTPError as e:
    cfg.set('omdb_poster_status', e.code)
    p = None

  cfg.sync()
  if not p: return

  with open(artfile,'wb') as f: f.write(p)
  cfg.set('coverart',artfile)
  cfg.sync()

def update_description_tvshow(cfg,txt):
  def lfind(l,*ws):
    for w in ws:
      if w in l: return l.index(w)
    return -1

  tl=txt.splitlines()
  h=[a.strip() for a in tl[0].split('\t')]
  tl=tl[1:]
  i=lfind(h,"\xe2\x84\x96",'?','Total','Series number','Nº','No. overall')
  if i>=0: h[i]='Series Episode'
  sei=lfind(h,'Series Episode')

  epi=lfind(h,'#','No.','No. in season','No. in Season','Episode number','Ep','Ep.','No. in series','No. in Series')
  if epi<0: return False # Fix
  tii=lfind(h,'Title','Episode title','Episode name','Episode Title','Episode Name')
  dei=lfind(h,'Description')
  if dei<0:
    dei=len(h)
    h.append('Description')
  i=1
  while i<len(tl):
    if '\t' not in tl[i]:
      tl[i-1]=tl[i-1]+'\t'+tl[i]
      tl[i]=''
    i+=1
  # 'Directed by*','Director'
  wri=lfind(h,'Written by','Written by:','Writer')
  dai=lfind(h,'Original Airdate','Original air date','Original airdate','Airdate','Original release date','Release date','Aired on','Recorded on')
  pci=lfind(h,'Production code','Prod. code','prod. code','Prod.code','PC','Production number')

  r=regex.RegEx()
  for t in tl:
    if not t: continue
    l=t.split('\t')
    if cfg.has('episode'):
      if l[epi]!=str(cfg.get('episode')): continue
    else:
      if l[epi]!='*': continue
#    if l[epi].lstrip(' 0')!=str(cfg.get('episode','*')): continue
    if 0<=tii<len(l) and l[tii] and cfg.hasno('song'):
      cfg.set('song',l[tii].strip('" '))
    if 0<=wri<len(l) and l[wri] and cfg.hasno('writer'):
      cfg.set('writer',re.sub(r'\s*&\s*','; ',l[wri]))
    if 0<=pci<len(l) and l[pci] and cfg.hasno('episodeid'):
      cfg.set('episodeid',l[pci].strip())
    if 0<=dai<len(l) and r(r'\b([12]\d\d\d)\b',l[dai]) and cfg.hasno('year'):
      cfg.set('year',int(r[0]))
    if 0<=dei<len(l) and l[dei] and cfg.hasno('description'):
      cfg.set('description',l[dei])
    for i in range(len(l)):
      if i in [epi,tii,wri,pci,dei]: continue
      s=l[i].strip()
      if not s: continue
      s=(h[i].strip().rstrip(':') if i<len(h) else '')+': '+s
      cmt = cfg.get('comment','')
      if s not in cmt: cfg.set('comment',  (cmt+';' if cmt else '')+ s)

  cfg.sync()


def update_description_movie(cfg,txt):
  txt=re.sub(r'(This movie is|Cast|Director|Genres|Availability|Language|Format|Moods)(:|\n| )\s*',r'\n\1: ',txt)
  r=regex.RegEx(regex=r'^\s*(Rate 5 stars|Rate 4 stars|Rate 3 stars|Rate 2 stars|Rate 1 stars|Rate not interested(Clear Rating)?|Not Interested(Clear)?|[0-5]\.[0-9]|Movie Details|Overview\s*Details|At Home|In Queue)\s*$')
  tl=[l for l in txt.splitlines() if l and not r(text=l)]
  if r(r'^(.*?)\s*(\((.*)\))?$',tl[0]):
    tl=tl[1:]
    if cfg.hasno('title'): cfg.set('title',r[0])
    if r[2]:
      alt = 'Alternate Title: ' + r[2]
      cmt = cfg.get('comment','')
      if alt not in cmt: cfg.set('comment',  (cmt+';' if cmt else '')+ alt)
  if r(r'^\s*([12]\d\d\d)\s*(G|PG-13|PG|R|NC-17|UR|NR|TV-14|TV-MA)?\s*( Rated \2)?\s*(\d+\s*(hours|hrs|hr|h)\s*)?((\d+)\s*(minutes|mins|min|m)\s*)?.*$',tl[0]):
    tl=tl[1:]
    cfg.set('year',r[0])
    rat = 'Rating: ' + r[1]
    cmt = cfg.get('comment','')
    if rat not in cmt: cfg.set('comment',  (cmt+';' if cmt else '')+ rat)
#    if not cfg.has('duration'): cfg.add('duration',int(r[2])*60)
  description = ''
  for t in tl:
    if r(r'^Genres?:\s*(.+?)\s*$',t):
      if cfg.has('genre'): continue
      description = (description+'  ' if description else '') + 'Genres: ' + r[0] +'.'
      g=r[0]
      if r(r'\bMusicals?\b',g): cfg.set('genre','Musical')
      elif r(r'\bAnimes?\b',g): cfg.set('genre','Anime')
      elif r(r'\bOperas?\b',g): cfg.set('genre','Opera')
      elif r(r'\bSci-Fi\b',g): cfg.set('genre','Science Fiction')
      elif r(r'\bFantasy\b',g): cfg.set('genre','Fantasy')
      elif r(r'\bHorror\b',g): cfg.set('genre','Horror')
      elif r(r'\bDocumentar(y|ies)\b',g): cfg.set('genre','Documentary')
      elif r(r'\bSuperhero\b',g): cfg.set('genre','Superhero')
      elif r(r'\bWesterns?\b',g): cfg.set('genre','Western')
      elif r(r'\bClassics?\b',g): cfg.set('genre','Classics')
      elif r(r'\bComed(y|ies)\b',g): cfg.set('genre','Comedy')
      elif r(r'\bCrime\b',g): cfg.set('genre','Crime')
      elif r(r'\bThrillers?\b',g): cfg.set('genre','Thriller')
      elif r(r'\bRomantic\b',g): cfg.set('genre','Romance')
      elif r(r'\bAnimation\b',g): cfg.set('genre','Animation')
      elif r(r'\bCartoons?\b',g): cfg.set('genre','Animation')
      elif r(r'\bPeriod Pieces?\b',g): cfg.set('genre','History')
      elif r(r'\bAction\b',g): cfg.set('genre','Action')
      elif r(r'\bAdventure\b',g): cfg.set('genre','Adventure')
      elif r(r'\bDramas?\b',g): cfg.set('genre','Drama')
      else: cfg.set('genre',g)
    elif r(r'^(Writers?):\s*(.+?)\s*$',t):
      description = description + '  ' + r[0] + ': ' + r[1] +'.'
      if cfg.has('writer'): continue
      cfg.set('writer',val)
    elif r(r'^(\w+|Our best guess for you|Average of \d+ ratings|This movie is):\s*(.+?)\s*$',t):
      description = description + '  ' + r[0] + ': ' + r[1] +'.'
    elif r(r'^(rated )?\d+\.\d+( stars)?$'):
      pass
    else:
      description = '  ' + t + description

  if cfg.hasno('description') and description:
    cfg.set('description',description[2:])
  cfg.sync()


def update_description(cfg):
  cfg.setsection('MAIN')
  base   = cfg.get('base')
  show   = cfg.get('show')
  season = cfg.get('season',-1)
  episode= cfg.get('episode',-1)

  sshow = ''.join([c for c in show.strip().upper() if c.isalnum()])
  if cfg.hasno('year'): cfg.set('year', r'${}YEAR$'.format(sshow))
  if cfg.hasno('genre'): cfg.set('genre', r'${}GENRE$'.format(sshow))
  if cfg.hasno('description'): cfg.set('description', r'${}DESC$'.format(sshow))

  descfile = ''.join([
    join(args.descdir or '',show),
    ' S'+str(season) if season>0 else '',
    '.txt'])

  if exists(descfile):
    with open(descfile,'rt', encoding='utf-8-sig', errors='backslashreplace') as fp: txt=fp.read()
    txt=txt.strip()
    txt=re.sub(r'Add to Google Calendar','',txt)
    txt=re.sub(r' *\[(\d+|[a-z])\] *','',txt)
    txt=re.sub(r'\s+-+\s+',r'—',txt)
    txt=re.sub(r'\s*%',' percent',txt)
    if cfg.get('type')=='tvshow': update_description_tvshow(cfg,txt)
    elif cfg.get('type')=='movie': update_description_movie(cfg,txt)
    cfg.sync()
    return

  if cfg.get('omdb_status')!=200:
    q = { 'plot':'full', 'tomatoes':'true', 'r':'json' }
    if cfg.has('year'): q['y']=str(cfg.get('year'))
    if cfg.has('imdb_id'):
      q['i'] = cfg.get('imdb_id')
    elif cfg.get('type')=='movie':
      q['t'] = str(show)
      q['type'] = 'movie'
    elif cfg.get('type')=='tvshow':
      q['t'] = str(show)
      if episode>0 and season>0:
        q['type'] = 'episode'
        q['Season'] = str(season)
        q['Episode'] = str(episode)
      else:
        q['type'] = 'series'

    u = urlunparse(['http','www.omdbapi.com', '/', '', urlencode(q), ''])
    try:
      with urlopen(u) as f:
        cfg.set('omdb_status',f.getcode())
        j = json.loads(f.read().decode('utf-8'))
    except HTTPError as e:
      cfg.set('omdb_status',e.code)
      j = None

    cfg.sync()
    if not j: return

    imdb_id = j.get('imdbID',None)
    imdb_series_id = j.get('seriesID',None)
    imdb_rating = j.get('imdbRating',None)
    imdb_votes = j.get('imdbVotes',None)

    if cfg.has('imdb_id') and cfg.get('imdb_id')!=imdb_id:
      warning('{}: IMDB Id mismatch ("{}" != "{}")'.format(base,imdb_id,v))
    elif imdb_id:
      cfg.set('imdb_id',imdb_id)

    if cfg.has('imdb_series_id') and cfg.get('imdb_series_id')!=imdb_series_id:
      warning('{}: IMDB Series Id mismatch ("{}" != "{}")'.format(base,cfg.get('imdb_series_id'),imdb_series_id))
    elif imdb_series_id:
      cfg.set('imdb_series_id',imdb_series_id)

    if imdb_id or imdb_series_id or imdb_rating or imdb_votes:
      comment = cfg.get('comment')
      imdb = "IMDB({}{}): {}{}".format(
        imdb_id or "",
        "/"+imdb_series_id if imdb_series_id and imdb_series_id!=imdb_id else "",
        imdb_rating or "--",
        " from "+imdb_votes+ " votes." if imdb_votes else "")
      if not comment or comment.find(imdb)<0:
        cfg.set('comment', (comment+'  ' if comment else '') + imdb)

    comment_trans = {
      'Country': 'Country: ',
      'DVD':'DVD Release: ',
      'Awards':'Awards: ',
      'BoxOffice':'Boxoffice: ',
      'Language':'Language: ',
      'Metascore':'Metascore: ',
      'Rated':'Rating: ',
      'Released':'Released on: ',
      'Runtime':'Runtime: ',
      'Website':'Web Site: ',
      'totalSeasons': None
      }

    genre_trans = [
      # ('Game-Show','XXX'),
      # ('News','XXX'),
      # ('Reality-TV','XXX'),
      # ('Sport','XXX'),
      # ('Talk-Show','XXX'),
      # ('Film-Noir','XXX'),
      ('Animation','CGI'),
      ('Musical','Musical'),
      ('Documentary','Documentary'),
      ('Romance','Romance'),
      ('Horror','Horror'),
      ('Sci-Fi','Science Fiction'),
      ('Fantasy','Fantasy'),
      ('Western','Western'),
      ('Mystery','Mystery'),
      ('Crime','Crime'),
      ('Family','Children'),
      ('Adventure','Adventure'),
      ('Action','Action'),
      ('Thriller','Thriller'),
      ('War','History'),
      ('History','History'),
      ('Biography','History'),
      ('Drama','Drama'),
      ('Music','Opera'),
      ('Sitcom','Comedy'),
      ('Comedy','Comedy')
      ]

    for k,v in j.items():
      description = cfg.get('description')
      comment = cfg.get('comment')
      if v=='N/A':
        continue
      elif k in ['imdbID','seriesID','imdbRating','imdbVotes','Episodes','Poster']:
        continue
      elif k.startswith('tomato'):
# imdb_tomatoConsensus = Spectre nudges Daniel Craig's rebooted Bond closer to the glorious, action-driven spectacle of earlier entries, although it's admittedly reliant on established 007 formula.
# imdb_tomatoFresh = 188
# imdb_tomatoImage = fresh
# imdb_tomatoMeter = 64
# imdb_tomatoRating = 6.5
# imdb_tomatoReviews = 293
# imdb_tomatoRotten = 105
# imdb_tomatoURL = http://www.rottentomatoes.com/m/spectre_2015/
# imdb_tomatoUserMeter = 62
# imdb_tomatoUserRating = 3.5
# imdb_tomatoUserReviews = 103067"
        continue
      elif k=='Response':
        if v!="True":
          warning('{}: IMDB Response = "{}" in '.format(base,v))
      elif k=='Year':
        year = cfg.get('year')
        if not year:
          cfg.set('year',v)
        elif str(year)!=v:
          warning('{}: IMDB Year mismatch ("{}" != "{}")'.format(base,year,v))
      elif k=='Type': # "movie" or "episode"
        type = cfg.get('type')
        itype = 'movie' if v=='movie' else 'tvshow'
        if not type:
          cfg.set('type', itype)
        elif str(type)!=itype:
          warning('{}: IMDB Type mismatch ("{}" != "{}")'.format(base,type,v))
      elif k=='Episode':
        episode = cfg.get('episode')
        if not episode:
          cfg.set('episode', int(v))
        elif episode!=int(v):
          warning('{}: IMDB Episode mismatch ("{}" != "{}")'.format(base,episode,v))
      elif k=='Season':
        season = cfg.get('season')
        if not season:
          cfg.set('season', int(v))
        elif season!=int(v):
          warning('{}: IMDB Season mismatch ("{}" != "{}")'.format(base,season,v))
      elif k=='Title':
        if season>=0 and episode>=0:
          if v=="Episode #{}.{}".format(season,episode):
            continue
          song = cfg.get('song')
          if not song or v.endswith(song):
            cfg.set('song',v)
          elif song!=v:
            warning('{}: IMDB Episode Title mismatch ("{}" != "{}")'.format(base,song,v))
        elif season<0 and episode<0:
          if not show or v.endswith(show):
            cfg.set('show',v)
          elif show!=v:
            warning('{}: IMDB Show Title mismatch ("{}" != "{}")'.format(base,show,v))
      elif k=='Director':
        director = cfg.get('director')
        if not director:
          cfg.set('director',v)
        elif director!=v:
          warning('{}: IMDB Director mismatch ("{}" != "{}")'.format(base,director,v))
      elif k=='Writer':
        writer = cfg.get('writer')
        if not writer:
          cfg.set('writer',v)
        elif writer!=v:
          warning('{}: IMDB Writer mismatch ("{}" != "{}")'.format(base,writer,v))
      elif k=='Production':
        network = cfg.get('network')
        if not network:
          cfg.set('network',v)
        elif network!=v:
          warning('{}: IMDB Network mismatch ("{}" != "{}")'.format(base,network,v))
      elif k=='Plot':
        plot = re.sub(r'\s+-+\s+',r'—',v)
        if not description or description.find(plot)<0:
          cfg.set('description', plot + ('  '+description if description else ''))
      elif k=='Actors':
        actors = 'Actors: ' + v + '.'
        if not description or description.find(actors)<0:
          cfg.set('description', (description+'  ' if description else '') + actors)
      elif k=='Genre':
        genre = cfg.get('genre')
        igenre = None
        for f,t in genre_trans:
          if v.find(f)<0: continue
          igenre = t
          break
        if not igenre:
          continue
        elif not genre:
          cfg.set('genre',igenre)
        elif genre!=igenre:
          warning('{}: IMDB Genre mismatch ("{}" != "{}")'.format(base,genre,v))
      elif k in comment_trans:
        if not comment_trans[k]: continue
        t = comment_trans[k] + v + '' if v[-1]=='.' else '.'
        if not comment or comment.find(t)<0:
          cfg.set('comment', (comment+'  ' if comment else '') + t)
      elif k=='Ratings':
        for r in v:
          t = r['Source'] + ' Rating: ' + r['Value'] + '.'
          if not comment or comment.find(t)<0:
            cfg.set('comment', (comment+'  ' if comment else '') + t)
      else:
        warning('{}: Unrecognized IMDB "{}" = "{}"'.format(base,k,v))
  cfg.sync()

def config_from_dgifile(cfg):
  file = cfg.get('file', None)
  dgifile = cfg.get('dgi_file', None)
  if not file or not dgifile: return
  logfile = splitext(file)[0]+'.log'
  r=regex.RegEx()

  t = str.maketrans(string.ascii_uppercase,string.ascii_lowercase,string.whitespace)
  while True:
    time.sleep(1)
    if not (exists (logfile)): continue
    with open(logfile,'rt', encoding='utf-8-sig', errors='replace') as fp: log = fp.read()
    for l in log.splitlines():
      if not r('^([^:]*):(.*)$',l):
        warning('Unrecognized DGIndex log line: "' + repr(l) + '"')
        continue
      k='dg'+r[0].translate(t)
      v=r[1].strip()
      if not v: continue
      cfg.set(k, cfg.get(k) + "; " + v if cfg.has(k) else v)
    if cfg.get('dginfo')=='Finished!': break
  os.remove(logfile)
  cfg.sync()

  with open(dgifile, 'rt', encoding='utf-8-sig', errors='replace') as fp: dgi=fp.read()
  dgip=dgi.split('\n\n')
  if len(dgip)!=4:
    error('Malformed index file ' + dgifile)
    open(dgifile,'w').truncate(0)
    return
  r=regex.RegEx()
  if r(r'^DG(AVC|MPG|VC1)IndexFileNV(14|15|16)',dgip[0]):
    if not r(r'\bCLIP\ *(?P<left>\d+) *(?P<right>\d+) *(?P<top>\d+) *(?P<bottom>\d+)',dgip[2]):
      error('No CLIP in ' + dgifile)
      open(dgifile,'w').truncate(0)
      return
    cl=int(r.left)
    cr=int(r.right)
    ct=int(r.top)
    cb=int(r.bottom)
    cl=cr=ct=cb=0
    if not r(r'\bSIZ *(?P<sizex>\d+) *x *(?P<sizey>\d+)',dgip[3]):
      error('No SIZ in ' + dgifile)
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
      warning('Guessing 1:1 SAR for ' + dgifile)
      sarf=Fraction(1,1)

    if not r(r'\bORDER *(?P<order>\d+)',dgip[3]):
      error('No ORDER in ' + dgifile)
      open(dgifile,'w').truncate(0)
      return
    fio=int(r.order)
    if not r(r'\bFPS *(?P<num>\d+) */ *(?P<denom>\d+) *',dgip[3]):
      error('No FPS in ' + dgifile)
      open(dgifile,'w').truncate(0)
      return
    frf=Fraction(int(r.num),int(r.denom))
    if not r(r'\b(?P<ipercent>\d*\.\d*)% *FILM',dgip[3]):
      error('No FILM in ' + dgifile)
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
      error('No PLAYBACK in ' + dgifile)
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
    error('Unrecognize index file ' + dgifile)
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
  cfg.set('picture_size', "{:d}x{:d}".format(psx,psy))

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
    if not dgifile or exists(dgifile): continue
    if dgifile.endswith('.dgi'):
      do_call(['DGIndexNV', '-i', cfg.get('file'), '-o', dgifile, '-h', '-e'],dgifile)
    elif dgifile.endswith('.d2v'):
      do_call(['dgindex', '-i', cfg.get('file'), '-o', splitext(dgifile)[0], '-fo', '0', '-ia', '3', '-om', '2', '-hide', '-exit'],dgifile)
    else:
      continue

    config_from_dgifile(cfg)

def build_subtitle(cfg):
  infile = cfg.get('file')
  inext = cfg.get('extension')
  d=cfg.get('delay',0.0)
  e=cfg.get('elongation',1.0)

  r=regex.RegEx()
  if getsize(infile)==0:
    pass
  elif inext=='srt':
    outfile = splitext(infile)[0]+'.ttxt'
    cfg.set('out_file', outfile)
    if exists(outfile): return # Should be not readytomake(outfile,)
    with open(infile, 'rt', encoding='utf-8-sig', errors='replace') as i, open('temp.srt', 'wt', encoding='utf-8', errors='replace') as o:
      inp=i.read()
      for l in inp.split('\n\n'):
        if not r(r'^(?s)(?P<beg>\s*\d*\s*)(?P<neg1>-?)(?P<hours1>\d+):(?P<mins1>\d+):(?P<secs1>\d+),(?P<msecs1>\d+)(?P<mid> --> )(?P<neg2>-?)(?P<hours2>\d+):(?P<mins2>\d+):(?P<secs2>\d+),(?P<msecs2>\d+)\b(?P<end>.*)$',l):
          if l.strip(): warning('Unrecognized line in {}: {}'.format(infile,repr(l)))
          continue
        time1 = (-1 if r.neg1 else 1)*(int(r.hours1)*3600.0+int(r.mins1)*60.0+int(r.secs1)+int(r.msecs1)/1000.0)
        neg1,hours1,mins1,secs1,msecs1=secsToParts(time1*e+d)
        time2 =(-1 if r.neg2 else 1)*(int(r.hours2)*3600.0+int(r.mins2)*60.0+int(r.secs2)+int(r.msecs2)/1000.0)
        neg2,hours2,mins2,secs2,msecs2=secsToParts(time2*e+d)
        if neg1 or neg2: continue
        o.write('{}{:02d}:{:02d}:{:02d},{:03d}{}{:02d}:{:02d}:{:02d},{:03d}{}\n\n'.format(r.beg,hours1,mins1,secs1,msecs1,r.mid,hours2,mins2,secs2,msecs2,r.end))
    do_call(['mp4box','-ttxt','temp.srt'],outfile)
    if exists('temp.ttxt'): os.rename('temp.ttxt',outfile)
    if exists('temp.srt'): os.remove('temp.srt')
  elif inext=='sup' and getsize(infile)<1024:
    outfile = splitext(infile)[0]+'.idx'
  elif inext=='sup':
    outfile = splitext(infile)[0]+'.idx'
    cfg.set('out_file', outfile)
    if exists(outfile): return  # Should be not readytomake(outfile,)
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
    outfile = splitext(infile)[0]+'.adj'+splitext(infile)[1]
    cfg.set('out_file', outfile)
    if not exists(splitext(infile)[0]+'.adj.sub'):
      shutil.copy(splitext(infile)[0]+'.sub',splitext(infile)[0]+'.adj.sub')
    if exists(outfile): return  # Should be not readytomake(outfile,)
    with open(infile, 'rt', encoding='utf-8-sig', errors='replace') as i, open(outfile, 'wt', encoding='utf-8', errors='replace') as o:
      for l in i:
        if not r(r'^(?s)(?P<beg>\s*timestamp:\s*)(?P<neg>-?)(?P<hours>\d+):(?P<mins>\d+):(?P<secs>\d+):(?P<msecs>\d+)\b(?P<end>.*)$',l):
          o.write(l)
          continue
        time = (-1 if r.neg else 1)*(int(r.hours)*3600.0+int(r.mins)*60.0+int(r.secs)+int(r.msecs)/1000.0)
        neg,hours,mins,secs,msecs=secsToParts(time*e+d)
        if neg: continue
        o.write('{}{:02d}:{:02d}:{:02d}:{:03d}{}'.format(r.beg,hours,mins,secs,msecs,r.end))
  elif (d!=0.0 or e!=1.0):
    outfile = infile
    cfg.set('out_file', outfile)
    warning('Delay and elongation not implemented for subtitles type "{}"'.format(infile))
  else:
    outfile = infile
    cfg.set('out_file', outfile)

  if getsize(infile)==0 or not exists(outfile):
    cfg.set('disable',True)
  cfg.sync()


def build_audio(cfg):
  infile = cfg.get('file')
  inext = cfg.get('extension')
  outfile = cfg.get('out_file','{} T{}.m4a'.format(cfg.get('base',section='MAIN'),cfg.getsection()[5:]))
  cfg.set('out_file',outfile)
  cfg.sync()
  if not readytomake(outfile,infile): return False

  r=regex.RegEx()

  if inext in (): # ('dts', 'thd'):
    call = [ 'dcadec', '-6', infile, '-']
  else:
    call = [ 'eac3to', infile]
    if inext=='mkv': call.append("{}:".format(cfg.get('mkvtrack')+1))
    call.append('stdout.wav')
    # call.append('-no2ndpass')
    call.append('-log=nul')
    if cfg.get('delay',0.0)!=0.0: call.append('{:+.0f}ms'.format(cfg.get('delay')*1000.0))
    if cfg.get('elongation',1.0)!=1.0: warning('Audio elongation not implemented')
    # if cfg.get('channels')==7: call.append('-0,1,2,3,5,6,4')

    if cfg.get('downmix')==6: call.append('-down6')
    elif cfg.get('downmix')==2: call.append('-downDpl')
    elif cfg.has('downmix'): warning('Invalid downmix "{:d}"'.format(cfg.get('downmix')))

    if cfg.get('normalize',False): call.append('-normalize')

  call += [ '|', 'qaac64', '--threading', '--ignorelength', '--no-optimize', '--tvbr', str(cfg.get('quality',60)), '--quality', '2', '-', '-o', outfile]

  res=do_call(call, outfile)
  if res and r(r'\bwrote (\d+\.?\d*) seconds\b',res):
    cfg.set('duration',float(r[0]))
  if cfg.has('duration') and cfg.has('duration',section='MAIN') and abs(cfg.get('duration')-cfg.get('duration',section='MAIN'))>0.5:
    warning('Audio track "{}" duration differs (elongation={:f})'.format(infile,cfg.get('duration')/cfg.get('duration',section='MAIN')))
  cfg.sync()
  return True


def build_video(cfg):
  infile = cfg.get('file')
  inext = cfg.get('extension')
  dgifile = cfg.get('dgi_file', None)

  outfile = cfg.get('out_file')
  if outfile == None:
    baseout = '{} T{}'.format(cfg.get('base',section='MAIN'),cfg.getsection()[5:])
    if cfg.get('out_format') == 'h264':
      outext = '264'
    elif cfg.get('out_format') == 'h265':
      outext = '265'
    else:
      error('{}: Unrecognized output format:'.format(file, cfg.get('out_format', 'UNSPECIFIED')))
      return False
    outfile = baseout + '.' + outext
    cfg.set('out_file',outfile)
  avsfile = cfg.get('avs_file',splitext(basename(infile))[0] +'.avs' )
  cfg.set('avs_file',avsfile)
  cfg.sync()

  if not readytomake(outfile,infile,dgifile): return False

  r=regex.RegEx()
  avs=''

  ilt=cfg.get('interlace_type')
  fri=cfg.get('frame_rate_ratio')

  procs=cfg.get('processors',6)
  if procs!=1: avs += 'SetMTMode(5,{:d})\n'.format(procs)
  avs += 'SetMemoryMax(1024)\n'
  if dgifile.endswith('.d2v'):
    avs+='DGDecode_mpeg2source("{}", info=3, idct=4, cpu=3)\n'.format(abspath(dgifile))
  elif dgifile.endswith('.dgi'):
    avs+='DGSource("{}", deinterlace={:d})\n'.format(abspath(dgifile), 1 if ilt in ['VIDEO', 'INTERLACE'] else 0)
  else:
    warning('No valid video index file from "{}"'.format(infile))
    return False

#  avs+='ColorMatrix(hints = true, interlaced=false)\n'.format(abspath(dgifile))

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
#    avs+='tfm().tdecimate(hybrid=1,d2v="{}")\n'.format(abspath(dgifile))
#    avs+='Telecide(post={:d},guide=0,blend=True)'.format(0 if lp>0.99 else 2)
#    avs+='Decimate(mode={:d},cycle=5)'.format(0 if lp>0.99 else 3)
#  elif ilt in ['VIDEO', 'INTERLACE']:
#    fro = fri
#    avs+='Bob()\n'
#    avs+='TomsMoComp(1,5,1)\n'
#    avs+='LeakKernelDeint()\n'
#    avs+='TDeint(mode=2, type={:d}, tryWeave=True, full=False)\n'.format(3 if cfg.get('x264_tune','animation' if cfg.get('genre',section='MAIN') in ['Anime', 'Animation'] else 'film')=='animation' else 2)
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
        avs+='crop({:d},{:d},{:d},{:d},align=true)\n'.format(cl,ct,-cr,-cb)
    elif cfg.get('crop')=='auto':
      avs+='autocrop(threshold=30,wMultOf=2, hMultOf=2,samples=51, mode=0)\n'

  blocksize=16 if cfg.get('macroblocks',0)>1620 else 8
  if procs!=1: avs+='SetMTMode(2)\n'

  degrain=cfg.get('degrain',3)
  if degrain>=1: # or ilt in ['VIDEO', 'INTERLACE']
    avs+='super = MSuper(planar=true)\n'
    avs+='bv1 = MAnalyse(super, isb = true,  delta = 1, blksize={:d}, overlap={:d})\n'.format(blocksize,blocksize//2)
    avs+='fv1 = MAnalyse(super, isb = false, delta = 1, blksize={:d}, overlap={:d})\n'.format(blocksize,blocksize//2)
  if degrain>=2:
    avs+='bv2 = MAnalyse(super, isb = true,  delta = 2, blksize={:d}, overlap={:d})\n'.format(blocksize,blocksize//2)
    avs+='fv2 = MAnalyse(super, isb = false, delta = 2, blksize={:d}, overlap={:d})\n'.format(blocksize,blocksize//2)
  if degrain>=3:
    avs+='bv3 = MAnalyse(super, isb = true,  delta = 3, blksize={:d}, overlap={:d})\n'.format(blocksize,blocksize//2)
    avs+='fv3 = MAnalyse(super, isb = false, delta = 3, blksize={:d}, overlap={:d})\n'.format(blocksize,blocksize//2)
  if degrain>0:
    avs+='MDegrain{:d}(super,thSAD=400,planar=true,{})\n'.format(degrain,','.join(['bv{:d},fv{:d}'.format(i,i) for i in range(1,degrain+1)]))
#  if ilt in ['VIDEO', 'INTERLACE']:
#    avs+='MFlowFps(super, bv1, fv1, num={:d}, den={:d}, ml=100)\n'.format(fro.numerator,fro.denominator)
  if procs!=1: avs+='Distributor()\n'

  if not exists(avsfile) or getmtime(cfg.filename)>getmtime(avsfile):
    with open(avsfile, 'wt', encoding='utf-8', errors='replace') as fp: fp.write(avs)
    debug('Created AVS file: ' + repr(avs))

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
    error('{}: Unrecognized output format:'.format(file, cfg.get('out_format', 'UNSPECIFIED')))
    return False

  call += ['--fps', str(fro)]
  sarf=cfg.get('sample_aspect_ratio')
  if isinstance(sarf,Fraction): call += ['--sar', '{:d}:{:d}'.format(sarf.numerator,sarf.denominator)]
  call += [ '--output', outfile ]

  cfg.sync()
  res=do_call(call,outfile)
  if res and r(r'\bencoded (\d+) frames\b',res):
    cfg.sync()
    frames=int(r[0])
    oframes = int(fro/fri*cfg.get('frames')) # Adjust oframes for difference between frame-rate-in and frame-rate-out
    if cfg.has('frames') and abs(frames-oframes)>2:
      warning('Encoding changed frames in "{}" from {:d} to {:d}'.format(infile,oframes,frames))
    cfg.set('frames',frames)
    cfg.set('duration',float(int(r[0])/fro))
    mdur=cfg.get('duration',cfg.get('duration'),section='MAIN')
    if abs(cfg.get('duration')-mdur)>60.0:
      warning('Video track "{}" duration differs (elongation={:f})'.format(infile,cfg.get('duration')/mdur))
  cfg.sync()
  return True


def build_result(cfg):
  r=regex.RegEx()
  for track in sorted([t for t in cfg.sections() if t.startswith('TRACK') and not cfg.get('disable',section=t)]):
    cfg.setsection(track)
    if cfg.get('type')=='audio' and cfg.has('language') and cfg.has('audio_languages',section='MAIN') and cfg.get('language') not in cfg.get('audio_languages',section='MAIN').split(";"): continue
    file=cfg.get('file')
    outfile=cfg.get('out_file',None)
    if not outfile: return False
    if not exists(outfile): return False
    if getsize(outfile)==0: return False

  cfg.setsection('MAIN')
  base=cfg.get('base')

  outfile=''
  if cfg.get('type')=='movie':
    if cfg.has('show') and not cfg.get('suppress_show',False):
      outfile=str(alphabetize(cfg.get('show'))) + ' '
    if cfg.has('episode'): outfile+= '- pt{:d} '.format(cfg.get('episode'))
    if cfg.has('year'): outfile+='({:04d}) '.format(cfg.get('year'))
    if cfg.has('song'): outfile+='{} '.format(str(cfg.get('song')))
  elif cfg.get('type')=='tvshow':
    if cfg.has('show') and not cfg.get('suppress_show',False):
      outfile=str(cfg.get('show')) + ' '
      if outfile.startswith('The '): outfile = outfile[4:]
      elif outfile.startswith('A '): outfile = outfile[2:]
      elif outfile.startswith('An '): outfile = outfile[3:]
    if cfg.has('season') and cfg.has('episode'):
      outfile+='S{:d}E{:02d} '.format(cfg.get('season'),cfg.get('episode'))
    elif cfg.has('season'):
      outfile+='S{:d} '.format(cfg.get('season'))
    elif cfg.has('episode'):
      outfile+='S1E{:02d} '.format(cfg.get('episode'))
    if cfg.has('song'): outfile+="{} ".format(str(cfg.get('song')))
  else:
    warning('Unrecognized type for "{}"'.format(base))
    outfile=cfg.get('base')
  outfile=outfile.strip().translate(str.maketrans('','',r':"/\:*?<>|'+r"'"))+'.mp4'
  if args.outdir: outfile=join(args.outdir,outfile)

  infiles=[cfg.filename]
  coverfiles=[]
  if cfg.has('coverart'):
    for c in cfg.get('coverart','').split(';'):
      if exists(c):
        coverfiles.append(c)
      elif args.artdir and exists(join(args.artdir,c)):
        coverfiles.append(join(args.artdir,c))
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
        warning('Duration of "{}" ({:f}s) deviates from track {} duration({:f}s).'.format(base,mdur,of,dur))

    call+=['-add',of]
    infiles.append(of)
    if cfg.has('name'): call[-1]+=':name='+cfg.get('name')
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
    warning('Result for "{}" has {:d} tracks.'.format(base,tracks))

  do_call(call,outfile)

  cfg.setsection('MAIN')
  call=['-tool', prog + ' ' + version + ' on ' + time.strftime('%A, %B %d, %Y, at %X')]
  if cfg.has('type'):
    call += [ '-type' , cfg.get('type') ]
  else:
    warning('"'+outfile+'" has no type')

  if cfg.has('genre'):
    call += [ '-genre' , cfg.get('genre') ]
  else:
    warning('"'+outfile+'" has no genre')

  if cfg.has('year'):
    call += [ '-year' , cfg.get('year') ]
  else:
    warning('"'+outfile+'" has no year')

  if cfg.has('season'): call += [ '-season' , cfg.get('season') ]
  if cfg.has('episode'): call += [ '-episode' , cfg.get('episode') ]
  if cfg.has('episodeid'): call += [ '-episodeid' , cfg.get('episodeid') ]
  if cfg.has('artist'): call += [ '-artist' , cfg.get('artist') ]
  if cfg.has('writer'): call += [ '-writer' , cfg.get('writer') ]
  if cfg.has('network'): call += [ '-network' , cfg.get('network') ]
#  if cfg.has('rating'): call += [ '-rating' , cfg.get('rating') ]
  if cfg.has('macroblocks',section='TRACK01'): call += [ '-hdvideo' , '1' if cfg.get('macroblocks',section='TRACK01')>=3600 else '0']
  if cfg.has('title'): call += [ '-show' , str(cfg.get('title'))]
  elif cfg.has('show'): call += [ '-show' , str(cfg.get('show'))]

  song=None
  if cfg.get('type')=='movie':
    if cfg.has('title') and cfg.has('song'): song = str(cfg.get('title')) + ": " + str(cfg.get('song'))
    elif cfg.has('title'): song = str(cfg.get('title'))
    elif cfg.has('song'): song = str(cfg.get('song'))
  elif cfg.has('song'): song = str(cfg.get('song'))
  if song: call+=['-song', song]

  cfg.sync()
  if cfg.has('description'):
#   TODO: Deal with quotes/special characters
    desc=cfg.get('description')
    if len(desc)>255:
      call += [ '-desc', desc[:255], '-longdesc', desc ]
    elif len(desc)>0:
      call += [ '-desc' , desc ]
  else:
    warning('"'+outfile+'" has no description')

  if cfg.has('comment'): call += [ '-comment' , cfg.get('comment') ]
  if call: do_call(['mp4tags'] + call + [outfile],outfile)

  debug('Adding chapters to "{}"'.format(outfile))
  chapterfile=splitext(outfile)[0]+'.chapters.txt'
  if exists(chapterfile) and getsize(chapterfile)!=0:
    warning('Adding chapters from existing config file "' + chapterfile + '"')
    do_call(['mp4chaps', '--import', outfile],outfile)
  elif cfg.has('chapter_time') and cfg.has('chapter_name'):
    delay=cfg.get('chapter_delay',0.0)
    elong=cfg.get('chapter_elongation',1.0)
    c=cfg.get('chapter_time')
    cts=[float(i) for i in c.split(';')] if isinstance(c,str) else [c]
    c=cfg.get('chapter_name')
    cns=[i.strip() for i in c.split(';')] if isinstance(c,str) else [c]
    with open(chapterfile,'wt', encoding='utf-8', errors='replace') as f:
      for (ct,cn) in zip(cts,cns):
        (neg,hours,mins,secs,msecs)=secsToParts(ct*elong+delay)
        f.write('{}{:02d}:{:02d}:{:02d}.{:03d} {} ({:d}m {:d}s)\n'.format(neg,hours,mins,secs,msecs,cn,(-1 if neg else 1)*hours*60+mins,secs))
    do_call(['mp4chaps', '--import', outfile],outfile)
    os.remove(chapterfile)
  cfg.sync()

  for i in coverfiles:
    debug('Adding coverart for "{}": "{}"'.format(outfile, i))
    do_call(['mp4art', '--add', i, outfile], outfile)
  if not(coverfiles):
      warning('"'+outfile+'" has no cover art')

  #do_call(['mp4file', '--optimize', outfile])
  return True

def main():
#    if getmtime(sys.argv[0])>progmodtime:
#      exec(compile(open(sys.argv[0]).read(), sys.argv[0], 'exec')) # execfile(sys.argv[0])

  for d in sources:
    for f in sorted(os.listdir(d)):
      if not isfile(join(d,f)):
        continue
      elif f.endswith(('.TIVO','.tivo','.TiVo')):
        prepare_tivo(join(d,f))
      elif f.endswith(('.MPG','.MPEG','.mpg','.mpeg')):
        prepare_mpg(join(d,f))
      elif f.endswith(('.VOB','.vob')):
        prepare_vob(join(d,f))
      elif f.endswith(('.MKV','.mkv')):
        prepare_mkv(join(d,f))
      else:
        warning('Source file type not recognized "' + join(d,f) + '"')

  for f in regex.reglob(r'.*\.cfg'):
    cfg = AdvConfig(f)
    if not cfg: continue
    update_description(cfg)
    update_coverart(cfg)
    build_result(cfg)

  for f in regex.reglob(r'.*\.cfg'):
    cfg = AdvConfig(f)
    if not cfg: continue
    for track in sorted([t for t in cfg.sections() if t.startswith('TRACK')]):
      cfg.setsection(track)
      if cfg.get('type')!='video': continue
      if cfg.get('disable',False): continue
      build_indices(cfg)

  for f in regex.reglob(r'.*\.cfg'):
    cfg = AdvConfig(f)
    if not cfg: continue
    for track in sorted([t for t in cfg.sections() if t.startswith('TRACK')]):
      cfg.setsection(track)
      if cfg.get('type')!='subtitles': continue
      if cfg.get('disable',False): continue
      build_subtitle(cfg)

  for f in regex.reglob(r'.*\.cfg'):
    cfg = AdvConfig(f)
    if not cfg: continue
    for track in sorted([t for t in cfg.sections() if t.startswith('TRACK')]):
      cfg.setsection(track)
      if cfg.get('type')!='audio': continue
      if cfg.get('disable',False): continue
      if cfg.has('language') and cfg.has('audio_languages',section='MAIN') and cfg.get('language') not in cfg.get('audio_languages',section='MAIN').split(";"): continue
      build_audio(cfg)

  for f in regex.reglob(r'.*\.cfg'):
    cfg = AdvConfig(f)
    if not cfg: continue
    for track in sorted([t for t in cfg.sections() if t.startswith('TRACK')]):
      cfg.setsection(track)
      if cfg.get('type')!='video': continue
      if cfg.get('disable',False): continue
      build_video(cfg)

if __name__ == "__main__":
  if 'parser' not in globals():
    parser = argparse.ArgumentParser(description='Extract all tracks from .mkv, .mpg, .TiVo, or .vob files; convert video tracks to h264, audio tracks to aac; then recombine all tracks into properly tagged .mp4',fromfile_prefix_chars='@',prog=prog,epilog='Written by: '+author)

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
    inifile='{}.ini'.format(splitext(sys.argv[0])[0])
    if exists(inifile): sys.argv.insert(1,'@'+inifile)
    inifile=prog + '.ini'
    if exists(inifile): sys.argv.insert(1,'@'+inifile)
    inifile='..\\' + prog + '.ini'
    if exists(inifile): sys.argv.insert(1,'@'+inifile)
    args = parser.parse_args()

  startlogging(args.logfile,args.loglevel,'90D')
  info(prog + ' ' + version + ' starting up.')
  nice(args.niceness)
  progmodtime=getmtime(sys.argv[0])

  sources=[]
  for d in args.sourcedirs:
    if not exists(d):
      warning('Source directory "'+d+'" does not exists')
    elif not isdir(d):
      warning('Source directory "'+d+'" is not a directory')
  #  elif not isreadable(d):
  #    warning('Source directory "'+d+'" is not readable')
    else:
      sources.append(d)

  work_lock_delete()
  sleep_state = None
  while True:
    sleep_state = sleep_change_directories(['.'] + sources, sleep_state)
    main()
    debug('Sleeping.')
