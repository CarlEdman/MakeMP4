#!/usr/bin/python

prog='MakeMP4'
version='7.0'
author='Carl Edman (CarlEdman@gmail.com)'
desc='''
Extract all tracks from .mkv, .mpg, .TiVo files;
convert video tracks to h264, audio tracks to aac;
then recombine all tracks into properly tagged .mp4
'''

import argparse
import glob
import json
import logging
import math
import os
import os.path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from fractions import Fraction

from cetools import * # pylint: disable=unused-wildcard-import
from tagmp4 import * # pylint: disable=unused-wildcard-import

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

def tracks(cfg, type = None):
  if cfg is None: return
  for t in sorted(cfg.sections()):
    if not t.startswith('TRACK'): continue
    track = cfg[t]
    if track['disable']: continue
    if type and track['type']!=type: continue
    yield track

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

def make_srt(cfg, track, files):
  # pylint: disable=unreachable
  return True
  main = cfg['MAIN']
  base = main['base']
  srtfile=f'{base} T{track:02d}.srt'
  if not os.path.exists(srtfile):
    do_call(['ccextractorwin'] + files + ['-o', srtfile],srtfile)
  if os.path.exists(srtfile) and os.path.getsize(srtfile)==0:
    os.remove(srtfile)
  if not os.path.exists(srtfile):
    return False
  track = cfg[f'TRACK{track:02d}']
  track['file'] = srtfile
  track['type'] = 'subtitles'
  track['delay'] = '0.0'
  track['elongation'] = '1.0'
  track['extension'] = 'srt'
  track['language'] = 'eng'
  cfg.sync()
  return True

def config_from_base(cfg, base):
  main = cfg['MAIN']
  main['base'] = base
  main['show'] = base

  #cfg.set('audio_languages','eng') # Set if we want to keep only some languages
  if (m := re.fullmatch(r'(?P<show>.*?) (pt\.? *(?P<episode>\d+) *)?\((?P<year>\d*)\) *(?P<song>.*?)',base)):
    main['type'] = 'movie'
    main['show'] = m['show']
    if m['episode']: main['episode'] = m['episode']
    main['year'] = m['year']
    main['song'] = m['song']
  elif (m := re.fullmatch(r'(?P<show>.*?) S(?P<season>\d+)E(?P<episode>\d+)$', base)) \
       or (m := re.fullmatch(r'(.*?) (Se\.\s*(?P<season>\d+)\s*)?Ep\.\s*(?P<episode>\d+)$', base)):
    main['type'] = 'tvshow'
    main['show'] = m['show']
    if m['season'] and m['season']!='0': main['season'] = m['season']
    main['episode'] = int(m['episode'])
  elif (m := re.fullmatch(r'(?P<show>.*) S(?P<season>\d+) +(?P<song>.*?)', base)) \
       or (m := re.fullmatch(r'(.*) Se\. *(?P<season>\d+) *(?P<song>.*?)', base)):
    main['type'] = 'tvshow'
    main['show'] = m['show']
    main['season'] = m['season']
    main['song'] = m['song']
  elif m := re.fullmatch(r'(?P<show>.*) (S(?P<season>\d+))?(V|Vol\. )(?P<episode>\d+)', base):
    main['type'] = 'tvshow'
    main['show'] = m['show']
    main['season'] = m['season']
    main['episode'] = m['episode']
  elif m := re.fullmatch(r'(?P<show>.*) S(?P<season>\d+)D\d+', base):
    main['type'] = 'tvshow'
    main['show'] = m['show']
    main['season'] = m['season']
    main['episode'] = None
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
  cfg=SyncConfig(cfgfile)
  config_from_base(cfg, base)
  work_lock(cfgfile)

  tid=1
  dgifile=f'{base} T{tid:02d}.d2v'
  if not os.path.exists(dgifile):
    do_call(['dgindex', '-i', mpgfile, '-o', os.path.splitext(base)[0], '-fo', '0', '-ia', '3', '-om', '2', '-hide', '-exit'],base+'.d2v')
#    do_call(['DGIndexNV', '-i', mpgfile, '-a', '-o', dgifile, '-h', '-e'],dgifile)
  if not os.path.exists(dgifile): return
  track = cfg[f'TRACK{tid:02d}']
  track['file'] = mpgfile
  cfg.sync()
  config_from_dgifile(cfg, track)

  for file in glob.iglob(f'{base} .*'):
    m = re.fullmatch(re.escape(base)+r'\s+T[0-9a-fA-F][0-9a-fA-F]\s+(.*)\.(ac3|dts|mpa|mp2|wav|pcm)',file)
    if not m: continue
    feat=m[1]
    ext=m[2]
    tid+=1
    track = cfg[f'TRACK{tid:02d}']
    nf=f'{base} T{tid:02d}.{ext}'
    os.rename(file,nf)
    cfg.set('file',nf)
    cfg.set('type','audio')
    cfg.set('extension',ext)
    cfg.set('quality',55)
    cfg.set('delay',0.0)
