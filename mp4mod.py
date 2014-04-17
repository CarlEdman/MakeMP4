#!/usr/bin/python
# -*- coding: latin-1 -*-
# Version: 0.1
# Author: Carl Edman (email full name as one word at gmail.com)

prog='MP4mod'
version='0.3'
author='Carl Edman (CarlEdman@gmail.com)'

import re, os, os.path, argparse, subprocess, glob
from cetools import *

tags = {
	'-A':'\s*Album:\s*(.+)', # -album       STR  Set the album title
	'-a':'\s*Artist:\s*(.+)', # -artist      STR  Set the artist information
	'-b':'\s*BPM:\s*(\d+)', # -tempo       NUM  Set the tempo (beats per minute)
	'-c':'\s*Comments:\s*(.+)', # -comment     STR  Set a general comment
	'-C':'\s*Copyright:\s*(.+)', # -copyright   STR  Set the copyright information
	'-d':'\s*Disk:\s*(\d+)\s*of\s*\d+', # -disk        NUM  Set the disk number
	'-D':'\s*Disk:\s*\d+\s*of\s*(\d+)', # -disks       NUM  Set the number of disks
	'-e':'\s*Encoded by:\s*(.+)', # -encodedby   STR  Set the name of the person or company who encoded the file "
	'-E':'\s*Encoded with:\s*(.+)', #, -tool        STR  Set the software used for encoding
	'-g':'\s*Genre:\s*(.+)', # -genre       STR  Set the genre name
	'-G':'\s*Grouping:\s*(.+)', # -grouping    STR  Set the grouping name
	'-H':'\s*HD Video:\s*(yes|no)', # -hdvideo     NUM  Set the HD flag (1\0)
	'-i':'\s*Media Type:\s*(.+)', # -type        STR  Set the Media Type(tvshow, movie, music, ...)
	'-I':'\s*Content ID:\s*(\d+)', # -contentid   NUM  Set the content ID
	'-j':'\s*GenreType:\s*(\d+),\s*.+', # -genreid     NUM  Set the genre ID # : 58, Comedy
	'-l':'\s*Long Description:\s*(.+)', # -longdesc    STR  Set the long description
	'-l':'\s*Description:\s*(.+)', # -longdesc    STR  Set the long description
#	'-L':'Lyrics:\s*(.+)', # -lyrics      NUM  Set the lyrics # multiline
	'-m':'\s*Short Description:\s*(.{1,250}).*', # -description STR  Set the short description
	'-m':'\s*Description:\s*(.{1,250}).*', # -description STR  Set the short 	'-M':'\s*TV Episode:\s*(\d+)', # -episode     NUM  Set the episode number
	'-n':'\s*TV Season:\s*(\d+)', # -season      NUM  Set the season number
	'-N':'\s*TV Network:\s*(.+)', # -network     STR  Set the TV network
	'-o':'\s*TV Episode Number:\s*(.+)', # -episodeid   STR  Set the TV episode ID
	'-O':'\s*Category:\s*(.+)', # -category    STR  Set the category
	'-p':'\s*Playlist ID:\s*(\d+)', # -playlistid  NUM  Set the playlist ID
	'-B':'\s*Podcast:\s*(\d+)', # -podcast     NUM  Set the podcast flag.
	'-R':'\s*Album Artist:\s*(.+)', # -albumartist STR  Set the album artist
	'-s':'\s*Name:\s*(.+)', # -song        STR  Set the song title
	'-S':'\s*TV Show:\s*(.+)', # -show        STR  Set the TV show
	'-t':'\s*Track:\s*(\d+)\s*of\s*\d+', # -track       NUM  Set the track number
	'-T':'\s*Track:\s*\d*\s*of\s*(\d+)', # -tracks      NUM  Set the number of tracks
	'-x':'\s*xid:\s*(.+)', # -xid         STR  Set the globally-unique xid (vendor:scheme:id)
#	'X':'\s*Content Rating:\s*(.+)', # -rating      STR  Set the Rating(none, clean, explicit) # : UNDEFINED(255)
	'-w':'\s*Composer:\s*(.+)', # -writer      STR  Set the composer information
	'-y':'\s*Release Date:\s*(\d+)', # -year        NUM  Set the release date
	'-z':'\s*Artist ID:\s*(\d+)', # -artistid    NUM  Set the artist ID
	'-Z':'\s*Composer ID:\s*(\d+)', # -composerid  NUM  Set the composer ID

# Sort Artist: Reynolds, Alastair
# Sort Composer: Lee, John
# Sort Album
# Sort Name
# Sort Album Artist
# Part of Compilation: (yes|no)
# Part of Gapless Album: (yes|no)
# Keywords:
# iTunes Account: %s
# Purchase Date: %s
# iTunes Store Country: %s
}
media_t2n = { 
	"oldmovie":"Movie",
	"normal":"Normal",
	"audiobook":"Audio Book",
	"musicvideo":"Music Video",
	"movie":"Movie",
	"tvshow":"TV Show",
	"booklet":"Booklet",
	"ringtone":"Ringtone" }
media_n2t = dict_inverse(media_t2n)

def mp4_valid(f):
	valid_exts = ['.mp4','.m4a','.m4b','.m4v']
	if not os.path.exists(f):
		critical('file "' + f + '" does not exist')
	b, e = os.path.splitext(f)
	if e not in valid_exts:
		critical('file "' + f + '" does not have valid mp4 extension (' + ','.join(valid_exts) + ')')
	return (b,e)

