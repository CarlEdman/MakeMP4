#!/usr/bin/python
# A Python frontend to various audio/video tools to automatically convert to MP4/H264/AAC-LC and tag the results

prog='MakeMP4'
version='4.0'
author='Carl Edman (CarlEdman@gmail.com)'

import string, re, os, sys, argparse, logging, time, math, shutil, tempfile
from subprocess import call, check_call, check_output, CalledProcessError, Popen, PIPE, STDOUT, list2cmdline
from os.path import exists, isfile, isdir, getmtime, getsize, join, basename, splitext, abspath, dirname
from fractions import Fraction

from AdvConfig import AdvConfig
from cetools import *
import regex

langNameToISO6392T = { 'English':'eng', 'Français': 'fra', 'Japanese':'jpn', 'Español':'esp' , 'German':'deu', 'Deutsch':'deu', 'Svenska':'swe', 'Latin':'lat', 'Dutch':'nld', 'Chinese':'zho' }
iso6392BtoT = { 'alb':'sqi', 'arm':'hye', 'baq':'eus', 'bur':'mya', 'chi':'zho', 'cze':'ces', 'dut':'nld', 'fre':'fra', 'geo':'kat', 'ger':'deu', 'gre':'ell', 'ice':'isl', 'mac':'mkd', 'mao':'mri', 'may':'msa', 'per':'fas', 'rum':'ron', 'slo':'slk', 'tib':'bod', 'wel':'cym' }


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
  outstr = outstr.decode(encoding='cp1252')
  errstr = errstr.decode(encoding='cp1252')
  errstr += "".join([p.stderr.read().decode(encoding='cp1252') for p in ps if not p.stderr.closed])
  outstr=cookout(outstr)
  errstr=cookout(errstr)
  if outstr: debug('Output: '+repr(outstr))
  if errstr: debug('Error: '+repr(errstr))
  if ps[-1].poll()!=0:
    error('Error code for ' + repr(cstr))
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
  cfg.set('year','')
  cfg.set('genre','')
  cfg.set('song','')
  cfg.set('description','')
  cfg.set('audio_languages','eng')
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
  cfg.sync(True)


def config_from_dgifile(cfg,dgifile):
  with open(dgifile, 'rt') as fp: dgi=fp.read()
  dgip=dgi.split('\n\n')
  if len(dgip)!=4:
    critical('Malformed index file ' + dgifile)
    exit(1)
  r=regex.RegEx()
  if r(r'^(DGAVCIndexFileNV14|DGMPGIndexFileNV14|DGVC1IndexFileNV14)',dgip[0]):
    if not r(r'\bCLIP\ *(?P<left>\d+) *(?P<right>\d+) *(?P<top>\d+) *(?P<bottom>\d+)',dgip[2]):
      critical('No CLIP in ' + dgifile)
      exit(1)
    cl=int(r.left)
    cr=int(r.right)
    ct=int(r.top)
    cb=int(r.bottom)
    cl=cr=ct=cb=0
    if not r(r'\bSIZ *(?P<sizex>\d+) *x *(?P<sizey>\d+)',dgip[3]):
      critical('No SIZ in ' + dgifile)
      exit(1)
    psx=int(r.sizex)
    psy=int(r.sizey)
    # HACK TODO
    if psx==720 and psy==480:
      sarf=Fraction(32,27)
    else:
      sarf=Fraction(1,1)
    if not r(r'\bORDER *(?P<order>\d+)',dgip[3]):
      critical('No ORDER in ' + dgifile)
      exit(1)
    fio=int(r.order)
    if not r(r'\bFPS *(?P<num>\d+) */ *(?P<denom>\d+) *',dgip[3]):
      critical('No FPS in ' + dgifile)
      exit(1)
    frf=Fraction(int(r.num),int(r.denom))
    if not r(r'\b(?P<ipercent>\d*\.\d*)% *FILM',dgip[3]):
      critical('No FILM in ' + dgifile)
      exit(1)
    ilp = float(r.ipercent)/100.0
    
    if fio == 0:
      ilt = 'PROGRESSIVE'
    elif ilp>0.5:
      ilt = 'FILM'
    else:
      ilt = 'INTERLACE'
    
    if not r(r'\bPLAYBACK *(?P<playback>\d+)',dgip[3]): # ALSO 'CODED' FRAMES
      critical('No PLAYBACK in ' + dgifile)
      exit(1)
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
    critical('Unrecognize index file ' + dgifile)
    exit(1)
  
  cfg.set('type', 'video')