#    cfg.set('elongation',1.0)
#    cfg.set('normalize',False)
    cfg.set('features',feat)
    if m := re.search(r'\bDELAY (-?\d+)ms\b',feat):
      cfg.set('delay',float(m[1])/1000.0)
    if m := re.search(r'([_0-9]+)ch\b',feat):
      cfg.set('channels',m[1])
#      if m[1]=="3_2": cfg.set('downmix',2)
    if m := re.search(r'\b([\d.]+)(K|Kbps|bps)\b',feat):
      bps=int(m[1])
      if m[2][0]=="K": bps=bps*1000
      cfg.set('bit_rate',bps)
    if m := re.search(r'\b([0-9]+)bit\b',feat):
      cfg.set('bit_depth',m[1])
    if m := re.search(r'\b([0-9]+)rate\b',feat):
      cfg.set('sample_rate',m[1])
    if m := re.search(r'\b([a-z]{3})-lang\b',feat):
      cfg.set('language',m[1])
    cfg.sync()

  if make_srt(cfg,tid+1,[mpgfile]): tid+=1

  if args.delete_source:
    os.remove(mpgfile)

  cfg.sync()
  work_unlock(cfgfile)

def prepare_mkv(mkvfile):
  base=os.path.splitext(os.path.basename(mkvfile))[0]
  cfgfile=base+'.cfg'
  if not readytomake(cfgfile,mkvfile): return False
  cfg=SyncConfig(cfgfile)
  config_from_base(cfg,base)
  work_lock(cfgfile)

  main = cfg['MAIN']

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
    main['chapter_delay'] = 0.0
    main['chapter_elongation'] = 1.0
    main['chapter_uid'] = ';'.join(chap_uid)
    if chap_time: main['chapter_time'] = ';'.join(chap_time)
    if chap_hidden: main['chapter_hidden'] = ';'.join(chap_hidden)
    if chap_enabled: main['chapter_enabled'] = ';'.join(chap_enabled)
    if chap_name: main['chapter_name'] = ';'.join(chap_name)
    if chap_lang: main['chapter_language'] = ';'.join(chap_lang)
    cfg.sync()
  except ET.ParseError:
    log.warning(f'No valid XML chapters for {mkvfile}.')

  j = json.loads(subprocess.check_output(['mkvmerge','-J',mkvfile]).decode(errors='replace'))
  main['container_type'] = j['container']['type']

  for k, v in j['container']['properties'].items():
    if k=='duration':
      main['duration'] = str(int(v)/1000000000.0)
    else:
      main['container_property_'+k] = str(v)

  skip_a_dts = False
  for t in j['tracks']:
    tid = t['id']+1
    track = cfg[f'TRACK{tid:02d}']
    track['mkvtrack'] = t['id']
    track['type'] = t['type']
    track['format'] = t['codec']

    if track['format'] in {'V_MPEG2','MPEG-1/2',}:
      track['extension'] = 'mpg'
      track['file'] = f'{base} T{tid:02d}.mpg'
      track['dgifile'] = f'{base} T{tid:02d}.dgi'
    elif track['format'] in {'V_MPEG4/ISO/AVC','MPEG-4p10/AVC/h.264',}:
      track['extension'] = '264'
      track['file'] = f'{base} T{tid:02d}.264'
#        track['t2cfile'] = f'{base} T{tid:02d}.t2c'
      track['dgifile'] = f'{base} T{tid:02d}.dgi'
    elif track['format'] in {'V_MS/VFW/FOURCC, WVC1','VC-1',}:
      track['extension'] = 'wvc'
      track['file'] = f'{base} T{tid:02d}.wvc'
