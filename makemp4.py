#!/usr/bin/python
# A Python frontend to various audio/video tools to automatically convert them to MP4/H264/AAC-LC and tag them
# -*- coding: latin-1 -*-

prog='MakeMP4'
version='3.2'
author='Carl Edman (CarlEdman@gmail.com)'

import shutil, re, shlex, os, codecs, argparse, configparser, logging, subprocess
from os.path import exists, isfile, getmtime, getsize, join, basename, splitext, abspath, dirname
from os import remove, access, rename, listdir
from sys import exit, argv
from string import digits
from time import sleep, strftime
from math import floor, ceil
from fractions import Fraction
from datetime import datetime, date, time
from tempfile import TemporaryFile, NamedTemporaryFile, mkstemp
from logging import debug, info, warn, error, critical

langNameToISO6392T = { 'English':'eng', 'Français': 'fra', 'Japanese':'jpn', 'Español':'esp' , 'German':'deu', 'Deutsch':'deu', 'Svenska':'swe', 'Latin':'lat', 'Dutch':'nld', 'Chinese':'zho' }
langNameToISO6392T = { 'English':'eng', 'Français': 'fra', 'Japanese':'jpn', 'Español':'esp' , 'German':'deu', 'Deutsch':'deu', 'Svenska':'swe', 'Latin':'lat', 'Dutch':'nld', 'Chinese':'zho' }

iso6392BtoT = { 'alb':'sqi', 'arm':'hye', 'baq':'eus', 'bur':'mya', 'chi':'zho', 'cze':'ces', 'dut':'nld', 'fre':'fra', 'geo':'kat', 'ger':'deu', 'gre':'ell', 'ice':'isl', 'mac':'mkd', 'mao':'mri', 'may':'msa', 'per':'fas', 'rum':'ron', 'slo':'slk', 'tib':'bod', 'wel':'cym' }

def nice(niceness):
	'''Nice for Windows Processes.  Nice is a value between -3-2 where 0 is normal priority.'''
	
	if os.name != 'nt': return
	
	import win32api,win32process,win32con
	
	priorityclasses = [win32process.IDLE_PRIORITY_CLASS,
			win32process.BELOW_NORMAL_PRIORITY_CLASS,
			win32process.NORMAL_PRIORITY_CLASS,
			win32process.ABOVE_NORMAL_PRIORITY_CLASS,
			win32process.HIGH_PRIORITY_CLASS,
			win32process.REALTIME_PRIORITY_CLASS]
	pid = win32api.GetCurrentProcessId()
	handle = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, True, pid)
	if niceness<-3: win32process.SetPriorityClass(handle, priorityclasses[5])
	elif niceness>2: win32process.SetPriorityClass(handle, priorityclasses[0])
	else: win32process.SetPriorityClass(handle, priorityclasses[2-niceness])

def readytomake(file,*comps):
	for f in comps:
		if not f: continue
		if not exists(f) or not isfile(f) or getsize(f)==0: return False
		fd=os.open(f,os.O_RDONLY|os.O_EXCL)
		if fd<0:
			return False
		os.close(fd)
	if not exists(file): return True
	if getsize(file)==0:
		return False
#	fd=os.open(file,os.O_WRONLY|os.O_EXCL)
#	if fd<0: return False
#	os.close(fd)
	for f in comps:
		if f and getmtime(f)>getmtime(file):
			os.remove(file)
			return True
	return False

def myglob(pat,dir='.'):
	return sorted([f if dir=='.' else join(dir,f) for f in listdir(dir) if imps(pat,f)],key=(lambda s:re.sub(r'\d+',lambda m: m.group(0).zfill(6),s)))

class MakeMP4Config(configparser.RawConfigParser):
	"""A subclass of configparser for MakeMP4 Configuration Files"""
	
	def __init__(self,filename):
		configparser.RawConfigParser.__init__(self,allow_no_value=True)
		self.filename=filename
		self.currentsection=None
		self.modified=False
		
		self.sync()
	
	def sync(self):
		if not exists(self.filename):
			with open(self.filename, 'w') as fp: self.write(fp)
		elif self.modified:
			if self.mtime<getmtime(self.filename):
				warn('Overwriting external edits in "{}"'.format(self.filename))
			with open(self.filename, 'w') as fp: self.write(fp)
		elif not hasattr(self,'mtime') or self.mtime<getmtime(self.filename):
			with open(self.filename, 'r') as fp: self.readfp(fp)
		self.mtime=getmtime(self.filename)
		self.modified=False

	def setsection(self,sect):
		if sect and not self.has_section(sect):
			self.add_section(sect)
			self.modified=True
		self.currentsection=sect
	
	def getsection(self):
		return self.currentsection

	@staticmethod
	def valtostr(v):
#		if isinstance(v,list): return ';'.join([self.valtostr(i) for i in v])
		if isinstance(v,bool): return "Yes" if v else "No"
		if isinstance(v,int): return str(v)
		if isinstance(v,float): return str(v)
		if isinstance(v,Fraction): return str(v.denominator)+'/'+str(v.numerator)
		if isinstance(v,str): return v.strip()
		return repr(v)
	
	@staticmethod
	def strtoval(s):
		if s.lower() in ['yes', 'true', 'on']: return True
		if s.lower() in ['no', 'false', 'off']: return False
		if s[0]=='"' and s[-1]=='"': return s.strip('"')
#		if s.find(';')>=0: return [self.strtoval(i) for i in s.split(';')]
		if s.lstrip('-').strip('0123456789')=='': return int(s)
		if s.lstrip('-').strip('0123456789')=='.': return float(s)
		if s.lstrip('-').strip('0123456789')=='/': return Fraction(s)
		if s.lstrip('-').strip('0123456789')==':': return Fraction(int(s[:s.index(':')]),int(s[s.index(':')+1:]))
		return s
	
	def set(self,option,value=None,section=None):
		if not section:
			if not self.currentsection: raise configparser.NoSectionError('No Current Section Set')
			section=self.currentsection
		
		oval=configparser.RawConfigParser.get(self,section,option) if self.has_option(section,option) else None
		nval=self.valtostr(value)
		if oval and oval==nval: return
		configparser.RawConfigParser.set(self,section,option,nval)
		self.modified=True
	
	def append(self,option,aval,section=None):
		if not section:
			if not self.currentsection: raise configparser.NoSectionError('No Current Section Set')
			section=self.currentsection
		
		oval=configparser.RawConfigParser.get(self,section,option) if self.has_option(section,option) else ''
#		nval=(oval+';' if oval else '') + re.sub(r';',r'\;',self.valtostr(aval))
		nval=(oval+';' if oval else '') + self.valtostr(aval)
		configparser.RawConfigParser.set(self,section,option,nval)
		self.modified=True
	
	def get(self,option,default=None,section=None):
		if not section:
			if not self.currentsection: raise configparser.NoSectionError('No Current Section Set')
			section=self.currentsection
		if not self.has_option(section,option) or configparser.RawConfigParser.get(self,section,option)=='': return default
		return self.strtoval(configparser.RawConfigParser.get(self,section,option))
	
	def has(self,option,section=None):
		if not section:
			if not self.currentsection: raise configparser.NoSectionError('No Current Section Set')
			section=self.currentsection
		return self.has_option(section,option) and configparser.RawConfigParser.get(self,section,option)
	
	def hasno(self,option,section=None):
		return not self.has(option,section)
	
	def equals(self,option,value,section=None):
		return self.get(option,None,section=section)==value
	
	def items(self,section=None):
		if not section:
			if not self.currentsection: raise configparser.NoSectionError('No Current Section Set')
			section=self.currentsection
		return configparser.RawConfigParser.items(self,section)

def secsToParts(s):
	if s<0:
		neg="-"
		s=-s
	else:
		neg=""
	secs, msecs= divmod(s,1)
	mins, secs = divmod(secs,60)
	hours, mins = divmod(mins,60)
	return (neg,int(hours),int(mins),int(secs),int(floor(msecs*1000)))