#  cfg.set('file', dgip[1].splitlines()[0])
  cfg.set('dgi_file', dgifile)
  cfg.set('interlace_type', ilt)
  cfg.set('interlace_type_fraction', ilp)
  cfg.set('field_operation', fio)
  cfg.set('frame_rate_ratio', str(frf))
  
  cfg.set('crop', 'auto' if cl==cr==ct==cb==0 else '0,0,0,0')
#  cfg.set('aspect_ratio',str(arf))
  cfg.set('picture_size', "{:d}x{:d}".format(psx,psy))
  
  cfg.set('sample_aspect_ratio',str(sarf))
  mbs = int(math.ceil((psx-cl-cr)/16.0))*int(math.ceil((psy-ct-cb)/16.0))
  cfg.set('macroblocks',mbs)
  cfg.set('avc_profile','high')
  if mbs<=1620: # 480p@30fps; 576p@25fps
    cfg.set('avc_level',3.0)
    cfg.set('x264_rate_factor',16.0)
  elif mbs<=3600: # 720p@30fps
    cfg.set('avc_level',3.1)
    cfg.set('x264_rate_factor',18.0)
  elif mbs<=8192: # 1080p@30fps
    cfg.set('avc_level',4.0)
    cfg.set('x264_rate_factor',19.0)
  elif mbs<=22080: # 1080p@72fps; 1920p@30fps
    cfg.set('avc_level',5.0)
    cfg.set('x264_rate_factor',20.0)
  else: # 1080p@120fps; 2048@30fps
    cfg.set('avc_level',5.1)
    cfg.set('x264_rate_factor',21.0)
  if frames!=0:
    cfg.set('frames', frames)
  cfg.sync()
  return True


def config_from_idxfile(cfg,idxfile):
  with open(idxfile, 'rt') as fp: idx=fp.read()
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
      warning('Ignorning in {} uninterpretable line: {}'.format(idxfile,l))
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
  
  track=0
  
  r=regex.RegEx()
  for l in check_output(['mkvmerge','--identify-verbose',mkvfile]).decode(encoding='cp1252').splitlines():
    if r('^\s*$',l):
      continue
    elif r(r'^\s*File\s*(.*):\s*container:\s*(\w*)\s*\[(.*)\]\s*$',l):
      cfg.set('mkvfile',r[0],section='MAIN')
      cfg.set('container',r[1],section='MAIN')
      dets=r[2]
      if r(r'\bduration:(\d+)\b',dets):
        cfg.set('duration',int(r[0])/1000000000.0,section='MAIN')
      
    elif r('^\s*Track ID (\d+): (\w+)\s*\((.*)\)\s*\[(.*)\]\s*$',l):
      track+=1
      cfg.setsection('TRACK{:02d}'.format(track))
      cfg.set('mkvtrack',int(r[0]))
      cfg.set('type',r[1])
      cfg.set('format',r[2])
      dets=r[3]
      if r[2] in ('V_MPEG2','MPEG-1/2'):
        cfg.set('extension','mpg')
        cfg.set('file','{} T{:02d}.mpg'.format(base,track))
        cfg.set('t2c_file','{} T{:02d}.t2c'.format(base,track))
        cfg.set('dgi_file','{} T{:02d}.dgi'.format(base,track))
#        cfg.set('dgi_file','{} T{:02d}.d2v'.format(base,track))
      elif r[2] in ('V_MPEG4/ISO/AVC','MPEG-4p10/AVC/h.264'):
        cfg.set('extension','264')
        cfg.set('file','{} T{:02d}.264'.format(base,track))
        cfg.set('t2c_file','{} T{:02d}.t2c'.format(base,track))
        cfg.set('dgi_file','{} T{:02d}.dgi'.format(base,track))
      elif r[2] in ('V_MS/VFW/FOURCC, WVC1'):
        cfg.set('extension','wvc')
        cfg.set('file','{} T{:02d}.wvc'.format(base,track))
        cfg.set('t2c_file','{} T{:02d}.t2c'.format(base,track))
        cfg.set('dgi_file','{} T{:02d}.dgi'.format(base,track))
      elif r[2] in ('A_AC3','A_EAC3','AC3/EAC3'):
        cfg.set('extension','ac3')