#        track['t2cfile'] = f'{base} T{tid:02d}.t2c'
      track['dgifile'] = f'{base} T{tid:02d}.dgi'
    elif track['format'] in {'A_AC3','A_EAC3','AC3/EAC3','AC-3/E-AC-3', 'AC-3','E-AC-3'}:
      track['extension'] = 'ac3'
      track['file'] = f'{base} T{tid:02d}.ac3'
      track['quality'] = 60
    elif track['format'] in {'E-AC-3'}:
      log.warning(f'{main["base"]}: Track type {track["format"]} in {mkvfile} not supported, disabling.')
      track['disable'] = True
      track['extension'] = 'ac3'
      track['file'] = f'{base} T{tid:02d}.ac3'
      track['quality'] = 60
    elif track['format'] in {'TrueHD','A_TRUEHD','TrueHD Atmos',}:
      track['extension'] = 'thd'
      track['file'] = f'{base} T{tid:02d}.thd'
      track['quality'] = 60
      skip_a_dts = True
    elif track['format'] in {'DTS-HD Master Audio',}:
      track['extension'] = 'dts'
      track['file'] = f'{base} T{tid:02d}.dts'
      track['quality'] = 60
      skip_a_dts = True
    elif track['format'] in {'A_DTS', 'DTS', 'DTS-ES', 'DTS-HD High Resolution', 'DTS-HD High Resolution Audio',}:
      track['extension'] = 'dts'
      track['file'] = f'{base} T{tid:02d}.dts'
      track['quality'] = 60
      if skip_a_dts:
        track['disable'] = True
        skip_a_dts = False
    elif track['format'] in {'A_PCM/INT/LIT','PCM',}:
      track['extension'] = 'pcm'
      track['file'] = '{base} T{tid:02d}.pcm'
      track['quality'] = 60
    elif track['format'] in {'S_VOBSUB','VobSub',}:
      track['extension'] = 'idx'
      track['file'] = f'{base} T{tid:02d}.idx'
    elif track['format'] in {'S_HDMV/PGS','HDMV PGS','PGS',}:
      track['extension'] = 'sup'
      track['file'] = '{base} T{tid:02d}.sup'
    elif track['format'] in {'SubRip/SRT',}:
      track['extension'] = 'srt'
      track['file'] = '{base} T{tid:02d}.srt'
    elif track['format'] in {'A_MS/ACM',}:
      track['disable'] = True
    else:
      log.warning(f'{main["base"]}: Unrecognized track type {track["format"]} in {mkvfile}')
      track['disable'] = True

    for k,v in t['properties'].items():
      if k == 'language':
        track['language'] = iso6392BtoT.get(v, v)
      elif k == 'display_dimensions':
        (track['display_width'], track['display_height']) = v.split('x')
      elif k == 'pixel_dimensions':
        (track['pixel_width'], track['pixel_height']) = v.split('x')
      # elif k == 'default_track':
      #   track['defaulttrack'] = int(v)!=0
      elif k == 'forced_track':
        track['forcedtrack'] = int(v)!=0
      elif k == 'default_duration':
        track['frameduration'] = int(v)/1000000000.0
      elif k == 'track_name':
        track['trackname'] = v
      # elif k == 'minimum_timestamp':
      #   track['delay'] = int(v)/1000000000.0
      elif k == 'audio_sampling_frequency':
        track['samplerate'] = v
      elif k == 'audio_channels':
        track['channels'] = v
      # if int(v)>2: track['downmix'] =
      else:
        track['property_'+k] = v

  cfg.sync()

  extract=[]
  for track in tracks(cfg):
    file=track['file']
    mkvtrack=track['mkvtrack']
    if (args.keep_video_in_mkv and track['type'] =='video') \
       or (args.keep_audio_in_mkv and track['type']=='audio'):
      track['extension'] = 'mkv'
      track['file'] = mkvfile
    elif file and not os.path.exists(file) and mkvtrack:
      extract.append(f'{mkvtrack:d}:{file}')

  if extract: do_call(['mkvextract', 'tracks', mkvfile] + extract)
  cfg.sync()

  for track in tracks(cfg, 'video'):
    if make_srt(cfg,tid+1,[track['file']]): tid+=1
  cfg.sync()

  tcs=[]
  for track in tracks(cfg):
    if 't2cfile' not in track: continue
    t2cfile=track['t2cfile']
    mkvtrack=track['mkvtrack']
    if t2cfile and not os.path.exists(t2cfile) and mkvtrack:
      tcs.append(f'{mkvtrack}:{t2cfile}')
  if tcs: do_call(['mkvextract', 'timecodes_v2', mkvfile] + tcs)
  cfg.sync()

  for track in tracks(cfg):
    if track['extension'] != '.sub': continue
    t2cl = []
    with open(track["t2cfile"],'rt', encoding='utf-8') as fp:
      for l in fp:
        try:
          t2cl.append(float(l))
        except ValueError:
          log.warning(f'Unrecognized line "{l}" in {track["t2cfile"]}, skipping.')
    if len(t2cl)==0: continue