im=None
img=None
def imps(p,s):
	global im
	global img
	im=re.search(p,s)
	if im:
		img=im.groups()
		return True
	else:
		img=None
		return False

def lfind(l,*ws):
	for w in ws:
		if w in l: return l.index(w)
	return -1

def cookout(s):
	s=re.sub(r'[ \r*]*\n[\r* ]*',r'\n',s)
	s=re.sub(r'[^\n]*\r',r'',s)
	s=re.sub(r'\n+',r'\n',s)
	s=re.sub(r'\n \*(.*?) \*',r'\n\1',s)
	return s.strip()
	
def do_call(args,outfile=None,infile=None):
	from subprocess import call, check_call, CalledProcessError, Popen, PIPE, STDOUT, list2cmdline
	try:
		cs=[[]]
		for a in args:
			if a=='|':
				cs.append([])
			else:
				cs[-1].append(str(a))
		#os.system('TITLE ' + ' | '.join([list2cmdline(c) for c in cs]))
		debug('Executing: '+' | '.join([list2cmdline(c) for c in cs]))
		
		ps=[]
		for c in cs:
			ps.append(Popen(c, stdin=ps[-1].stdout if ps else infile, stdout=PIPE, stderr=PIPE))
		outstr, errstrl = ps[-1].communicate()
		outstr=outstr.decode(encoding='cp1252')
		errstrl=errstrl.decode(encoding='cp1252')
	except KeyboardInterrupt:
		if outfile and exists(outfile): remove(outfile)
		raise
	else:
		errstr=""
		for p in ps:
			e = "" if p.stderr.closed else p.stderr.read().decode(encoding='cp1252')
			if p.poll()!=0:
				error('Fatal Error:'+repr(e))
				if outfile: open(outfile,'w').truncate(0)
				return None
			errstr+=e
		errstr+=errstrl
		outstr=cookout(outstr)
		errstr=cookout(errstr)
		if outstr: debug('Output: '+repr(outstr))
		if errstr: debug('Error: '+repr(errstr))
		return outstr+errstr

def make_srt(cfg,track,files):
	return True
	base=cfg.get('base',section='MAIN')
	srtfile='{} T{:02d}.srt'.format(base,track)
	if not exists(srtfile): do_call(['ccextractorwin'] + files + ['-o', srtfile],srtfile)
	if exists(srtfile) and getsize(srtfile)==0: remove(srtfile)
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
	if imps(r'^(.*?) (pt\. (\d+) *)?\((\d*)\) *(.*?)$',base):
		cfg.set('type','movie')
		cfg.set('show',img[0])
		if img[2]: cfg.set('episode',int(img[2]))
		cfg.set('year',img[3])
		cfg.set('song',img[4])
	elif imps(r'^(.*?) (Se\.\s*(\d+)\s*)?Ep\.\s*(\d+)$',base):
		cfg.set('type','tvshow')
		cfg.set('show',img[0])
		if img[2] and img[2]!='0': cfg.set('season',int(img[2]))
		cfg.set('episode',int(img[3]))
	elif imps(r'^(.*) Se\. (\d+) *(.*?)$',base):
		cfg.set('type','tvshow')
		cfg.set('show',img[0])
		cfg.set('season',int(img[1]))
		cfg.set('song',img[2])
	elif imps(r'^(.*) (V|Vol\. )(\d+)$',base):
		cfg.set('type','tvshow')
		cfg.set('show',img[0])
		cfg.set('episode',int(img[2]))
	elif imps(r'^(.*) S(\d+)D\d+$',base):
		cfg.set('type','tvshow')
		cfg.set('show',img[0])
		cfg.set('season',int(img[1]))
		cfg.set('episode','')
	cfg.sync()

def config_from_d2vfile(cfg,d2vfile):
	with open(d2vfile, 'rb') as fp: d2v=fp.read().decode(encoding='cp1252')
	d2vp=d2v.split('\r\n\r\n')
	if len(d2vp)!=4: return False
	if not imps(r'^DGIndexProjectFile16',d2vp[0]): return False
	if not imps(r'^FINISHED\s+([0-9.]+)%\s+(.*?)\s*$',d2vp[3]): return False
	ilp=img[0]
	ilt=img[1]
	if not imps(r'\bAspect_Ratio=(\d+):(\d+)',d2vp[1]): return False
	arf=Fraction(int(img[0]),int(img[1]))
	if not imps(r'\bClipping=\ *(\d+) *, *(\d+) *, *(\d+) *, *(\d+)',d2vp[1]): return False
	cl,cr,ct,cb=[int(img[i]) for i in range(4)]
	if not imps(r'\bPicture_Size= *(\d+)x(\d+)',d2vp[1]): return False
	psx,psy=[int(img[i]) for i in range(2)]
	sarf=arf/Fraction(psx,psy)
	if not imps(r'\bField_Operation= *(\d+)',d2vp[1]): return False
	fio=img[0]
	if not imps(r'\bFrame_Rate= *(\d+) *\((\d+)/(\d+)\)',d2vp[1]): return False
	frm=float(img[0])/1000.0
	frf=Fraction(int(img[1]),int(img[2]))
	
	cfg.set('type', 'video')
#	cfg.set('file', d2vp[0].splitlines()[2])
	cfg.set('d2v_file', d2vfile)
	cfg.set('interlace_type', ilt)
	cfg.set('interlace_percent', ilp)
	cfg.set('aspect_ratio',str(arf))
	if cl==cr==ct==cb==0:
		cfg.set('crop', 'auto')
	else:
		cfg.set('crop', '0,0,0,0')
	cfg.set('picture_size', "{:d}x{:d}".format(psx,psy))
	cfg.set('field_operation', fio)
	cfg.set('frame_rate_ratio', str(frf))
	cfg.set('sample_aspect_ratio',str(sarf))
	mbs = int(ceil((psx-cl-cr)/16.0))*int(ceil((psy-ct-cb)/16.0))
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
		cfg.set('x264_rate_factor',20.0)
	elif mbs<=22080: # 1080p@72fps; 1920p@30fps
		cfg.set('avc_level',5.0)
		cfg.set('x264_rate_factor',22.0)
	else: # 1080p@120fps; 2048@30fps
		cfg.set('avc_level',5.1)
		cfg.set('x264_rate_factor',22.0)
	
	frames=0
	for l in d2vp[2].splitlines():
		if imps(r'^([0-9a-f]+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(?P<flags>([0-9a-f]+ +)*[0-9a-f]+)\s*$',l):
			frames += len(img[7].split())
	cfg.set('frames', frames)
	cfg.sync()
	return True

def config_from_dgifile(cfg,dgifile):
	with open(dgifile, 'rb') as fp: dgi=fp.read().decode(encoding='cp1252')
	dgip=dgi.split('\r\n\r\n')
	if len(dgip)!=4: return False
	if not imps(r'^(DGAVCIndexFileNV14|DGMPGIndexFileNV14|DGVC1IndexFileNV14)',dgip[0]): return False
	if not imps(r'\bCLIP\ *(\d+) *(\d+) *(\d+) *(\d+)',dgip[2]): return False
	cl,cr,ct,cb=[int(img[i]) for i in range(4)]
	if not imps(r'\bSIZ *(\d+) *x *(\d+)',dgip[3]): return False
	psx,psy=[int(img[i]) for i in range(2)]
	sarf=Fraction(1,1)
	if not imps(r'\bORDER *(\d+)',dgip[3]): return False
	fio=img[0]
	if not imps(r'\bFPS *(\d+) */ *(\d+) *',dgip[3]): return False
	frf=Fraction(int(img[0]),int(img[1]))
	if not imps(r'\b(\d*\.\d*)% *FILM',dgip[3]): return False
	ilp = float(img[0])
	
	cfg.set('type', 'video')
#	cfg.set('file', dgip[1].splitlines()[0])
	cfg.set('dgi_file', dgifile)
	cfg.set('interlace_type', 'PROGRESSIVE')