#        cfg.set('extension','eac')
        cfg.set('file','{} T{:02d}.ac3'.format(base,track))
        cfg.set('quality',60)
        cfg.set('delay',0.0)
#        cfg.set('elongation',1.0)
#        cfg.set('normalize',False)
      elif r[2] in ('A_TRUEHD'):
        cfg.set('extension','thd')
        cfg.set('file','{} T{:02d}.thd'.format(base,track))
        cfg.set('quality',60)
        cfg.set('delay',0.0)
#        cfg.set('elongation',1.0)
#        cfg.set('normalize',False)
      elif r[2] in ('A_DTS','DTS','DTS-ES'):
        cfg.set('extension','dts')
        cfg.set('file','{} T{:02d}.dts'.format(base,track))
        cfg.set('quality',60)
        cfg.set('delay',0.0)
#        cfg.set('elongation',1.0)
#        cfg.set('normalize',False)
      elif r[2] in ('A_PCM/INT/LIT'):
        cfg.set('extension','pcm')
        cfg.set('file','{} T{:02d}.pcm'.format(base,track))
        cfg.set('quality',60)
        cfg.set('delay',0.0)
#        cfg.set('elongation',1.0)
#        cfg.set('normalize',False)
      elif r[2] in ('S_VOBSUB','VobSub'):
        cfg.set('extension','idx')
        cfg.set('file','{} T{:02d}.idx'.format(base,track))
        cfg.set('delay',0.0)
        cfg.set('elongation',1.0)
      elif r[2] in ('S_HDMV/PGS','HDMV PGS','PGS'):
        cfg.set('extension','sup')
        cfg.set('file','{} T{:02d}.sup'.format(base,track))
        cfg.set('delay',0.0)
        cfg.set('elongation',1.0)
      elif r[2] in ('A_MS/ACM'):
        cfg.set('disable',True)
        pass
      else:
        warning('Unrecognized track type {} in {}'.format(r[2],mkvfile))
        cfg.set('disable',True)
      
      if r(r'\blanguage:(\w+)\b',dets):
        cfg.set('language',iso6392BtoT[r[0]] if r[0] in iso6392BtoT else r[0])
      
      if r(r'\bdisplay_dimensions:(\d+)x(\d+)\b',dets):
        cfg.set('display_width',int(r[0]))
        cfg.set('display_height',int(r[1]))
        
#      if r(r'\bdefault_track:(\d+)\b',dets):
#        cfg.set('defaulttrack',int(r[0])!=0)
      
      if r(r'\bforced_track:(\d+)\b',dets):
        cfg.set('forcedtrack',int(r[0])!=0)
      
      if r(r'\bdefault_duration:(\d+)\b',dets):
        cfg.set('frameduration',int(r[0])/1000000000.0)
      
      if r(r'\btrack_name:(.+?)\b',dets):
        cfg.set('trackname',r[0])
      
      if r(r'\baudio_sampling_frequency:(\d+)\b',dets):
        cfg.set('samplerate',int(r[0]))
      
      if r(r'\baudio_channels:(\d+)\b',dets):
        cfg.set('channels',int(r[0]))