#    oframes = track['frames']
#    frames = len(t2cl)-1
#    if oframes>0 and frames != oframes:
#      log.warning(f'Timecodes changed frames in "{file}" from {oframes:d} to {frames:d}')
#    cfg.set('frames',frames)
    duration=t2cl[-1]/1000.0
    oduration=track.getfloat('duration')
    if oduration and oduration>0 and oduration!=duration:
      log.warning(f'Encoding changed duration in "{file}" from {oduration:f} to {duration:f}')
    track['duration'] = duration
    cfg.sync()

  for track in tracks(cfg, 'subtitle'):
    if track['extension'] != '.sub': continue
    idxfile = os.path.splitext(track['file'])[0]+'.idx'
    timestamp=[]
    filepos=[]
    with open(idxfile, 'rt', encoding='utf-8', errors='replace').read() as fp:
      for l in fp:
        if re.fullmatch(r'\s*#.*',l): continue
        elif re.fullmatch(r'\s*',l): continue
        elif (m := re.fullmatch(r'\s*timestamp:\s*(?P<time>.*),\s*filepos:\s*(?P<pos>[0-9a-fA-F]+)\s*',l)) and (t := parse_time(m['time'])):
          timestamp.append(str(t))
          filepos.append(m['pos'])
        elif (m := re.fullmatch(r'\s*id\s*:\s*(\w+?)\s*, index:\s*(\d+)\s*',l)):
          track['language'] = m[1] # Convert to 3 character codes
          track['langindex'] = m[2]
        elif (m := re.fullmatch(r'\s*(\w+)\s*:\s*(.*?)\s*',l)):
          track[m[1]] = m[2]
        else:
          log.warning(f'{cfg["MAIN"]["base"]}: Ignorning in {idxfile} uninterpretable line: {l}')
    track['timestamp'] = ','.join(timestamp)
    track['filepos'] = ','.join(filepos)
    # remove idx file
    cfg.sync()

  if args.delete_source:
    os.remove(mkvfile)

  work_unlock(cfgfile)

def config_from_dgifile(cfg, track):
  if not track['file'] or not track['dgifile']: return
  logfile = os.path.splitext(track['file'])[0]+'.log'

  while True:
    time.sleep(1)
    if not os.path.exists(logfile): continue
    with open(logfile,'rt', encoding='utf-8', errors='replace') as fp:
      for l in fp:
        if m := re.fullmatch('([^:]*):(.*)',l):
          k = 'dg' + ''.join(i for i in m[1].casefold() if i.isalnum())
          v = m[2].strip()
          if not v: continue
          if track[k] == v: continue
          elif track[k]: track[k] += f';{v}'
          else: track[k] = f'{v}'
        else:
          log.warning(f'Unrecognized DGIndex log line: "{repr(l)}"')
    if track['dginfo']=='Finished!': break
  os.remove(logfile)
  cfg.sync()

  with open(track['dgifile'], 'rt', encoding='utf-8', errors='replace') as fp: dgi=fp.read()
  dgip=dgi.split('\n\n')
  if len(dgip)!=4:
    log.error(f'Malformed index file {track["dgifile"]}')
    open(track["dgifile"],'w').truncate(0)
    return False
  if re.match('DG(AVC|MPG|VC1)IndexFileNV(14|15|16)',dgip[0]):
    m = re.search(r'\bCLIP\ *(?P<left>\d+) *(?P<right>\d+) *(?P<top>\d+) *(?P<bottom>\d+)',dgip[2])
    if not m:
      log.error(f'No CLIP in {track["dgifile"]}')
      open(track["dgifile"],'w').truncate(0)
      return False

    cl = int(m['left'])
    cr = int(m['right'])
    ct = int(m['top'])
    cb = int(m['bottom'])
    m = re.search(r'\bSIZ *(?P<sizex>\d+) *x *(?P<sizey>\d+)',dgip[3])
    if not m:
      log.error(f'No SIZ in {track["dgifile"]}')
      open(track["dgifile"],'w').truncate(0)
      return False
    psx = int(m['sizex'])
    psy = int(m['sizey'])

    if cfg.has('dgsar'):
      sarf=cfg.get('dgsar')
    elif cfg.has('display_width') and cfg.has('display_height') and cfg.has('pixel_width') and cfg.has('pixel_height'):
      sarf=Fraction(cfg.get('display_width')*cfg.get('pixel_height'),cfg.get('display_height')*cfg.get('pixel_width'))