#	if ilp>50.0:
#		cfg.set('interlace_type', 'FILM')
#		cfg.set('interlace_percent', ilp)
#	else:
#		cfg.set('interlace_type', 'VIDEO')
#		cfg.set('interlace_percent', 100.0-ilp)
#	if cl==cr==ct==cb==0:
	cfg.set('crop', 'auto')
#	else:
#		cfg.set('crop', '0,0,0,0')
	cfg.set('picture_size', "{:d}x{:d}".format(psx,psy))
	cfg.set('field_operation', fio)
	cfg.set('frame_rate_ratio', str(frf))
	cfg.set('sample_aspect_ratio',str(sarf))
	mbs = int(ceil((psx-cl-cr)/16.0))*int(ceil((psy-ct-cb)/16.0))
	cfg.set('macroblocks',mbs)
	cfg.set('avc_profile','high')
	if mbs<=1620: # 480p@30fps; 576p@25fps
		cfg.set('avc_level',3.0)
		cfg.set('x264_rate_factor',16.0)
	elif mbs<=3600: # 720p@30fps
		cfg.set('avc_level',3.1)
		cfg.set('x264_rate_factor',18.0)
	elif mbs<=8192: # 1080p@30fps
		cfg.set('avc_level',4.1)
		cfg.set('x264_rate_factor',20.0)
	elif mbs<=22080: # 1080p@72fps; 1920p@30fps
		cfg.set('avc_level',5.0)
		cfg.set('x264_rate_factor',22.0)
	else: # 1080p@120fps; 2048@30fps
		cfg.set('avc_level',5.1)
		cfg.set('x264_rate_factor',22.0)
	
	cfg.sync()
	return True

def config_from_idxfile(cfg,idxfile):
	with open(d2vfile, 'rb') as fp: idx=fp.read()
	timestamp=[]
	filepos=[]
	for l in idx.splitlines():
		if imps(r'^\s*#',l):
			continue
		if imps(r'^\s*$',l):
			continue
		elif imps(r'^\s*timestamp:\s*(\d+):(\d+):(\d+):(\d+):(\d+),\s*filepos:\s*0*([0-9a-fA-F]+?)\s*$',l):
			timestamp.append(str(float(img[0])*3600+float(img[1])*60+float(img[2])+float(img[3])/1000.0))
			filepos.append(img[4])
		elif imps(r'^\s*id\s*:\s*(\w+?)\s*, index:\s*(\d+)\s*$',l):
			cfg.set('language',img[0]) # Convert to 3 character codes
			cfg.set('langindex',img[1])
		elif imps(r'^\s*(\w+)\s*:\s*(.*?)\s*$',l):
			cfg.set(img[0],img[1])
		else:
			warn('Ignorning in {} uninterpretable line: {}'.format(idxfile,l))
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
		if exists(mpgfile) and getsize(mpgfile)>0: remove(tivofile)

def prepare_mpg(mpgfile):
	base, ext=splitext(basename(mpgfile))
	cfgfile=base+'.cfg'
	if not readytomake(cfgfile,mpgfile): return False
	cfg=MakeMP4Config(cfgfile)
	config_from_base(cfg,base)
	
	track=1
	d2vfile='{} T{:02d}.d2v'.format(base,track)
	if not exists(d2vfile):
		do_call(['dgindex', '-i', mpgfile, '-fo', '0', '-ia', '3', '-om', '2', '-exit'],base+'.d2v')
		rename(base+'.d2v',d2vfile)
	if not exists(d2vfile): return
	cfg.setsection('TRACK{:02d}'.format(track))
	cfg.set('file',mpgfile)
	cfg.set('d2v_file',d2vfile)
	cfg.sync()
	config_from_d2vfile(cfg,d2vfile)

	for file in myglob(r'^' + re.escape(base) +r'\s+T[0-9a-fA-F][0-9a-fA-F]\s+(.*)\.(ac3|dts|mpa|mp2|wav|pcm)$'):
		if not imps('^'+re.escape(base)+r'\s+T[0-9a-fA-F][0-9a-fA-F]\s+(.*)\.(ac3|dts|mpa|mp2|wav|pcm)$',file): continue
		feat=img[0]
		ext=img[1]
		track+=1
		cfg.setsection('TRACK{:02d}'.format(track))
		nf='{} T{:02d}.{}'.format(base,track,ext)
		rename(file,nf)
		cfg.set('file',nf)
		cfg.set('type','audio')
		cfg.set('extension',ext)
		cfg.set('quality',55)
		cfg.set('delay',0.0)
#		cfg.set('elongation',1.0)
#		cfg.set('normalize',False)
		cfg.set('features',feat)
		if imps(r'\bDELAY (-?\d+)ms\b',feat): cfg.set('delay',float(img[0])/1000.0)
		if imps(r'([_0-9]+)ch\b',feat):
			cfg.set('channels',img[0])
#			if img[0]=="3_2": cfg.set('downmix',2)
		if imps(r'\b([\d.]+)(K|Kbps|bps)\b',feat):
			bps=int(img[0])
			if img[1][0]=="K": bps=bps*1000
			cfg.set('bit_rate',bps)
		if imps(r'\b([0-9]+)bit\b',feat): cfg.set('bit_depth',img[0])
		if imps(r'\b([0-9]+)rate\b',feat): cfg.set('sample_rate',img[0])
		if imps(r'\b([a-z]{3})-lang\b',feat):  cfg.set('language',img[0])
		cfg.sync()
	
	if make_srt(cfg,track+1,[mpgfile]): track+=1

def prepare_mkv(mkvfile):
	base=splitext(basename(mkvfile))[0]
	cfgfile=base+'.cfg'
	if not readytomake(cfgfile,mkvfile): return False
	cfg=MakeMP4Config(cfgfile)
	config_from_base(cfg,base)
	
	track=0
	for l in subprocess.check_output(['mkvmerge','--identify-verbose',mkvfile]).decode(encoding='cp1252').splitlines():
		if imps('^\s*$',l):
			continue
		elif imps(r'^\s*File\s*(.*):\s*container:\s*(\w*)\s*\[(.*)\]\s*$',l):
			cfg.set('mkvfile',img[0],section='MAIN')
			cfg.set('container',img[1],section='MAIN')
			dets=img[2]
			if imps(r'\bduration:(\d+)\b',dets):
				cfg.set('duration',int(img[0])/1000000000.0,section='MAIN')
			
		elif imps('^\s*Track ID (\d+): (\w+)\s*\(([A-Z0-9_/, ]*)\)\s*\[(.*)\]\s*$',l):
			track+=1
			cfg.setsection('TRACK{:02d}'.format(track))
			cfg.set('mkvtrack',int(img[0]))
			cfg.set('type',img[1])
			cfg.set('format',img[2])
			dets=img[3]
			if img[2]=='V_MPEG2':
				cfg.set('extension','mpg')
				cfg.set('file','{} T{:02d}.mpg'.format(base,track))
				cfg.set('t2c_file','{} T{:02d}.t2c'.format(base,track))
				cfg.set('d2v_file','{} T{:02d}.d2v'.format(base,track))
			elif img[2]=='V_MPEG4/ISO/AVC':
				cfg.set('extension','264')
				cfg.set('file','{} T{:02d}.264'.format(base,track))
				cfg.set('t2c_file','{} T{:02d}.t2c'.format(base,track))
				cfg.set('dgi_file','{} T{:02d}.dgi'.format(base,track))
			elif img[2]=='V_MS/VFW/FOURCC, WVC1':
				cfg.set('extension','avi')
				cfg.set('file','{} T{:02d}.avi'.format(base,track))
				cfg.set('t2c_file','{} T{:02d}.t2c'.format(base,track))
				cfg.set('dgi_file','{} T{:02d}.dgi'.format(base,track))
			elif img[2]=='A_AC3':
				cfg.set('extension','ac3')
				cfg.set('file','{} T{:02d}.ac3'.format(base,track))
				cfg.set('quality',60)
				cfg.set('delay',0.0)