#        if int(r[0])>2: cfg.set('downmix',2)
      
    elif r(r'^Chapters: (\d+) entries$',l):
      cfg.set('chaptercount',int(r[0]),section='MAIN')
    elif r(r'^Tags for track ID (\d+): (\d+) entries$',l):
      pass
    elif r(r'^Attachment ID (\d+): type \'([a-z/]+)\', size (\d+) bytes, file name \'(.*)\' \[uid:(\d+)\]$',l):
      pass
    else:
      warning('Unrecognized mkvmerge identify line {}: {}'.format(mkvfile,l))
  cfg.sync()

  chap_uid=[]
  chap_time=[]
  chap_hidden=[]
  chap_enabled=[]
  chap_name=[]
  chap_lang=[]
  for l in check_output(['mkvextract','chapters',mkvfile]).decode(encoding='cp1252').splitlines():
    if r('^\s*<ChapterUID>(.*)</ChapterUID>\s*$',l):
      chap_uid.append(r[0])
    elif r('^\s*<ChapterTimeStart>(\d+):(\d+):(\d+\.?\d*)</ChapterTimeStart>\s*$',l):
      chap_time.append(str(float(r[0])*3600.0+float(r[1])*60.0+float(r[2])))
    elif r('^\s*<ChapterFlagHidden>(\d+)</ChapterFlagHidden>\s*$',l):
      chap_hidden.append(r[0])
    elif r('^\s*<ChapterFlagEnabled>(\d+)</ChapterFlagEnabled>\s*$',l):
      chap_enabled.append(r[0])
    elif r('^\s*<ChapterString>(.*)</ChapterString>\s*$',l):
      chap_name.append(r[0])
    elif r('^\s*<ChapterLanguage>(\w+)</ChapterLanguage>\s*',l):
      chap_lang.append(iso6392BtoT[r[0]] if r[0] in iso6392BtoT else r[0])

  if chap_uid or chap_time or chap_hidden or chap_enabled or chap_name or chap_lang:
    cfg.setsection('MAIN')
    cfg.set('chapter_delay',0.0)
    cfg.set('chapter_elongation',1.0)
    cfg.set('chapter_uid',';'.join(chap_uid))
    cfg.set('chapter_time',';'.join(chap_time))
    cfg.set('chapter_hidden',';'.join(chap_hidden))
    cfg.set('chapter_enabled',';'.join(chap_enabled))
    cfg.set('chapter_name',';'.join(chap_name))
    cfg.set('chapter_language', ';'.join(chap_lang))
    cfg.sync()
  
  call=[]
  for vt in sorted([t for t in cfg.sections() if t.startswith('TRACK') and not cfg.get('disable',section=t)]):
    cfg.setsection(vt)
    file=cfg.get('file',None)
    mkvtrack=cfg.get('mkvtrack',-1)
    if file and not exists(file) and mkvtrack>=0:
      call.append('{:d}:{}'.format(mkvtrack,file))
  if call: do_call(['mkvextract', 'tracks', mkvfile] + call)
  cfg.sync()
  
  for vt in sorted([t for t in cfg.sections() if t.startswith('TRACK') and not cfg.get('disable',section=t) and cfg.get('type',section=t)=='video']):
    cfg.setsection(vt)
    file=cfg.get('file')
    if make_srt(cfg,track+1,[file]): track+=1
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
  
  for vt in sorted([t for t in cfg.sections() if t.startswith('TRACK') and not cfg.get('disable',section=t) and cfg.get('type',section=t)=='video']):
    cfg.setsection(vt)
    file=cfg.get('file')
    dgifile=cfg.get('dgi_file', None)
    if dgifile:
      if not exists(dgifile):
        time.sleep(1)
        if dgifile.endswith('.dgi'):
          do_call(['DGIndexNV', '-i', cfg.get('file'), '-o', dgifile, '-h', '-e'],dgifile)
        elif dgifile.endswith('.d2v'):
          do_call(['dgindex', '-i', cfg.get('file'), '-o', splitext(dgifile)[0], '-fo', '0', '-ia', '3', '-om', '2', '-hide', '-exit'],dgifile)
        else:
          continue
        time.sleep(1)
        logfile = splitext(dgifile)[0]+'.log'
        if exists(logfile):
          with open(logfile,'rt') as f:
            debug('Log: "' + logfile + '" contains: "' + repr(f.read().strip()) + '"')
          os.remove(logfile)
      config_from_dgifile(cfg,dgifile)

  for vt in sorted([t for t in cfg.sections() if t.startswith('TRACK') and not cfg.get('disable',section=t)]):
    cfg.setsection(vt)
    t2cfile=cfg.get('t2c_file',None)
    if not t2cfile: continue
    with open(t2cfile,'rt') as fp:
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