#    elif m := re.fullmatch(r'\s*(\d+)\s*x\s*(\d+)\s*XXX\s*(\d+)\s*:(\d+)',cfg.get('dgdisplaysize','')+'XXX'+cfg.get('dgaspectratio','')):
#      sarf=Fraction(int(m[2])*int(m[3]),int(m[1])*int(m[4]))
#    elif m := re.fullmatch(r'\s*(\d+)\s*x\s*(\d+)\s*XXX\s*(\d+)\s*:(\d+)',cfg.get('dgcodedsize','')+'XXX'+cfg.get('dgaspectratio','')):
#      sarf=Fraction(int(m[2])*int(m[3]),int(m[1])*int(m[4]))
#    elif cfg.has('display_width') and cfg.has('display_height') and re.fullmatch(r'\s*(\d+)\s*x\s*(\d+)\s*$',cfg.get('picture_size','')):
#      sarf=Fraction(cfg.get('display_width')*int(m[1]),cfg.get('display_height')*int(m[2]))
    else:
      log.warning(f'Guessing 1:1 SAR for {track["dgifile"]}')
      sarf=Fraction(1,1)

    m = re.search(r'\bORDER *(?P<order>\d+)',dgip[3])
    if not m:
      log.error(f'No ORDER in {track["dgifile"]}')
      open(track["dgifile"],'w').truncate(0)
      return False
    fio=int(m['order'])

    m = re.search(r'\bFPS *(?P<num>\d+) */ *(?P<denom>\d+) *',dgip[3])
    if not m:
      log.error(f'No FPS in {track["dgifile"]}')
      open(track["dgifile"],'w').truncate(0)
      return False
    frf=Fraction(int(m['num']),int(m['denom']))

    m = re.search(r'\b(?P<ipercent>\d*\.\d*)% *FILM',dgip[3])
    if not m:
      log.error(f'No FILM in {track["dgifile"]}')
      open(track["dgifile"],'w').truncate(0)
      return False
    ilp = float(m['ipercent'])/100.0

    if fio == 0:
      ilt = 'PROGRESSIVE'
    elif ilp>0.5:
      ilt = 'FILM'
    else:
      ilt = 'INTERLACE'

    # ALSO 'CODED' FRAMES
    m = re.search(r'\bPLAYBACK *(?P<playback>\d+)',dgip[3])
    if not m:
      log.error(f'No PLAYBACK in {track["dgifile"]}')
      open(track["dgifile"],'w').truncate(0)
      return False
    frames = int(m['playback'])
  elif re.match(r'DGIndexProjectFile16',dgip[0]):
    m = re.search(r'FINISHED\s+([0-9.]+)%\s+(.*?)\s*',dgip[3])
    if not m: return False

    ilp=float(m[1])/100.0
    ilt=m[2]

    m = re.search(r'\bAspect_Ratio=(\d+):(\d+)',dgip[1])
    if not m: return False
    arf=Fraction(int(m[1]),int(m[2]))

    m = re.search(r'\bClipping=\ *(\d+) *, *(\d+) *, *(\d+) *, *(\d+)',dgip[1])
    if not m: return False
    cl,cr,ct,cb=[int(m[i]) for i in range(1, 5)]

    m = re.search(r'\bPicture_Size= *(\d+)x(\d+)',dgip[1])
    if not m: return False
    psx,psy=[int(m[i]) for i in range(1, 3)]
    sarf=arf/Fraction(psx,psy)

    m = re.search(r'\bField_Operation= *(\d+)',dgip[1])
    if not m: return False
    fio=int(m[1])

    m = re.search(r'\bFrame_Rate= *(\d+) *\((\d+)/(\d+)\)',dgip[1])
    if not m: return False
    frf=Fraction(int(m[2]),int(m[3]))

    frames=0
    for l in dgip[2].splitlines():
      if m := re.fullmatch(r'([0-9a-f]+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(?P<flags>([0-9a-f]+ +)*[0-9a-f]+)\s*',l):
        frames += len(m[8].split())
  else:
    log.error(f'Unrecognize index file {track["dgifile"]}')
    open(track["dgifile"],'w').truncate(0)
    return

  cfg.set('type', 'video')
#  cfg.set('file', dgip[1].splitlines()[0])
  cfg.set('dgifile', track["dgifile"])
  cfg.set('interlace_type', ilt)
  cfg.set('interlace_type_fraction', ilp)
  cfg.set('field_operation', fio)
  cfg.set('frame_rate_ratio', str(frf))

  #cfg.set('out_format', 'h264')
  cfg.set('out_format', 'h265')

  cfg.set('crop', 'auto')
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