#				cfg.set('elongation',1.0)
#				cfg.set('normalize',False)
			elif img[2]=='A_EAC3':
				cfg.set('extension','eac')
				cfg.set('file','{} T{:02d}.eac'.format(base,track))
				cfg.set('quality',60)
				cfg.set('delay',0.0)
#				cfg.set('elongation',1.0)
#				cfg.set('normalize',False)
			elif img[2]=='A_TRUEHD':
				cfg.set('extension','thd')
				cfg.set('file','{} T{:02d}.thd'.format(base,track))
				cfg.set('quality',60)
				cfg.set('delay',0.0)
#				cfg.set('elongation',1.0)
#				cfg.set('normalize',False)
			elif img[2]=='A_DTS':
				cfg.set('extension','dts')
				cfg.set('file','{} T{:02d}.dts'.format(base,track))
				cfg.set('quality',60)
				cfg.set('delay',0.0)
#				cfg.set('elongation',1.0)
#				cfg.set('normalize',False)
			elif img[2]=='A_PCM/INT/LIT':
				cfg.set('extension','pcm')
				cfg.set('file','{} T{:02d}.pcm'.format(base,track))
				cfg.set('quality',60)
				cfg.set('delay',0.0)
#				cfg.set('elongation',1.0)
#				cfg.set('normalize',False)
			elif img[2]=='S_VOBSUB':
				cfg.set('extension','idx')
				cfg.set('file','{} T{:02d}.idx'.format(base,track))
				cfg.set('delay',0.0)
				cfg.set('elongation',1.0)
			elif img[2]=='S_HDMV/PGS':
				cfg.set('extension','sup')
				cfg.set('file','{} T{:02d}.sup'.format(base,track))
				cfg.set('delay',0.0)
				cfg.set('elongation',1.0)
			elif img[2]=='A_MS/ACM':
				cfg.set('disable',True)
				pass
			else:
				warn('Unrecognized track type {} in {}'.format(img[2],mkvfile))
				cfg.set('disable',True)
			
			if imps(r'\blanguage:(\w+)\b',dets):
				cfg.set('language',iso6392BtoT[img[0]] if img[0] in iso6392BtoT else img[0])
			
			if imps(r'\bdisplay_dimensions:(\d+)x(\d+)\b',dets):
				cfg.set('display_width',int(img[0]))
				cfg.set('display_height',int(img[1]))
				
#			if imps(r'\bdefault_track:(\d+)\b',dets):
#				cfg.set('defaulttrack',int(img[0])!=0)
			
			if imps(r'\bforced_track:(\d+)\b',dets):
				cfg.set('forcedtrack',int(img[0])!=0)
			
			if imps(r'\bdefault_duration:(\d+)\b',dets):
				cfg.set('frameduration',int(img[0])/1000000000.0)
			
			if imps(r'\btrack_name:(.+?)\b',dets):
				cfg.set('trackname',img[0])
			
			if imps(r'\baudio_sampling_frequency:(\d+)\b',dets):
				cfg.set('samplerate',int(img[0]))
			
			if imps(r'\baudio_channels:(\d+)\b',dets):
				cfg.set('channels',int(img[0]))
#				if int(img[0])>2: cfg.set('downmix',2)
			
		elif imps(r'^Chapters: (\d+) entries$',l):
			cfg.set('chaptercount',int(img[0]),section='MAIN')
		else:
			warn('Unrecognized mkvmerge identify line {}: {}'.format(mkvfile,l))
	cfg.sync()

	cfg.setsection('MAIN')
	cfg.set('chapter_delay',0.0)
	cfg.set('chapter_elongation',1.0)
	for l in subprocess.check_output(['mkvextract','chapters',mkvfile]).decode(encoding='cp1252').splitlines():
		if imps('^\s*<ChapterUID>(.*)</ChapterUID>\s*$',l):
			cfg.append('chapter_uid',img[0])
		elif imps('^\s*<ChapterTimeStart>(\d+):(\d+):(\d+\.?\d*)</ChapterTimeStart>\s*$',l):
			cfg.append('chapter_time',float(img[0])*3600.0+float(img[1])*60.0+float(img[2]))
		elif imps('^\s*<ChapterFlagHidden>(\d+)</ChapterFlagHidden>\s*$',l):
			cfg.append('chapter_hidden',int(img[0]))
		elif imps('^\s*<ChapterFlagEnabled>(\d+)</ChapterFlagEnabled>\s*$',l):
			cfg.append('chapter_enabled',int(img[0]))
		elif imps('^\s*<ChapterString>(.*)</ChapterString>\s*$',l):
			cfg.append('chapter_name',img[0])
		elif imps('^\s*<ChapterLanguage>(\w+)</ChapterLanguage>\s*',l):
			cfg.append('chapter_language', iso6392BtoT[img[0]] if img[0] in iso6392BtoT else img[0])

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
	
	for vt in sorted([t for t in cfg.sections() if t.startswith('TRACK') and not cfg.get('disable',section=t) and cfg.equals('type','video',section=t)]):
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
	
	for vt in sorted([t for t in cfg.sections() if t.startswith('TRACK') and not cfg.get('disable',section=t) and cfg.equals('type','video',section=t)]):
		cfg.setsection(vt)
		file=cfg.get('file')
		d2vfile=cfg.get('d2v_file', None)
		if d2vfile:
			if not exists(d2vfile):
				do_call(['dgindex', '-i', cfg.get('file'), '-o', splitext(d2vfile)[0], '-fo', '0', '-ia', '3', '-om', '2', '-hide', '-exit'],d2vfile)
			config_from_d2vfile(cfg,d2vfile)
		dgifile=cfg.get('dgi_file', None)
		if dgifile:
			if not exists(dgifile):
				do_call(['DGIndexNV', '-i', cfg.get('file'), '-o', dgifile, '-h', '-e'],dgifile)
				config_from_dgifile(cfg,dgifile)
		

	for vt in sorted([t for t in cfg.sections() if t.startswith('TRACK') and not cfg.get('disable',section=t)]):
		cfg.setsection(vt)
		t2cfile=cfg.get('t2c_file',None)
		if not t2cfile: continue
		with open(t2cfile,'r') as fp:
			t2cl=list(filter(lambda s:imps(r'^\s*\d*\.?\d*\s*$',s),fp.readlines()))
		frames=len(t2cl)+1 # FIX WHEN timecode file is fixed.
		oframes=cfg.get('frames',-1)
		if oframes>0 and oframes!=frames:
			warn('Timecodes changed frames in "{}" from {:d} to {:d}'.format(file,oframes,frames))
			cfg.set('frames',frames)
		duration=(2*float(t2cl[-1])-float(t2cl[-2]))/1000.0  # FIX WHEN timecode file is fixed.
		oduration=cfg.get('duration',-1.0)
		if oduration>0 and oduration!=duration:
			warn('Encoding changed duration in "{}" from {:f} to {:f}'.format(file,oduration,duration))
			cfg.set('duration',duration)
		cfg.sync()
	
	for vt in sorted([t for t in cfg.sections() if t.startswith('TRACK') and not cfg.get('disable',section=t) and cfg.equals('type','subtitles',section=t)]):
		cfg.setsection(vt)
		file=cfg.get('file')
		ext=cfg.get('extension')
		if ext=='.sub':
			config_from_idxfile(cfg,splitext(file)[0]+'.idx')
			# remove idx file
	
	cfg.sync()

