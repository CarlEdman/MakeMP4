#!/usr/bin/python
# -*- coding: latin-1 -*-
# Version: 2.0
# Author: Carl Edman (email full name as one word at gmail.com)

import shutil, logging, re, shlex, os, codecs, argparse, configparser
from os.path import exists, isfile, getmtime, getsize, join, basename, splitext, abspath, dirname
from os import remove, access, rename
from sys import exit, argv
#from string import strip, digits, translate, upper
from time import sleep
from math import floor, ceil
from datetime import datetime, date, time
from subprocess import call, check_call, CalledProcessError, Popen, PIPE, STDOUT, list2cmdline
from fractions import gcd
from glob import glob
from tempfile import TemporaryFile, NamedTemporaryFile, mkstemp

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

def do_call(s):
	try:
		cs=[[]]
		for a in s:
			if a=='|':
				cs.append([])
			else:
				cs[-1].append(str(a))
		if args.debug: print('Executing: '+' | '.join([list2cmdline(c) for c in cs]))
		ps=[]
		for c in cs:
			ps.append(Popen(c, stdin=ps[-1].stdout if ps else None, stdout=PIPE))
		outstr, errstr = ps[-1].communicate()
	except KeyboardInterrupt:
		raise
	else:
		for p in ps:
			if p.poll()!=0:
				return None
		if outstr and args.debug: print('Output: '+repr(outstr))
		if errstr and args.debug: print('Error: '+repr(errstr))
		if errstr: outstr+=errstr
		return outstr

parser = argparse.ArgumentParser(description='Chop an mkv file into subfiles at timecodes or chapters.')
parser.add_argument('--version', action='version', version='%(prog)s 1.0')
parser.add_argument('-s', '--start', type=int, default=1, help='initial value of index for outfiles (default: %(default)d)')
parser.add_argument('--debug', action='store_true', default=False, help='output debugging messages')
parser.add_argument('infile', type=str, help='mkv file to be chopped up')
parser.add_argument('outfiles', type=str, help='mkv files to be created with decimal {} formatter')
parser.add_argument('split', nargs='+', metavar='timecodeOrChapter', help='splitting points; may be either integer (for timecode from chapter number), +integer (to generate additional cutting points at regular chapter intervals starting at the last chapter given), float (for timecode in seconds), or hh:mm:ss.ms (for timecode in alternate format)')
args = parser.parse_args()

chaps=dict()
for l in do_call(['mkvextract', 'chapters', '--simple', args.infile]).splitlines():
	if imps('^CHAPTER(\d+)=(\d+):(\d+):(\d+\.?\d*)$',l):
		chaps[int(img[0])]=3600*float(img[1])+60*float(img[2])+float(img[3])

splits=[]
chap=None
for s in args.split:
	if imps('^(\d+)$',s):
		chap=int(img[0])
		if chap not in chaps:
			print('Chapter {:d} not in "{:}"'.format(chap,args.infile))
			exit(-1)
		splits.append(chaps[chap])
	elif imps('^\+(\d+)$',s):
		i=int(img[0])
		if not chap:
			print('No previous chapter for increment +{:d} not in "{:}"'.format(i,args.infile))
		chap+=i
		while chap in chaps:
			splits.append(chaps[chap])
			chap+=i
	elif imps('^(\d+\.\d*$',s):
		splits.append(float(img[0]))
	elif imps('^(\d):(\d+\.?\d*$',s):
		splits.append(60*float(img[0])+float(img[1]))
	elif imps('^(\d):(\d):(\d+\.?\d*$',s):
		splits.append(3600*float(img[0])+60*float(img[1])+float(img[2]))
	elif imps('^(\d):(\d+\.\d*)$',s):
		splits.append(float(img[0])*60+float(img[1]))

timecodes=",".join(['{:02d}:{:02d}:{:02d}:{:03d}'.format(int(s/3600),int(s/60)%60,int(s)%60,int(s*1000)%1000) for s in splits])

do_call(['mkvmerge','--split','timecodes:'+timecodes,'-o','Temp-%06d.mkv',args.infile])

for i in xrange(1000000):
	tf='Temp-{:06d}.mkv'.format(i+1)
	if not exists(tf): break
	chaptimes=[]
	chapnames=[]
	for l in do_call(['mkvextract', 'chapters', '--simple', tf]).splitlines():
		if imps('^CHAPTER(\d+)=(\d+):(\d+):(\d+\.?\d*)$',l):
			chaptimes.append(3600*float(img[1])+60*float(img[2])+float(img[3]))
		elif imps('^CHAPTER(\d+)NAME=(.*)$',l):
			chapnames.append(img[1])
	chapchange=False
	
	if len(chaptimes)>=2 and chaptimes[1]-chaptimes[0]<1.0:
		chaptimes[1]=chaptimes[0]
		chaptimes=chaptimes[1:]
		chapnames=chapnames[1:]
		chapchange=True

	if i<len(splits) and chaptimes[-1]>(splits[i]-(splits[i-1] if i>0 else 0.0))-1.0:
		chaptimes=chaptimes[:-1]
		chapnames=chapnames[:-1]
		chapchange=True

	chapfile=tf+'.chap.txt'
	with open(chapfile,'w') as cf:
		for no,cn,ct in zip(xrange(100),chapnames,chaptimes):
			cf.write('CHAPTER{:02d}={:02d}:{:02d}:{:02d}.{:03d}\n'.format(no,int(ct/3600),int(ct/60)%60,int(ct)%60,int(ct*1000)%1000))
			cf.write('CHAPTER{:02d}NAME={}\n'.format(no,cn))
	
	do_call(['mkvmerge','--output', args.outfiles.format(i+args.start), '--chapters', chapfile, '--no-chapters', tf])
	remove(tf+'.chap.txt')
	remove(tf)
