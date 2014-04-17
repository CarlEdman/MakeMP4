#!/usr/bin/python
# -*- coding: latin-1 -*-
# Version: 2.0

import logging, re, shlex, os, os.path, argparse, sys, subprocess

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

parser = argparse.ArgumentParser(description='Disable commentary (and other multi-language tracks) on all mp4 files in directory (and subdirectories).')
parser.add_argument('--version', action='version', version='%(prog)s 1.0')
parser.add_argument('--debug', action='store_true', default=False, help='output debugging messages')
parser.add_argument('directory', nargs='?', default='.', help='Directory to collect from (default: current)')
args = parser.parse_args()

for root, dirs, files in os.walk(args.directory):
	for file in sorted(files):
		if os.path.splitext(file)[1] not in ['.mp4']: continue
		f=os.path.join(root,file)
		ts=[]
		inp=subprocess.check_output(['mp4track','--list',f])
		for l in inp.split(r'track'):
			if not imps(r'^\[(\d+)\]((.|\s)*)$',l): continue
			if len(ts)!=int(img[0]):
				print >> sys.stderr, 'Track number {:d} inconsistent in {}'.format(int(img[0]),f)
				exit(-1)
			ts.append(dict([(kv.split('=',1)[0].strip(),kv.split('=',1)[1].strip()) for kv in img[1].splitlines()]))
			ts[-1]['index']=img[0]
		ats=0
		for t in ts:
			if t['type']!='audio': continue
			if ats==0:
				print 'Enabling track id {} in {}'.format(t['id'],f)
				subprocess.call(['mp4track',f,'--track-id',t['id'],'--enabled','true'])
			else:
				print 'Disabling track id {} in {}'.format(t['id'],f)
				subprocess.call(['mp4track',f,'--track-id',t['id'],'--enabled','false'])
			ats+=1