def prepare_vob(vobfile):
	base=splitext(basename(vobfile))[0]
	if imps(r'^(.*)_(\d+)$',base):
		if int(img[1])!=1: return
		base=img[0]
	cfgfile=base+'.cfg'
	if not readytomake(cfgfile,vobfile): return
	cfg=MakeMP4Config(cfgfile)
	config_from_base(cfg,base)
	
	#TODO
	#dgindex & rename
	
	#vob -> idx, sub
	#basefile=myjoin(root, file[:-6])
	#idxfile=basefile+".idx"
	#avsfile=basefile+".video.avs"
	#if exists(idxfile): continue
	#ifofile=basefile+"_0.ifo"
	#if exists(ifofile) and getsize(ifofile)>0:
	#	pgc=1
	#	trueifofile=ifofile
	#elif ifofile[-13:-8] == "_PGC_" and exists(ifofile[:-13]+"_0.ifo"):
	#	pgc=int(ifofile[-8:-6])
	#	trueifofile=ifofile[:-13]+"_0.ifo"
	#else:
	#	continue
	#
	#vobsubfile=r'C:\Windows\Temp\vobsub'
	#info('Generating "%(vobfile)s" -> "%(idxfile)s"' % locals())
	#open(vobsubfile,'w').write('%(ifofile)s\n%(basefile)s\n%(pgc)d\n0\nALL\nCLOSE\n' % locals())
	#if trueifofile!=ifofile: copyfile(trueifofile,ifofile)
	#do_call([r'C:\Windows\SysWOW64\rundll32.exe','vobsub.dll,Configure',vobsubfile],vobsubfile)
	#if trueifofile!=ifofile: remove(ifofile)
	##if not exists(idxfile): open(idxfile,'w').truncate(0)

	#if make_srt(cfg,track+1,vobfiles): track+=1
	
	#chapter txt -> cfg
	cfg.sync()

def update_coverart(cfgfile):
	cfg=MakeMP4Config(cfgfile)
	if not cfg: return False
	cfg.setsection('MAIN')
	if cfg.has('coverart'): return
	base=cfg.get('base','')
	show=str(cfg.get('show',''))
	season=cfg.get('season',-1)
	
	cfg.setsection('MAIN')
	
	for p in myglob('^.*\.(jpg|jpeg|png)$',args.artdir if args.artdir else '.'):
		b=splitext(basename(p))[0]
		if imps(r'^(.*)\s+P[\d+]',b):
			b=img[0]
		if b in [base, show, '{} Se. {:d}'.format(show,season)]:
			cfg.append('coverart',p)
	cfg.sync()

def update_description_tvshow(cfg,txt):
	tl=txt.splitlines()
	h=tl[0].split('\t')
	tl=tl[1:]
	i=lfind(h,"\xe2\x84\x96",'?','No. in series','Total','Series number')
	if i>=0: h[i]='Series Episode'
	sei=lfind(h,'Series Episode')
	
	epi=lfind(h,'#','No. in series','Episode number')
	if epi<0: return False # Fix
	tii=lfind(h,'Title','Episode title')
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
	dai=lfind(h,'Original Airdate','Original air date','Original airdate','Airdate','Release date')
	pci=lfind(h,'Production code','Prod. code','prod. code','Prod.code')
	
	for t in tl:
		if not t: continue
		l=t.split('\t')
		if l[epi]!=str(cfg.get('episode','*')): continue
		if 0<=tii<len(l) and l[tii] and cfg.hasno('song'):
			cfg.set('song',l[tii].strip('" '))
		if 0<=wri<len(l) and l[wri] and cfg.hasno('writer'):
			cfg.set('writer',re.sub('\s*&\s*','; ',l[wri]))
		if 0<=pci<len(l) and l[pci] and cfg.hasno('episodeid'):
			cfg.set('episodeid',l[pci].strip())
		if 0<=dai<len(l) and imps(r'\b([12]\d\d\d)\b',l[dai]) and cfg.hasno('year'):
			cfg.set('year',int(img[0]))
		if 0<=dei<len(l) and l[dei] and cfg.hasno('description'):
			cfg.set('description',l[dei])
		for i in range(len(l)):
			if i in [epi,tii,wri,pci,dei]: continue
			s=l[i].strip()
			if not s: continue
			s=(h[i].strip() if i<len(h) else '')+': '+s
			if s not in cfg.get('comment',''): cfg.append('comment', s)

def update_description_movie(cfg,txt):
	txt=re.sub(r'(This movie is:|Cast:|Director:|Genres:|Availability:|Language:|Format:)\s*',r'\n\1 ',txt)
	tl=[t.strip() for t in txt.splitlines() if t.strip()]
	if len(tl)>0 and imps(r'^(.*?)\s*(\((.*)\))?$',tl[0]):
		cfg.set('show',img[0])
		if img[2]:
			alt = 'Alternate Title: ' + img[2]
			if alt not in cfg.get('comment',''): cfg.append('comment', alt)
	if len(tl)>1 and imps(r'^([12]\d\d\d)\s*(G|PG|PG-13|R|NC-17|UR|NR|TV-14)?\s*(\d+)\s*minutes$',tl[1]):
		cfg.set('year',img[0])
		if img[1] not in cfg.get('comment',''): cfg.append('comment', 'Rating: ' + img[1])
	description= tl[2] if len(tl)>2 else ''
	for t in tl[3:]:
		if not imps(r'^(.*?):\s*(.+?)\s*$',t): continue
		atr=img[0]
		val=img[1]
		if atr=='Genres' and cfg.hasno('genre'):
			if imps('\b'+'Musicals'+'\b',val): cfg.set('genre','Musical')
			elif imps('\b'+'Animes'+'\b',val): cfg.set('genre','Anime')
			elif imps('\b'+'Operas'+'\b',val): cfg.set('genre','Opera')
			elif imps('\b'+'Fantasy'+'\b',val): cfg.set('genre','Fantasy')
			elif imps('\b'+'Horror'+'\b',val): cfg.set('genre','Horror')
			elif imps('\b'+'Documentaries'+'\b',val): cfg.set('genre','Documentary')
			elif imps('\b'+'Superhero'+'\b',val): cfg.set('genre','Superhero')
			elif imps('\b'+'Western'+'\b',val): cfg.set('genre','Westerns')
			elif imps('\b'+'Classics'+'\b',val): cfg.set('genre','Classics')
			elif imps('\b'+'Sci-Fi & Fantasy'+'\b',val): cfg.set('genre','Science Fiction')
			elif imps('\b'+'Comedies'+'\b',val): cfg.set('genre','Comedy')
			elif imps('\b'+'Crime'+'\b',val): cfg.set('genre','Crime')
			elif imps('\b'+'Thrillers'+'\b',val): cfg.set('genre','Thriller')
			elif imps('\b'+'Romantic'+'\b',val): cfg.set('genre','Romance')
			elif imps('\b'+'Animation'+'\b',val): cfg.set('genre','Animation')
			elif imps('\b'+'Cartoons'+'\b',val): cfg.set('genre','Animation')
			elif imps('\b'+'Period Pieces'+'\b',val): cfg.set('genre','History')
			elif imps('\b'+'Action'+'\b',val): cfg.set('genre','Action')
			elif imps('\b'+'Adventure'+'\b',val): cfg.set('genre','Adventure')
			elif imps('\b'+'Dramas'+'\b',val): cfg.set('genre','Drama')
			else: cfg.set('genre',val)
		elif atr=='Director':
			description += '  '+t+'.'
		elif atr=='Writer' and cfg.hasno('writer'):
			cfg.set('writer',val)
		elif atr=='Cast':
			description += '  '+t+'.'
		else:
			if t not in cfg.get('comment',''): cfg.append('comment', t)
	if cfg.hasno('description') and description:
		cfg.set('description',description)

def update_description(cfgfile):
	cfg=MakeMP4Config(cfgfile)
	cfg.setsection('MAIN')
	if cfg.has('show') and cfg.has('season'): n='{} Se. {:d}'.format(cfg.get('show'),cfg.get('season'))
	elif cfg.has('show'): n=cfg.get('show')
	elif cfg.has('base'): n=cfg.get('base')
	n=join(args.descdir if args.descdir else '',str(n)+'.txt')
	if not exists(n): return
	txt=open(n,'r').read()
	if txt.startswith("\xef\xbb\xbf"): txt=txt[3:]
	txt=txt.strip()
	txt=re.sub(r' *\[(\d+|[a-z])\] *','',txt)
	txt=re.sub(r' -- ',r'--',txt)
	if cfg.equals('type','tvshow'): update_description_tvshow(cfg,txt)
	elif cfg.equals('type','movie'): update_description_movie(cfg,txt)
	cfg.sync()

