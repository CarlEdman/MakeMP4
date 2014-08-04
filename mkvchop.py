#!/usr/bin/python
# -*- coding: latin-1 -*-
# Author: Carl Edman (email full name as one word at gmail.com)

prog='MakeM4B'
version='2.3'
author='Carl Edman (CarlEdman@gmail.com)'

import logging, re, os, argparse, subprocess, math, sys
from os.path import exists, isfile, getmtime, getsize, join, basename, splitext, abspath, dirname
from cetools import *
from regex import *

parser = argparse.ArgumentParser(description='Chop an mkv file into subfiles at timecodes or chapters.')
parser.add_argument('--version', action='version', version='%(prog)s '+version)
parser.add_argument('-s', '--start', type=int, default=1, help='initial value of index for outfiles (default: %(default)d)')
parser.add_argument('--debug', action='store_true', default=False, help='output debugging messages')
parser.add_argument('infile', type=str, help='mkv file to be chopped up')
parser.add_argument('outfiles', type=str, help='mkv files to be created with decimal {} formatter')
parser.add_argument('split', nargs='+', metavar='timecodeOrChapter', help='splitting points; may be either integer (for timecode from chapter number), +integer (to generate additional cutting points at regular chapter intervals starting at the last chapter given), float (for timecode in seconds), or hh:mm:ss.ms (for timecode in alternate format)')
args = parser.parse_args()

chaps=dict()
for l in subprocess.check_output(['mkvextract', 'chapters', '--simple', args.infile], universal_newlines = True).splitlines():
	if rser('^CHAPTER(\d+)=(\d+):(\d+):(\d+\.?\d*)$',l):
		chaps[int(rget(0))]=3600*float(rget(1))+60*float(rget(2))+float(rget(3))

splits=[]
chap=None
for s in args.split:
	if rser('^(\d+)$',s):
		chap=int(rget(0))
		if chap not in chaps:
			print('Chapter {:d} not in "{:}"'.format(chap,args.infile))
			sys.exit(-1)
		splits.append(chaps[chap])
	elif rser('^\+(\d+)$',s):
		i=int(rget(0))
		if not chap:
			print('No previous chapter for increment +{:d} not in "{:}"'.format(i,args.infile))
		chap+=i
		while chap in chaps:
			splits.append(chaps[chap])
			chap+=i
	elif rser('^(\d+\.\d*)$',s):
		splits.append(float(rget(0)))
	elif rser('^(\d):(\d+\.?\d*$',s):
		splits.append(60*float(rget(0))+float(rget(1)))
	elif rser('^(\d):(\d):(\d+\.?\d*$',s):
		splits.append(3600*float(rget(0))+60*float(rget(1))+float(rget(2)))
	elif rser('^(\d):(\d+\.\d*)$',s):
		splits.append(float(rget(0))*60+float(rget(1)))

timecodes=",".join(['{:02d}:{:02d}:{:02d}:{:03d}'.format(int(s/3600),int(s/60)%60,int(s)%60,int(s*1000)%1000) for s in splits])

debug(subprocess.check_output(['mkvmerge','--split','timecodes:'+timecodes,'-o','Temp-%06d.mkv',args.infile]))

if splits[0] != 0.0:
	os.remove('Temp-000001.mkv')

for tf,ff in zip(reglob(r'Temp-\d{6}\.mkv'),(args.outfiles.format(i) for i in range(args.start,sys.maxsize))):
	chaptimes=[]
	chapnames=[]
	for l in subprocess.check_output(['mkvextract', 'chapters', '--simple', tf], universal_newlines = True).splitlines():
		if rser('^CHAPTER(\d+)=(\d+):(\d+):(\d+\.?\d*)$',l):
			chaptimes.append(3600*float(rget(1))+60*float(rget(2))+float(rget(3)))
		elif rser('^CHAPTER(\d+)NAME=(.*)$',l):
			chapnames.append(rget(1))
	chapchange=False
	
	if len(chaptimes)>=2 and chaptimes[1]-chaptimes[0]<1.0:
		chaptimes[1]=chaptimes[0]
		chaptimes=chaptimes[1:]
		chapnames=chapnames[1:]
		chapchange=True

	if len(chaptimes)>=3 and chaptimes[-1]-chaptimes[-2]<1.0:
		chaptimes=chaptimes[:-1]
		chapnames=chapnames[:-1]
		chapchange=True

	if chapchange:
		chapfile=tf+'.chap.txt'
		with open(chapfile,'w') as cf:
			for no,cn,ct in zip(range(1000),chapnames,chaptimes):
				cf.write('CHAPTER{:02d}={:02d}:{:02d}:{:02d}.{:03d}\n'.format(no,int(ct/3600),int(ct/60)%60,int(ct)%60,int(ct*1000)%1000))
				cf.write('CHAPTER{:02d}NAME={}\n'.format(no,cn))
		
		debug(subprocess.check_output(['mkvmerge','--output', ff, '--chapters', chapfile, '--no-chapters', tf]))
		os.remove(tf+'.chap.txt')
		os.remove(tf)
	else:
		os.rename(tf,ff)