def update_coverart(cfg):
  cfg.setsection('MAIN')
  if cfg.has('coverart'): return
  
  show=cfg.get('show','')
  season=cfg.get('season',-1)
  base=cfg.get('base','')
  
  if show and season>=0: n='{} S{:d}'.format(show,season)
  elif base: n=base.partition(' ()')[0]
  elif show: n=show
  n=re.escape(n)+r'(\s+P[\d+])?\.(jpg|jpeg|png)'
  
  cfg.set('coverart', ';'.join(regex.reglob(n,args.artdir if args.artdir else os.getcwd())))
  cfg.sync()


def update_description_tvshow(cfg,txt):
  def lfind(l,*ws):
    for w in ws:
      if w in l: return l.index(w)
    return -1
  tl=txt.splitlines()
  h=tl[0].split('\t')
  tl=tl[1:]
  i=lfind(h,"\xe2\x84\x96",'?','No. in series','Total','Series number')
  if i>=0: h[i]='Series Episode'
  sei=lfind(h,'Series Episode')
  
  epi=lfind(h,'#','No.','No. in season','No. in Season','Episode number')
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
  wri=lfind(h,'Written by','Writer')
  dai=lfind(h,'Original Airdate','Original air date','Original airdate','Airdate','Release date','Aired on','Recorded on')
  pci=lfind(h,'Production code','Prod. code','prod. code','Prod.code')
  
  r=regex.RegEx()
  for t in tl:
    if not t: continue
    l=t.split('\t')
    if cfg.has('episode') and not l[epi].strip(string.digits):
      if int(l[epi])!=cfg.get('episode'): continue
    else:
      if l[epi]!='*': continue
#    if l[epi].lstrip(' 0')!=str(cfg.get('episode','*')): continue
    if 0<=tii<len(l) and l[tii] and cfg.hasno('song'):
      cfg.set('song',l[tii].strip('" '))
    if 0<=wri<len(l) and l[wri] and cfg.hasno('writer'):
      cfg.set('writer',re.sub('\s*&\s*','; ',l[wri]))
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
      s=(h[i].strip() if i<len(h) else '')+': '+s
      cmt = cfg.get('comment','')
      if s not in cmt: cfg.set('comment',  (cmt+';' if cmt else '')+ s)
  
  cfg.sync()


def update_description_movie(cfg,txt):
  txt=re.sub(r'(This movie is|Cast|Director|Genres|Availability|Language|Format)(:|\n)\s*',r'\n\1: ',txt)
  r=regex.RegEx(regex=r'^(Rate 5 starsRate 4 starsRate 3 starsRate 2 starsRate 1 starRate not interested(Clear Rating)?|Rate 5 starsRate 4 starsRate 3 starsRate 2 starsRate 1 stars|Not Interested(Clear)?|[0-5]\.[0-9]|Movie Details|\s*)$')
  tl=[l for l in txt.splitlines() if l and not r(text=l)]
  
  if r(r'^(.*?)\s*(\((.*)\))?$',tl[0]):
    tl=tl[1:]
    if cfg.hasno('title'): cfg.set('title',r[0])
    if r[2]:
      alt = 'Alternate Title: ' + r[2]
      cmt = cfg.get('comment','')
      if alt not in cmt: cfg.set('comment',  (cmt+';' if cmt else '')+ alt)
  if r(r'^([12]\d\d\d)\s*(G|PG|PG-13|R|NC-17|UR|NR|TV-14|TV-MA)?\s*(\d+)\s*(minutes|mins)$',tl[0]):
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
      elif r(r'\bWestern\b',g): cfg.set('genre','Westerns')
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
    else:
      description = '  ' + t + description
    
  if cfg.hasno('description') and description:
    cfg.set('description',description[2:])
  cfg.sync()