def build_subtitles(cfgfile):
	cfg=MakeMP4Config(cfgfile)
	for track in sorted([t for t in cfg.sections() if t.startswith('TRACK') and not cfg.get('disable',section=t) and cfg.equals('type','subtitles',section=t)]):
		cfg.setsection(track)
		infile = cfg.get('file')
		inext = cfg.get('extension')
		d=cfg.get('delay',0.0)
		e=cfg.get('elongation',1.0)
		if inext=='srt':
			outfile = splitext(infile)[0]+'.ttxt'
			cfg.set('out_file', outfile)
			if exists(outfile): continue
			with open(infile, 'r') as i, open('temp.srt', 'w') as o:
				inp=i.read()
				if inp.startswith("\xef\xbb\xbf"): inp = inp[3:]
				for l in inp.split('\n\n'):
					if not imps(r'^(?s)(\s*\d*\s*)(-?)(\d+):(\d+):(\d+),(\d+)( --> )(-?)(\d+):(\d+):(\d+),(\d+)\b(.*)$',l):
						if l: warn('Unrecognized line in {}: {}'.format(infile,repr(l)))
						continue
					beg,oneg1,ohours1,omins1,osecs1,omsecs1,mid,oneg2,ohours2,omins2,osecs2,omsecs2,end = img
					otime1 = (-1 if oneg1 else 1)*(int(ohours1)*3600.0+int(omins1)*60.0+int(osecs1)+int(omsecs1)/1000.0)
					nneg1,nhours1,nmins1,nsecs1,nmsecs1=secsToParts(otime1*e+d)
					otime2 =(-1 if oneg2 else 1)*(int(ohours2)*3600.0+int(omins2)*60.0+int(osecs2)+int(omsecs2)/1000.0)
					nneg2,nhours2,nmins2,nsecs2,nmsecs2=secsToParts(otime2*e+d)
					if nneg1 or nneg2: continue
					o.write(beg+'{:02d}:{:02d}:{:02d},{:03d}'.format(nhours1,nmins1,nsecs1,nmsecs1)+mid+'{:02d}:{:02d}:{:02d},{:03d}'.format(nhours2,nmins2,nsecs2,nmsecs2)+end+'\n\n')
			do_call(['mp4box','-ttxt','temp.srt'],outfile)
			rename('temp.ttxt',outfile)
			remove('temp.srt')
		elif inext=='sup':
			outfile = splitext(infile)[0]+'.idx'
			cfg.set('out_file', outfile)
			if exists(outfile): continue
			call = ['bdsup2sub++']
			call += ['--resolution','keep']
			if d!=0: call += ['--delay',str(d*1000.0)]
			fps = cfg.get('frame_rate_ratio',section='TRACK01')
			if fps == Fraction(30000,1001):
				call += [ '--fps-target', '30p' ]
			elif fps == Fraction(24000,1001):
				call += [ '--fps-target', '24p' ]
			elif fps == Fraction(25000,1000) or fps == 25 or fps == 25.0:
				call += [ '--fps-target', '25p' ]
			call += ['--output',outfile,infile]
			do_call(call,outfile) # '--fix-invisible',
			if not exists(outfile):
				cfg.set('disable',True)
				continue
		elif (d!=0.0 or e!=1.0) and inext=='idx':
			outfile = splitext(infile)[0]+'.adj'+splitext(infile)[1]
			cfg.set('out_file', outfile)
			if not exists(splitext(infile)[0]+'.adj.sub'):
				shutil.copy(splitext(infile)[0]+'.sub',splitext(infile)[0]+'.adj.sub')
			if exists(outfile): continue
			with open(infile, 'r') as i, open(outfile, 'w') as o:
				for l in i:
					if not imps(r'^(?s)(\s*timestamp:\s*)(-?)(\d+):(\d+):(\d+):(\d+)\b(.*)$',l):
						o.write(l)
						continue
					beg, oneg, ohours, omins, osecs, omsecs, end = img
					otime = (-1 if oneg else 1)*(int(ohours)*3600.0+int(omins)*60.0+int(osecs)+int(omsecs)/1000.0)
					nneg,nhours,nmins,nsecs,nmsecs=secsToParts(otime*e+d)
					if nneg: continue
					o.write(beg+'{:02d}:{:02d}:{:02d}:{:03d}'.format(nhours,nmins,nsecs,nmsecs)+end)
		elif (d!=0.0 or e!=1.0):
			outfile = infile
			cfg.set('out_file', outfile)
			warn('Delay and elongation not implemented for subtitles type "{}"'.format(infile))
		else:
			outfile = infile
			cfg.set('out_file', outfile)
	cfg.sync()

def build_audios(cfgfile):
	cfg=MakeMP4Config(cfgfile)
	for track in sorted([t for t in cfg.sections() if t.startswith('TRACK') and not cfg.get('disable',section=t) and cfg.equals('type','audio',section=t)]):
		cfg.setsection(track)
		infile = cfg.get('file')
		inext = cfg.get('extension')
		outfile = cfg.get('out_file',splitext(basename(infile))[0]+'.m4a')
		cfg.set('out_file',outfile)
		cfg.sync()
		if not readytomake(outfile,infile): continue
		
		call = [ 'eac3to', infile, 'stdout.wav', '-no2ndpass', '-log=nul' ]
		if cfg.get('delay',0.0)!=0.0: call.append('{:+f}ms'.format(cfg.get('delay')*1000.0))
		if cfg.get('elongation',1.0)!=1.0: warn('Audio elongation not implemented')
#		if cfg.equals(channels,7): call.append('-0,1,2,3,5,6,4')
		if cfg.hasno('downmix'):
			call.append('-down6')
		elif cfg.get('downmix')==6:
			call.append('-down6')
		elif cfg.get('downmix')==2:
			call.append('-downDpl')
		else:
			warn('Invalid downmix "{:d}"'.format(cfg.get('downmix')))
#		if cfg.get('normalize',False): call.append('-normalize')
		
		call += [ '|', 'qaac', '--ignorelength', '--no-optimize', '--tvbr', str(cfg.get('quality',60)), '--quality', '2', '-', '-o', outfile]
		
		res=do_call(call, outfile)
		if res and imps(r'\bwrote (\d+\.?\d*) seconds\b',res):
			cfg.set('duration',float(img[0]))
		if cfg.has('duration') and cfg.has('duration',section='MAIN') and abs(cfg.get('duration')-cfg.get('duration',section='MAIN'))>0.5:
			warn('Audio track "{}" duration differs (elongation={:f})'.format(infile,cfg.get('duration')/cfg.get('duration',section='MAIN')))
		cfg.sync()

