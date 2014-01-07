#!/usr/bin/python
# -*- coding: latin-1 -*-

prog='SortMP4'
version='0.2'
author='Carl Edman (CarlEdman@gmail.com)'

import shutil, re, shlex, os, argparse, logging, subprocess
from os.path import exists, isfile, isdir, getmtime, getsize, join, basename, splitext, abspath, dirname
from logging import debug, info, warn, error, critical

parser = argparse.ArgumentParser(description='Sort mp4s from current directory to target subdirectories',fromfile_prefix_chars='@',prog=prog,epilog='Written by: '+author)
parser.add_argument('-v','--verbose',dest='loglevel',action='store_const', const=logging.INFO)
parser.add_argument('-d','--debug',dest='loglevel',action='store_const', const=logging.DEBUG)
parser.set_defaults(loglevel=logging.WARN)
parser.add_argument('--version', action='version', version='%(prog)s '+version)
parser.add_argument('--target', action='store', default= 'Y:\\')
args = parser.parse_args()
logging.basicConfig(level=args.loglevel,format='%(asctime)s [%(levelname)s]: %(message)s')

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

def myglob(pat,dir='.'):
	return sorted([f if dir=='.' else join(dir,f) for f in os.listdir(dir) if imps(pat,f)],key=(lambda s:re.sub(r'\d+',lambda m: m.group(0).zfill(6),s)))

for f in myglob('^.*\.(mp4|m4r|m4b)$'):
	ifo=subprocess.check_output(['mp4info',f]).decode(errors='ignore')
	if not imps('^(?m)\s*Media Type:\s*(.*)$',ifo):
		warn('No Media Type in {}, skipping.'.format(f))
		continue
	type=img[0].strip()
	if type=='TV Show':
		if not imps('(?m)^\s*TV Show:\s*(.*)$',ifo):
			warn('No tv show "{}" in {}.'.format(f))
			continue
		show=img[0].strip()
		dir = join(join(args.target,'TV Shows'),show)
		if not exists(dir):
			os.mkdir(dir)
		if exists(join(dir,f)):
			warn('{} already in {}, skipping.'.format(f,dir))
			continue
		info("Moving {} to {}".format(f,dir))
		shutil.move(f,dir)
	elif type=='Movie':
		if not imps('(?m)^\s*Genre:\s*(.*)$',ifo):
			warn('No genre in movie {}, skipping.'.format(f))
			continue
		genre=img[0].strip()
		dir=join(join(args.target,'Movies'),genre)
		if not isdir(dir):
			warn('Genre "{}" in {} not recognized, skipping.'.format(genre,f))
			continue
		if imps('^.*\\([0-9]+\\)\s*(.*)$',splitext(f)[0]):
			sub=img[0]
			if sub:
				if sub.startswith('Trailer'):
					dir=join(dir,'Trailers')
					if not exists(dir):
						os.mkdir(dir)
				elif sub and sub!='HD':
					dir=join(dir,'Extras')
					if not exists(dir):
						os.mkdir(dir)
		if exists(join(dir,f)):
			warn('{} already in {}, skipping.'.format(f,dir))
			continue
		info("Moving {} to {}".format(f,dir))
		shutil.move(f,dir)
	elif type=='Audio Book':
		dir=join(args.target,'Books')
		if exists(join(dir,f)):
			warn('{} already in {}, skipping.'.format(f,dir))
			continue
		warn('Target for {} already exists, skipping.'.format(f))
		shutil.move(f,dir)
	elif img[1]=='Ringtone':
		dir=join(join(args.target,'Music'),'Ringtones')
		if exists(join(dir,f)):
			warn('{} already in {}, skipping.'.format(f,dir))
			continue
		info("Moving {} to {}".format(f,dir))
		shutil.move(f,dir)
	else:
		warn('Media Type "{}" in {} not recognized, skipping.'.format(type,f))
		continue
