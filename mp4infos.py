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

parser = argparse.ArgumentParser(description='Tabular list of mp4 metadata in directory and all subdirectories.')
parser.add_argument('--version', action='version', version='%(prog)s 2.0')
parser.add_argument('--debug', action='store_true', default=False, help='output debugging messages')
parser.add_argument('directory', nargs='?', default='.', help='Directory to collect from (default: current)')
args = parser.parse_args()

cats=['Filename']
tcats=[]
vals=[]

for root, dirs, files in os.walk(args.directory):
	for file in sorted(files):
		if os.path.splitext(file)[1] not in ['.m4a', '.mp4', '.m4r', '.m4b']: continue
		f=os.path.join(root,file)
		if args.debug: print >>sys.stderr, f
		vals.append(dict({'Filename':f}))
		for l in subprocess.check_output(['mp4info',f]).splitlines():
			if imps(r'^\s+(.+?)\s*:\s*(.+?)\s*$',l):
				if img[0] not in cats: cats.append(img[0])
				vals[-1][img[0]]=img[1]
			if imps(r'^(\d+)\s+(\w+)\s*(.*)$',l):
				type='TrackType'+img[0]
				if type not in tcats: tcats.append(type)
				vals[-1][type]=img[1]
				info='TrackInfo'+img[0]
				if info not in tcats: tcats.append(info)
				vals[-1][info]=img[2]

print '\t'.join(cats + tcats)
for v in vals:
	print '\t'.join([v[c] if c in v else '' for c in (cats+tcats)])