def build_videos(cfgfile):
	cfg=MakeMP4Config(cfgfile)
	for track in sorted([t for t in cfg.sections() if t.startswith('TRACK') and not cfg.get('disable',section=t) and cfg.equals('type','video',section=t)]):
		cfg.setsection(track)
		infile = cfg.get('file')
		inext = cfg.get('extension')
		d2vfile = cfg.get('d2v_file', None)
		dgifile = cfg.get('dgi_file', None)
		outfile = cfg.get('out_file',splitext(basename(infile))[0] +'.mp4') # +'.m4v')
		cfg.set('out_file',outfile)
		cfg.sync()
		if not readytomake(outfile,infile,d2vfile,dgifile): continue
		
		avs=''
		procs=cfg.get('processors',6)
		if procs!=1: avs += 'SetMTMode(5,{:d})\n'.format(procs)
		avs += 'SetMemoryMax(1024)\n'
		if d2vfile:
			avs+='DGDecode_mpeg2source("{}", info=3, idct=4, cpu=3)\n'.format(abspath(d2vfile))
			avs+='ColorMatrix(hints = true,interlaced=true)\n'.format(abspath(d2vfile))
		elif dgifile:
			avs+='DGSource("{}", deinterlace=1, use_pf = true)\n'.format(abspath(dgifile))
			avs+='ColorMatrix(hints = true, interlaced=false)\n'
		else:
			warn('No video index file from "{}"'.format(cfg.get('file')))
			return
		
		if cfg.hasno('unblock') or cfg.get('unblock',None)==False:
			pass
		elif cfg.get('unblock',None)==True and cfg.has('x264_tune'):
			if cfg.get('x264_tune',None)=='animation':
				avs += 'unblock(cartoon=true)'
			else:
				avs += 'unblock(photo=true)'
		elif cfg.get('unblock',None)=='normal':
			avs += 'unblock()'
		elif cfg.get('unblock',None)=='cartoon':
			avs += 'unblock(cartoon=true)'
		elif cfg.get('unblock',None)=='photo':
			avs += 'unblock(photo=true)'
		
		avs+='KillAudio()\n'
		
		d2vfo=cfg.get('field_operation')
		lt=cfg.get('interlace_type','PROGRESSIVE')
		lp=cfg.get('interlace_percent',100.0)
		fr=cfg.get('frame_rate_ratio',Fraction(30000,1001))
		
		doublerate=False
		
		if lt == 'PROGRESSIVE':
			pass
		elif lt == 'VIDEO':
#			avs+='TomsMoComp(1,5,1)\n'
#			avs+='LeakKernelDeint()\n'
#			avs+='TDeint(mode=2, type={:d}, tryWeave=True, full=False)\n'.format(3 if cfg.get('x264_tune','animation' if cfg.get('genre',section='MAIN') in ['Anime', 'Animation'] else 'film')=='animation' else 2)
			avs+='Bob()\n'
			doublerate=True
		elif d2vfo != 1 and lt == 'FILM':
			fr*=Fraction(4,5)
			avs+='tfm().tdecimate(hybrid=1)\n'
#			avs+='tfm().tdecimate(hybrid=1,d2v="{}")\n'.format(abspath(d2vfile))
#			avs+='Telecide(post={:d},guide=0,blend=True)'.format(0 if lp>0.99 else 2)
#			avs+='Decimate(mode={:d},cycle=5)'.format(0 if lp>0.99 else 3)
		
		if cfg.has('crop'):
			if imps('^\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*$',cfg.get('crop')):
				cl,cr,ct,cb=[int(img[i]) for i in range(4)]
				if imps('^\s*(\d+)\s*x\s*(\d+)\s*$',cfg.get('picture_size','')):
					px, py=[int(img[i]) for i in range(2)]
				else: # DELETE
					px=cfg.get('picture_size_x',0) # DELETE
					py=cfg.get('picture_size_y',0) # DELETE
				if (px-cl-cr) % 2!=0: cr+=1
				if (py-ct-cb) % 2!=0: cb+=1
				if cl or cr or ct or cb:
					avs+='crop({:d},{:d},{:d},{:d},align=true)\n'.format(cl,ct,-cr,-cb)
			elif cfg.equals('crop','auto'):
				avs+='autocrop(threshold=30,wMultOf=2, hMultOf=2,samples=11, mode=0)\n'
		
		blocksize=16 if cfg.get('macroblocks',0)>1620 else 8
		if procs!=1: avs+='SetMTMode(2)\n'
		
		degrain=cfg.get('degrain',3)
		if degrain>=1 or doublerate:
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
		if doublerate: avs+='MFlowFps(super, bv1, fv1, num={:d}, den={:d}, ml=100)\n'.format(fr.numerator,fr.denominator)
		if procs!=1: avs+='Distributor()\n'
		
		avsfile=mkstemp(suffix='.avs')
		os.write(avsfile[0],avs.encode())
		os.close(avsfile[0])
		debug('Created AVS file:' + repr(avs))

		call = ['avs2pipemod', '-y4mp', avsfile[1], '|' , 'x264', '--demuxer', 'y4m', '-']
#		call = ['x264', '--demuxer', 'avs', avsfile[1]]

		call += ['--tune', cfg.get('x264_tune','film')]
		call += ['--preset', cfg.get('x264_preset', 'veryslow')]
		call += ['--crf', cfg.get('x264_rate_factor', 20.0)]
		call += ['--fps', str(fr)]
		sarf=cfg.get('sample_aspect_ratio')
		call += ['--sar', '{:d}:{:d}'.format(sarf.numerator if sarf else 1,sarf.denominator if sarf else 1)]
		if not cfg.get('x264_deterministic',False): call += ['--non-deterministic']
		if not cfg.get('x264_fast_pskip',False): call += ['--no-fast-pskip']
		if not cfg.get('x264_dct_decimate',False): call += ['--no-dct-decimate']
		if cfg.has('avc_profile'): call += ['--profile', cfg.get('avc_profile')]
		if cfg.has('avc_level'): call += ['--level', cfg.get('avc_level')]
		#call += ['--timebase', '1/1000', '--tcfile-in', t2cfile]
		call += [ '--output', outfile ]
		res=do_call(call,outfile)
		remove(avsfile[1])
		if res and imps(r'\bencoded (\d+) frames\b',res):
			cfg.sync()
			frames=int(img[0])
			oframes=cfg.get('frames',-1)
			if oframes>=0 and frames!=oframes:
				warn('Encoding changed frames in "{}" from {:d} to {:d}'.format(infile,oframes,frames))
			cfg.set('frames',frames)
			cfg.set('duration',float(int(img[0])/fr))
			if cfg.has('duration') and cfg.has('duration',section='MAIN') and abs(cfg.get('duration')-cfg.get('duration',section='MAIN'))>0.5:
				warn('Video track "{}" duration differs (elongation={:f})'.format(infile,cfg.get('duration')/cfg.get('duration',section='MAIN')))
			cfg.sync()

def build_results(cfgfile):
	cfg=MakeMP4Config(cfgfile)
	
	for track in sorted([t for t in cfg.sections() if t.startswith('TRACK') and not cfg.get('disable',section=t)]):
		cfg.setsection(track)
		file=cfg.get('file')
		outfile=cfg.get('out_file',None)
		if not outfile: return False
	
	cfg.setsection('MAIN')
	base=cfg.get('base')
	
	if cfg.has('show'):
		outfile=str(cfg.get('show'))
		if outfile.startswith('The '): outfile=outfile[4:]
		elif outfile.startswith('A '): outfile=outfile[2:]
		elif outfile.startswith('An '): outfile=outfile[3:]
	else:
		outfile=cfg.get('base')
	
	if cfg.equals('type','movie'):
		if cfg.has('episode'): 	outfile+=' pt. '+str(cfg.get('episode'))
		if cfg.has('year'): outfile+=' ('+str(cfg.get('year'))+')'
		if cfg.has('song'): outfile+=' '+str(cfg.get('song'))
	
	elif cfg.equals('type','tvshow'):
		if cfg.has('season'): outfile+=' Se. '+str(cfg.get('season'))
		if cfg.has('song') and cfg.has('episode'):
			outfile+=' Ep. {:02d} \'{}\''.format(cfg.get('episode'),str(cfg.get('song')))
		elif cfg.has('song'):
			outfile+=' '+str(cfg.get('song'))
		elif cfg.has('episode'):
			outfile+=' Ep. {:02d}'.format(cfg.get('episode'))
		else:
			warn('TV Show file {} has neither episode or title.'.format(outfile))
	else:
		warn('Unrecognized type for "{}"',base)
	
	outfile=outfile.translate(str.maketrans('','',r':"/\:*?<>|'))+'.mp4'
	if args.outdir: outfile=join(args.outdir,outfile)
	
	infiles=[cfgfile]
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
		of=cfg.get('out_file')
		if cfg.has('duration',section='MAIN') and cfg.has('duration'):
			mdur=cfg.get('duration',section='MAIN')
			dur=cfg.get('duration')
			if abs(mdur-dur)>0.5 and abs(mdur-dur)*200>mdur:
				warn('Duration of "{}" ({:f}s) deviates from track {} duration({:f}s)'.format(base,mdur,of,dur))
		
		call+=['-add',of]
		infiles.append(of)
		if cfg.has('name'): call[-1]+=':name='+cfg.get('name')
		if cfg.has('language'): call[-1]+=':lang='+cfg.get('language')
		if cfg.equals('type','audio'):
			ats += 1
			if not cfg.get('defaulttrack',ats==1): call[-1]+=':disable'