def update_description(cfg):
  cfg.setsection('MAIN')
  show=cfg.get('show','')
  season=cfg.get('season',-1)
  base=cfg.get('base','')
  if show and season>=0: n='{} S{:d}'.format(show,season)
  elif base: n=base.partition(' ()')[0]
  elif show: n=show
  else:
    critical('Broken Config: '+repr(cfg))
    exit(1)
  n=join(args.descdir if args.descdir else '',str(n)+'.txt')
  if not exists(n): return
  #txt=open(n,'rb').read().decode(errors='replace')
  txt=open(n,'rt').read()
  txt=txt.strip()
  txt=re.sub(r'Add to Google Calendar','',txt)
  txt=re.sub(r' *\[(\d+|[a-z])\] *','',txt)
  txt=re.sub(r' -- ',r'--',txt)
  txt=re.sub(r'%','percent',txt)
  if cfg.get('type')=='tvshow': update_description_tvshow(cfg,txt)
  elif cfg.get('type')=='movie': update_description_movie(cfg,txt)


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
    with open(infile, 'rt') as i, open('temp.srt', 'wt') as o:
      inp=i.read()
      for l in inp.split('\n\n'):
        if not r(r'^(?s)(?P<beg>\s*\d*\s*)(?P<neg1>-?)(?P<hours1>\d+):(?P<mins1>\d+):(?P<secs1>\d+),(?P<msecs1>\d+)(?P<mid> --> )(?P<neg2>-?)(?P<hours2>\d+):(?P<mins2>\d+):(?P<secs2>\d+),(?P<msecs2>\d+)\b(?P<end>.*)$',l):
          if l: warning('Unrecognized line in {}: {}'.format(infile,repr(l)))
          continue
        time1 = (-1 if r.neg1 else 1)*(int(r.hours1)*3600.0+int(r.mins1)*60.0+int(r.secs1)+int(r.msecs1)/1000.0)
        neg1,hours1,mins1,secs1,msecs1=secsToParts(time1*e+d)
        time2 =(-1 if r.neg2 else 1)*(int(r.hours2)*3600.0+int(r.mins2)*60.0+int(r.secs2)+int(r.msecs2)/1000.0)
        neg2,hours2,mins2,secs2,msecs2=secsToParts(time2*e+d)
        if neg1 or neg2: continue
        o.write('{}{:02d}:{:02d}:{:02d},{:03d}{}{:02d}:{:02d}:{:02d},{:03d}{}\n\n'.format(r.beg,hours1,mins1,secs1,msecs1,mid,hours2,mins2,secs2,msecs2,end))
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
    with open(infile, 'rt') as i, open(outfile, 'wt') as o:
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
  outfile = cfg.get('out_file',splitext(basename(infile))[0]+'.m4a')
  cfg.set('out_file',outfile)
  cfg.sync()
  if not readytomake(outfile,infile): return False
  
  r=regex.RegEx()
  call = [ 'eac3to', infile, 'stdout.wav', '-no2ndpass', '-log=nul' ]
  if cfg.get('delay',0.0)!=0.0: call.append('{:+f}ms'.format(cfg.get('delay')*1000.0))
  if cfg.get('elongation',1.0)!=1.0: warning('Audio elongation not implemented')
#    if cfg.get('channels')==7: call.append('-0,1,2,3,5,6,4')
  if cfg.hasno('downmix'):
    call.append('-down6')
  elif cfg.get('downmix')==6:
    call.append('-down6')
  elif cfg.get('downmix')==2:
    call.append('-downDpl')
  else:
    warning('Invalid downmix "{:d}"'.format(cfg.get('downmix')))
#    if cfg.get('normalize',False): call.append('-normalize')
  
  call += [ '|', 'qaac', '--threading', '--ignorelength', '--no-optimize', '--tvbr', str(cfg.get('quality',60)), '--quality', '2', '-', '-o', outfile]
  
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
  outfile = cfg.get('out_file',splitext(basename(infile))[0] +'.out.264' ) # +'.mp4') # +'.m4v')
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
    if r('^\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*$',cfg.get('crop')):
      cl,cr,ct,cb=[int(r[i]) for i in range(4)]
      if r('^\s*(\d+)\s*x\s*(\d+)\s*$',cfg.get('picture_size','')):
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
    with open(avsfile, 'wt') as fp: fp.write(avs)
    debug('Created AVS file: ' + repr(avs))
  
  call = ['avs2pipemod', '-y4mp', avsfile, '|' , 'x264', '--demuxer', 'y4m', '-']