def build_indices(cfg, track):
  file=track['file']
  dgifile=track['dgifile']
  if not dgifile or os.path.exists(dgifile): return False
  if dgifile.endswith('.dgi'):
    do_call(['DGIndexNV', '-i', file, '-o', dgifile, '-h', '-e'],dgifile)
  elif dgifile.endswith('.d2v'):
    do_call(['dgindex', '-i', file, '-o', os.path.splitext(dgifile)[0], '-fo', '0', '-ia', '3', '-om', '2', '-hide', '-exit'],dgifile)
  else:
    return False
  config_from_dgifile(cfg, track)

def build_subtitle(cfg, track):
  infile = track['file']
  inext  = track['extension']
  delay = track.getfloat('delay') or 0.0
  elong = track.getfloat('elongation') or 1.0

  if os.path.getsize(infile)==0:
    return False
  elif inext=='srt':
    track['outfile'] = outfile = os.path.splitext(infile)[0]+'.ttxt'
    if os.path.exists(outfile): return False # Should be not readytomake(outfile,)
    with open(infile, 'rt', encoding='utf-8', errors='replace') as i, open('temp.srt', 'wt', encoding='utf-8', errors='replace') as o:
      for l in i.read().split('\n\n'):
        if not l.strip():
          continue
        elif (m := re.fullmatch(r'(?s)(?P<beg>\s*\d*\s*)(?P<time1>.*)(?P<mid> --> )(?P<time2>.*)',l)) and (t1 := parse_time(m['time1'])) and (t2 := parse_time(m['time2'])) and (s1 := t1*elong+delay)>=0 and (s2 := t2*elong+delay)>=0:
          o.write(f'{m["beg"]}{unparse_time(s1)}{m["mid"]}{unparse_time(s2)}{m["end"]}\n\n')
        else:
          log.warning(f'Unrecognized line in {infile}: {repr(l)}')

    do_call(['mp4box','-ttxt','temp.srt'],outfile)
    if os.path.exists('temp.ttxt'): os.rename('temp.ttxt',outfile)
    if os.path.exists('temp.srt'): os.remove('temp.srt')
  elif inext=='sup' and os.path.getsize(infile)<1024:
    outfile = os.path.splitext(infile)[0]+'.idx'
  elif inext=='sup':
    track['outfile'] = outfile = os.path.splitext(infile)[0]+'.idx'
    if os.path.exists(outfile): return  # Should be not readytomake(outfile,)
    call = ['bdsup2sub++', '--resolution','keep']
    if delay!=0.0: call += ['--delay',str(d)]

    fps = track.getfraction('frame_rate_ratio_out') or cfg['TRACK01'].getfraction('frame_rate_ratio_out')
    fps2target = { 24.0: '24p', Fraction(24000,1001): '24p'
                 , 25.0: '25p', Fraction(25000,1001): '25p'
                 , 30.0: '30p', Fraction(30000,1001): '30p' }
    if fps in fps2target: call += [ '--fps-target', fps2target[fps] ]

    call += ['--output', outfile, infile]
    do_call(call,outfile) # '--fix-invisible',
  elif (delay!=0.0 or elong!=1.0) and inext=='idx':
    track['outfile'] = outfile = os.path.splitext(infile)[0]+'.adj'+os.path.splitext(infile)[1]
    if not os.path.exists(os.path.splitext(infile)[0]+'.adj.sub'):
      shutil.copy(os.path.splitext(infile)[0]+'.sub',os.path.splitext(infile)[0]+'.adj.sub')
    if os.path.exists(outfile): return  # Should be not readytomake(outfile,)
    with open(infile, 'rt', encoding='utf-8', errors='replace') as i, open(outfile, 'wt', encoding='utf-8', errors='replace') as o:
      for l in i:
        if (m := re.fullmatch(r'(?s)(?P<beg>\s*timestamp:\s*)\b(?P<time>.*\d)\b(?P<end>.*)',l)) and (t := parse_time(m['time'])):
          s = t*elong+delay
          if s >= 0: o.write(f'{m["beg"]}{unparse_time(s)}{m["end"]}')
        else:
          o.write(l)
  elif (delay!=0.0 or elong!=1.0):
    track['outfile'] = outfile = infile
    log.warning(f'Delay and elongation not implemented for subtitles type "{infile}"')
  else:
    track['outfile'] = outfile = infile

  if os.path.getsize(infile)==0 or not os.path.exists(outfile):
    cfg.set('disable',True)
    return False
  cfg.sync()
  return True