#		if cfg.equals('type','video'):
#			vts += 1
#			if not cfg.get('defaulttrack',vts==1): call[-1]+=':disable'
#		if cfg.equals('type','subtitle'):
#			sts += 1
#			if not cfg.get('defaulttrack',sts==1): call[-1]+=':disable'
	
	if not readytomake(outfile,*infiles): return False
	do_call(call,outfile)
	
	cfg.setsection('MAIN')
	call=['-encodedby', prog + ' ' + version + ' on ' + strftime('%A, %B %d, %Y, at %X')]
	if cfg.has('type'): call += [ '-type' , cfg.get('type') ]
	if cfg.has('genre'): call += [ '-genre' , cfg.get('genre') ]
	if cfg.has('year'): call += [ '-year' , cfg.get('year') ]
	if cfg.has('season'): call += [ '-season' , cfg.get('season') ]
	if cfg.has('episode'): call += [ '-episode' , cfg.get('episode') ]
	if cfg.has('episodeid'): call += [ '-episodeid' , cfg.get('episodeid') ]
	if cfg.has('artist'): call += [ '-artist' , cfg.get('artist') ]
	if cfg.has('writer'): call += [ '-writer' , cfg.get('writer') ]
#	if cfg.has('rating'): call += [ '-rating' , cfg.get('rating') ]
	if cfg.has('macroblocks',section='TRACK01'): call += [ '-hdvideo' , '1' if cfg.get('macroblocks',section='TRACK01')>=3600 else '0']
	if cfg.has('show'): call += [ '-show' , str(cfg.get('show'))]
	
	song=None
	if cfg.equals('type','movie'):
		if cfg.has('show') and cfg.has('song'): song = str(cfg.get('show')) + ": " + str(cfg.get('song'))
		elif cfg.has('show'): song = str(cfg.get('show'))
		elif cfg.has('song'): song = str(cfg.get('song'))
	elif cfg.has('song'): song = str(cfg.get('song'))
	if song: call+=['-song', song]
	
	cfg.sync()
	# TODO: Deal with quotes/special characters
	desc=cfg.get('description','')
	if len(desc)>255:
		call += [ '-desc', desc[:255], '-longdesc', desc ]
	elif len(desc)>0:
		call += [ '-desc' , desc ]
	if cfg.has('comment'): call += [ '-comment' , cfg.get('comment') ]
	if call: do_call(['mp4tags'] + call + [outfile],outfile)
	
	if cfg.has('chapter_time'):
		info('Adding chapters to "{}"'.format(outfile))
		chapterfile=splitext(outfile)[0]+'.chapters.txt'
		chapters_made=not(exists(chapterfile))
		delay=cfg.get('chapter_delay',0.0)
		elong=cfg.get('chapter_elongation',1.0)
		if chapters_made:
			cts=cfg.get('chapter_time')
			cts=[float(i) for i in cts.split(';')] if isinstance(cts,str) else [cts]
			cns=cfg.get('chapter_name').split(';')
			with open(chapterfile,'w') as f:
				for (ct,cn) in zip(cts,cns):
					(neg,hours,mins,secs,msecs)=secsToParts(ct*elong+delay)
					f.write('{}{:02d}:{:02d}:{:02d}.{:03d} {} ({:d}m {:d}s)\n'.format(neg,hours,mins,secs,msecs,cn,(-1 if neg else 1)*hours*60+mins,secs))
		do_call(['mp4chaps', '--import', outfile],outfile)
		if chapters_made: remove(chapterfile)
	
	for i in coverfiles:
		info('Adding coverart for "{}": "{}"'.format(outfile, i))
		do_call(['mp4art', '--add', i, outfile], outfile)
	
	do_call(['mp4file', '--optimize', outfile])
	return True

if 'parser' not in globals():
	parser = argparse.ArgumentParser(description='Extract all tracks from .mkv, .mpg, .TiVo, or .vob files; convert video tracks to h264, audio tracks to aac; then recombine all tracks into properly tagged .mp4',fromfile_prefix_chars='@',prog=prog,epilog='Written by: '+author)
	
	parser.add_argument('--version', action='version', version='%(prog)s '+version)
	parser.add_argument('-v','--verbose',dest='loglevel',action='store_const', const=logging.INFO)
	parser.add_argument('-d','--debug',dest='loglevel',action='store_const', const=logging.DEBUG)
	parser.set_defaults(loglevel=logging.WARN)
	parser.add_argument('-n','--nice',dest='niceness',action='store', type=int, default=0)
	parser.add_argument('-l','--log',dest='logfile',action='store')
	parser.add_argument('--mkvdir',dest='mkvdir',action='store',help='directory of .mkv files to be processed')
	parser.add_argument('--tivodir',dest='tivodir',action='store',help='directory of .TiVo and .mpg files to be processed')
	parser.add_argument('--vobdir',dest='vobdir',action='store',help='directory of .vob files to be processed')
	parser.add_argument('--outdir',dest='outdir',action='store',help='directory for finalized .mp4 files')
	parser.add_argument('--tmpdir',dest='tmpdir',action='store',help='directory for temporary files')
	parser.add_argument('--descdir',dest='descdir',action='store',help='directory for .txt files with descriptive data')
	parser.add_argument('--artdir',dest='artdir',action='store',help='directory for .jpg and .png cover art')
	parser.add_argument('--mak',dest='mak',action='store',help='your TiVo MAK key to decrypt .TiVo files to .mpg')
	inifile='{}.ini'.format(splitext(argv[0])[0])
	if exists(inifile): argv.insert(1,'@'+inifile)
	args = parser.parse_args()

logging.basicConfig(level=args.loglevel,filename=args.logfile,format='%(asctime)s [%(levelname)s]: %(message)s')
nice(args.niceness)
progmodtime=getmtime(argv[0])

#cfg = MakeMP4Config("Kung Fu Panda () Animals.cfg")
#cfg.setsection('TRACK01')
#config_from_dgifile(cfg,'Kung Fu Panda () Animals T01.dgi')
#cfg.sync()
#print imps(r'^(.*?) (pt\. (\d+) *)?\((\d*)\) *(.*?)$','Two Towers pt. 2 () HD')
#print img[0]
#print img[2]
#exit()

while True:
	working=False
	if getmtime(argv[0])>progmodtime:
		exec(compile(open(argv[0]).read(), argv[0], 'exec')) # execfile(argv[0])
	
	if args.tivodir:
		for f in myglob('\.TiVo$',args.tivodir):
			prepare_tivo(f)
	
	if args.tivodir:
		for f in myglob('\.mpg$',args.tivodir):
			prepare_mpg(f)
	
	if args.mkvdir:
		for f in myglob('\.mkv$',args.mkvdir):
			prepare_mkv(f)
	
	if args.vobdir:
		for f in myglob('\.vob$',args.vobdir):
			prepare_vob(f)
	
	for f in myglob('\.cfg$'):
		update_coverart(f)
		update_description(f)
		build_results(f)
	
	for f in myglob('\.cfg$'):
		build_subtitles(f)
	
	for f in myglob('\.cfg$'):
		build_audios(f)
	
	for f in myglob('\.cfg$'):
		build_videos(f)
	
	print("Sleeping.")
	sleep(60)