def mp4meta_export(f):
	b,e = mp4_valid(f)
	t = b + '.txt'
	if os.path.exists(t):
		if not args.force:
			critical('cannot export metadata from "' + f + '" because "' + t + '" already exists')
		os.remove(t)
	cs = reglob(re.escape(b)+r'(\.cover|)\.art\[\d+\]\.(jpg|png|gif|bmp)')
	if cs:
		if not args.force:
			critical('cannot export metadata from "' + f + '" because "' + '","'.join(cs) + '" already exist(s)')
		for c in cs: os.remove(c)
	subprocess.check_call(['mp4info', f], stdout=open(t, "w"))
	subprocess.check_output(['mp4art', '--extract', f])

def mp4meta_import(f):
	b,e = mp4_valid(f)
	if args.loglevel <= logging.DEBUG: debug('Before import info:\n' + subprocess.check_output(['mp4info', f]).decode(encoding='cp1252'))
	t = b + '.txt'
	if not os.path.exists(t):
		critical('cannot extract metadata from "' + f + '" because "' + t + '" does not exist')
	ts = []
	with open(t,'r') as td:
		for line in td:
			line = line.rstrip()
			if rser(r'^mp4info version',line):
				continue
			if rser(r'^' + re.escape(f) + ':$',line):
				continue
			if rser(r'^Track\s+Type\s+Info\s*$',line):
				continue
			if rser(r'^\d+\s+',line):
				continue
			if rser(r'^\s*$',line):
				continue
			if rser(r'^\s*Cover Art pieces:\s*\d+',line):
				continue
			foundit = False
			for arg, pat in tags.items():
				foundit = True
				if rser(pat, line):
					ts.append(arg)
					if arg[1] in 'i':
						ts.append(media_n2t[rget(0)])
					elif arg[1] in 'HB':
						ts.append('1' if rget(0) == 'yes' else '0')
					else:
						ts.append(rget(0))
			if foundit:
				continue
			warn('Could not interpret "' + line + '" for "' + f + '"')
	
	ak = [ k[1:] for k in tags.keys() if k[0]=='-' ]
	subprocess.check_output(['mp4tags', '--remove', ''.join(ak), f])
	if args.loglevel <= logging.DEBUG: debug('After tags remove info:\n' + subprocess.check_output(['mp4info', f]).decode(encoding='cp1252'))
	if ts:
		subprocess.check_output(['mp4tags'] + ts + [f])
	if not args.nocleanup:
		os.remove(t)
	
	subprocess.call(['mp4art', '--art-any', '--remove', f])
	if args.loglevel <= logging.DEBUG: debug('After art remove info:\n' + subprocess.check_output(['mp4info', f]).decode(encoding='cp1252'))
	cs = reglob(re.escape(b)+r'(\.cover|)\.art\[\d+\]\.(jpg|png|gif|bmp)')
	if cs:
		call  = ['mp4art']
		if not args.nooptimize: call.append('--optimize')
		for c in cs: call += ['--add', c]
		call += [f]
		subprocess.check_output(call)
		if not args.nocleanup:
			for c in cs: os.remove(c)
	else:
		if not args.nooptimize:
			subprocess.check_output(['mp4file', '--optimize', f])
	if args.loglevel <= logging.DEBUG: debug('Final info:\n' + subprocess.check_output(['mp4info', f]).decode(encoding='cp1252'))
	

def mp4meta_swap(f1, f2):
	mp4meta_export(f1)
	mp4meta_export(f2)
	os.rename(f1,'temp')
	os.rename(f2,f1)
	os.rename('temp',f2)
	mp4meta_import(f1)
	mp4meta_import(f2)

if __name__ == '__main__':
	ops = ['export', 'import', 'swap']
	
	parser = argparse.ArgumentParser(description='Import, Export, and Swap MP4Meta Data.')
	parser.add_argument('--version', action='version', version='%(prog)s ' + version)
	parser.add_argument('operation', choices = ops, help='operation to be performed')
	parser.add_argument('files', nargs='+', help='files to be operated on')
	parser.add_argument('-f','--force', dest='force', action='store_true', help='overwrite existing metadata and image files')
	parser.add_argument('-o','--no-optimize', dest='nooptimize', action='store_true', help='optimize mp4 file after operation')
	parser.add_argument('-c','--no-cleanup', dest='nocleanup', action='store_true', help='remove imported tag and image files')
	parser.add_argument('-v','--verbose',dest='loglevel',action='store_const', const=logging.INFO)
	parser.add_argument('-d','--debug',dest='loglevel',action='store_const', const=logging.DEBUG)
	parser.set_defaults(loglevel=logging.WARN)
	parser.add_argument('-l','--log',dest='logfile',action='store')
	args = parser.parse_args()
	logging.basicConfig(level=args.loglevel,filename=args.logfile,format='%(asctime)s [%(levelname)s]: %(message)s')
	if args.operation=='export':
		for g in args.files:
			fs = glob.glob(g)
			if not fs:
				critical('"' + g + '" does not match any files')
			for f in fs:
				mp4meta_export(f)
	elif args.operation=='import':
		for g in args.files:
			fs = glob.glob(g)
			if not fs:
				critical('"' + g + '" does not match any files')
			for f in fs:
				mp4meta_import(f)
	elif args.operation=='swap':
		if len(args.files) != 2:
			critical('swap operation requires exactly two arguments')
		mp4_swap(args.files[0],args.files[1])
	else:
		critical('operation argument must be one of: ' + ', '.join(ops))
