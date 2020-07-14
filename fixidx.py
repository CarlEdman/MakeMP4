#!/usr/bin/python

prog='fixidx'
version='0.1'
author='Carl Edman (CarlEdman@gmail.com)'

import re
from sys import exit, argv
from logging import debug, info, warn, error, critical
from math import floor

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

d=0.0
e=1.0

with open('Batman Begins () Batman Mythology T03.idx', 'r') as i:
	ltime=0
	for l in i:
		if not imps(r'^(?s)(\s*timestamp:\s*)(-?)(\d+):(\d+):(\d+):(\d+)\b(.*)$',l):
			print(l)
			continue
		beg, oneg, ohours, omins, osecs, omsecs, end = img
		otime = (-1 if oneg else 1)*(int(ohours)*3600.0+int(omins)*60.0+int(osecs)+int(omsecs)/1000.0)
		nneg,nhours,nmins,nsecs,nmsecs=secsToParts(otime*e+d)
		if nneg: continue
		print(otime-ltime,otime)
		ltime=otime
#		print(beg+'{:02d}:{:02d}:{:02d}:{:03d}'.format(nhours,nmins,nsecs,nmsecs)+end)