def build_audio(cfg, track):
   # pylint: disable=used-before-assignment
  main = cfg['main']
  track["outfile"] = track["outfile"] or f'{main["base"]} T{cfg.getsection()[5:]}.m4a'
  cfg.sync()
  if not readytomake(track["outfile"],track["infile"]): return False

  if track['extension'] in (): # ('dts', 'thd'):
    call = [ 'dcadec', '-6', track["infile"], '-']
  else:
    call = [ 'eac3to', track["infile"]]
    if track['extension']=='mkv': call.append(f'{track["mkvtrack"]+1}:')
    call.append('stdout.wav')
    # call.append('-no2ndpass')
    call.append('-log=nul')
    if track['delay']: call.append(f'{track["delay"]*1000.0:+.0f}ms')
    if track['elongation'] and track['elongation'] != 1.0:
      log.warning(f'Audio elongation not implemented')
    # if track['channels']==7: call.append('-0,1,2,3,5,6,4')

    if track.getint('downmix')==6: call.append('-down6')
    elif track.getint('downmix')==2: call.append('-downDpl')
    elif track['downmix']: log.warning(f'Invalid downmix "{track["downmix"]}"')

    if track['normalize']: call.append('-normalize')

  call += [ '|', 'qaac64', '--threading', '--ignorelength', '--no-optimize' ]
  call += [ '--tvbr', track['quality'] or "60", '--quality', '2', '-', '-o', track["outfile"]]

  res=do_call(call, track["outfile"])
  if res and (m := re.match(r'\bwrote (\d+\.?\d*) seconds\b',res)):
    track['duration'] = m[1]
  if ( dur := track.getfloat('duration') ) and \
     ( mdur := main.getfloat('duration') ) and \
     abs(dur - mdur)>0.5:
    log.warning(f'Audio track "{track["infile"]}" duration differs (elongation={mdur/dur})')
  cfg.sync()
  return True


def build_video(cfg, track):
  infile = cfg.get('file')
  dgifile = cfg.get('dgifile', None)

  outfile = cfg.get('outfile')
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
    cfg.set('outfile',outfile)
  avsfile = cfg.get('avs_file',os.path.splitext(os.path.basename(infile))[0] +'.avs' )
  cfg.set('avs_file',avsfile)
  cfg.sync()

  if not readytomake(outfile,infile,dgifile): return False

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
    if m := re.fullmatch(r'\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*$',cfg.get('crop')):
      cl,cr,ct,cb=[int(m[i]) for i in range(1, 5)]
      if m := re.fullmatch(r'\s*(\d+)\s*x\s*(\d+)\s*$',cfg.get('picture_size','')):
        px, py=[int(m[i]) for i in range(1, 3)]
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
    log.error(f'{outfile}: Unrecognized output format "{cfg.get("out_format", "UNSPECIFIED")}"')
    return False

  call += ['--fps', str(fro)]
  sarf=cfg.get('sample_aspect_ratio')
  if isinstance(sarf,Fraction): call += ['--sar', f'{sarf.numerator:d}:{sarf.denominator:d}']
  call += [ '--output', outfile ]

  cfg.sync()
  res=do_call(call,outfile)
  if res and (m := re.match(r'\bencoded (\d+) frames\b',res)):
    cfg.sync()
    frames=int(m[1])
    oframes = int(fro/fri*cfg.get('frames')) # Adjust oframes for difference between frame-rate-in and frame-rate-out
    if cfg.has('frames') and abs(frames-oframes)>2:
      log.warning(f'Encoding changed frames in "{infile}" from {oframes:d} to {frames:d}')
    cfg.set('frames',frames)
    cfg.set('duration',float(frames/fro))
    mdur=cfg.get('duration',cfg.get('duration'),section='MAIN')
    if abs(cfg.get('duration')-mdur)>60.0:
      log.warning(f'Video track "{infile}" duration differs (elongation={cfg.get("duration")/mdur:f})')
  cfg.sync()
  return True