#  call = ['x264', '--demuxer', 'avs', avsfile]
  
  
  call += ['--preset', cfg.get('x264_preset', 'veryslow')]
  call += ['--tune', cfg.get('x264_tune','film')]
  call += ['--crf', cfg.get('x264_rate_factor', 20.0)]
  call += ['--fps', str(fro)]
  sarf=cfg.get('sample_aspect_ratio')
  call += ['--sar', '{:d}:{:d}'.format(sarf.numerator if sarf else 1,sarf.denominator if sarf else 1)]
  if not cfg.get('x264_deterministic',False): call += ['--non-deterministic']
  if not cfg.get('x264_fast_pskip',False): call += ['--no-fast-pskip']
  if not cfg.get('x264_dct_decimate',False): call += ['--no-dct-decimate']
  if cfg.has('avc_profile'): call += ['--profile', cfg.get('avc_profile')]
  if cfg.has('avc_level'): call += ['--level', cfg.get('avc_level')]
  #if cfg.has('t2cfile'): call += ['--timebase', '1000', '--tcfile-in', cfg.get('t2cfile')]
  if cfg.get('deinterlace','none')=='none' and cfg.has('frames'): call += ['--frames', cfg.get('frames')]
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
    file=cfg.get('file')
    outfile=cfg.get('out_file',None)
    if not outfile: return False
  
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
  outfile=outfile.strip().translate(str.maketrans('','',r':"/\:*?<>|'))+'.mp4'
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
  for track in sorted([t for t in cfg.sections() if t.startswith('TRACK') and not cfg.get('disable',section=t)]):
    cfg.setsection(track)
    if cfg.hasno('out_file'): continue
    if cfg.get('type')=='audio' and cfg.has('language') and cfg.has('audio_languages',section='MAIN') and cfg.get('language') not in cfg.get('audio_languages',section='MAIN').split(";"): continue
    of=cfg.get('out_file')
    if cfg.has('duration',section='MAIN') and cfg.has('duration'):
      mdur=cfg.get('duration',section='MAIN')
      dur=cfg.get('duration')
      if abs(mdur-dur)>0.5 and abs(mdur-dur)*200>mdur:
        warning('Duration of "{}" ({:f}s) deviates from track {} duration({:f}s).'.format(base,mdur,of,dur))
    
    call+=['-add',of]
    infiles.append(of)
    if cfg.has('name'): call[-1]+=':name='+cfg.get('name')
    if cfg.has('language'): call[-1]+=':lang='+cfg.get('language')
    if cfg.has('frame_rate_ratio_out'): call[-1] += ':fps=' + str(float(cfg.get('frame_rate_ratio_out')))
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
  if exists(chapterfile):
#    warning('Not adding chapters from config file because "' + chapterfile + '" exists')
    do_call(['mp4chaps', '--import', outfile],outfile)
  elif cfg.has('chapter_time') and cfg.has('chapter_name'):
    delay=cfg.get('chapter_delay',0.0)
    elong=cfg.get('chapter_elongation',1.0)
    c=cfg.get('chapter_time')
    cts=[float(i) for i in c.split(';')] if isinstance(c,str) else [c]
    c=cfg.get('chapter_name')
    cns=[i.strip() for i in c.split(';')] if isinstance(c,str) else [c]
    with open(chapterfile,'wt') as f:
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
  
  do_call(['mp4file', '--optimize', outfile])
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
    update_coverart(cfg)
    update_description(cfg)
    build_result(cfg)
  
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
    parser.add_argument('--move-source',action='store_true', default=False, help='move source files to working directory before extraction')
    parser.add_argument('--delete-source',action='store_true', default=False, help='delete source file after successful extraction')
    inifile='{}.ini'.format(splitext(sys.argv[0])[0])
    if exists(inifile): sys.argv.insert(1,'@'+inifile)
    inifile=prog + '.ini'
    if exists(inifile): sys.argv.insert(1,'@'+inifile)
    inifile='..\\' + prog + '.ini'
    if exists(inifile): sys.argv.insert(1,'@'+inifile)
    args = parser.parse_args()
  
  startlogging(args.logfile,args.loglevel,'7D')
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