def build_result(cfg):
  main = cfg['MAIN']
  for track in tracks(cfg):
    if track['type']=='audio' and track['language'] and main['audio_languages'] and track['language'] not in main['audio_languages'].split(";"): continue
    if track['type']=='video' and (mbs := track.getint('macroblocks')):
      main['hdvideo'] = mbs >= 3600
    if not track['outfile']: return False
    if not os.path.exists(track['outfile']): return False
    if os.path.getsize(track['outfile'])==0: return False

  base=main['base']
  outfile = make_filename(main)
  if not outfile:
    log.error(f"Unable to generate filename for {main}.")
    return False
  if args.outdir: outfile = os.path.join(args.outdir,outfile)

  infiles=[cfg.filename]
  coverfiles=[]
  for c in main.getlist('coverart'):
    if os.path.dirname(c)==None and args.artdir:
      c = os.path.join(args.artdir, c)
    if os.path.exists(c):
      coverfiles.append(c)
  infiles+=coverfiles

  call=['mp4box', '-new', outfile]
  trcnt = { }
  mdur=main.getfloat('duration')

  for track in tracks(cfg):
    if cfg.get('type')=='audio' and cfg.has('language') and cfg.has('audio_languages',section='MAIN') and cfg.get('language') not in cfg.get('audio_languages',section='MAIN').split(";"): continue
    of = track['outfile']
    dur = track.getfloat('duration')
    if mdur and dur:
      if abs(mdur-dur)>0.5 and abs(mdur-dur)*200>mdur:
        log.warning(f'Duration of "{base}" ({mdur:f}s) deviates from track {of} duration({dur:f}s).')

    call+=['-add',of]
    infiles.append(of)

    if name := track.getstr('name') or track.getstr('trackname'):
      call[-1]+=':name='+name

    if lang := track.getstr('language'):
      call[-1]+=':lang='+lang
    if fps := track.getfraction('frame_rate_ratio_out'):
      call[-1] += ':fps=' + str(float(fps))
    if mdur or dur: call[-1] += ':dur=' + str(mdur or dur)

    if track['type'] in trcnt:
      trcnt[track['type']] += 1
    else:
      trcnt[track['type']] = 1
      if track['type'] == 'audio' and not track['defaulttrack']: call[-1]+=':disable'

  if not readytomake(outfile,*infiles): return False

  if sum(trcnt.values())>18:
    log.warning(f'Result for "{base}" has more than 18 tracks.')

  main['tool'] = f'{prog} {version} on {time.strftime("%A, %B %d, %Y, at %X")}'
  cfg.sync()
  do_call(call,outfile)
  cfg.sync()
  set_meta_mutagen(outfile, main)
  set_chapters_cmd(outfile, main)
  cfg.sync()
  return True

def build_meta(cfg):
  def upd(i):
    if not i: return
    for k,v in i.items():
      if not v:
        continue
      elif k == 'comment':
        main['comment'] = semicolon_join(v, main['comment'])
      elif main[k] is None:
        main[k] = v

  if not cfg.has_section('MAIN'): return False
  main = cfg['MAIN']
  title  = main.getstr('title') or main.getstr('show') or main['base']
  season = main.getint('season')
  fn = f'{main["show"] or ""}{" " + str(season) if season else ""}'

  descpath = os.path.join(args.descdir, f'{fn}.txt')
  upd(get_meta_local(title, main['season'], main['episode'], descpath))
  upd(get_meta_imdb(title, main['season'], main['episode'],
      os.path.join(args.artdir, f'{fn}.jpg'),
      main['imdb_id'], main['omdb_status'], args.omdbkey))

  ufn = ''.join([c for c in fn.strip().upper() if c.isalnum()])
  upd({ 'year': f'_{ufn}YEAR_'
      , 'genre': f'_{ufn}GENRE_'
      , 'description': f'_{ufn}DESC_'
      , 'coverart': ';'.join(i for i in reglob(rf'{fn}(\s*P\d+)?(.jpg|.jpeg|.png)', args.artdir)) })

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
      elif f.endswith(('.MKV','.mkv')):
        prepare_mkv(os.path.join(d,f))
      else:
        log.warning(f'Source file type not recognized "{os.path.join(d,f)}"')

  for f in glob.iglob(r'*.cfg'):
    if (cfg := SyncConfig(f)):
      build_meta(cfg)

  for f in glob.iglob(r'*.cfg'):
    if (cfg := SyncConfig(f)):
      build_result(cfg)

  for f in glob.iglob(r'*.cfg'):
    for track in tracks(cfg := SyncConfig(f), 'video'):
      build_indices(cfg, track)

  for f in glob.iglob(r'*.cfg'):
    for track in tracks(cfg := SyncConfig(f), 'subtitles'):
      build_subtitle(cfg, track)

  for f in glob.iglob(r'*.cfg'):
    cfg = SyncConfig(f)
    if not cfg.has_section('MAIN'): continue
    main = cfg['MAIN']
    for track in tracks(cfg, 'audio'):
      if track['language'] and main['audio_languages'] and track['languages'] not in main['audio_languages'].split(";"):
        continue
      build_audio(cfg, track)

  for f in glob.iglob(r'*.cfg'):
    for track in tracks(cfg := SyncConfig(f), 'video'):
      build_video(cfg, track)


if __name__ == "__main__":
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

