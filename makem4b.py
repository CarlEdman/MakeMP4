#!/usr/bin/python
# Author: Carl Edman (email full name as one word at gmail.com)

prog='MakeM4B'
version='0.2'
author='Carl Edman (CarlEdman@gmail.com)'

import logging, re, os, os.path, argparse, subprocess, math, sys, glob, logging
from cetools import *
from regex import *

parser = argparse.ArgumentParser(description='Convert audio files to m4b audiobook, creating chapters as necessary.')
parser.add_argument('--version', action='version', version='%(prog)s ' + version)
parser.add_argument('--qaacopts', type=str, default='--tvbr 45 --quality 2', help='options to pass along to qaac')
parser.add_argument('outfile', type=str, help='resulting m4b file')
parser.add_argument('infiles', type=str, nargs='+', help='audiofiles to be added')
parser.add_argument('-v','--verbose',dest='loglevel',action='store_const', const=logging.INFO)
parser.add_argument('-d','--debug',dest='loglevel',action='store_const', const=logging.DEBUG)
parser.set_defaults(loglevel=logging.WARN)
parser.add_argument('-l','--log',dest='logfile',action='store')
args = parser.parse_args()
logging.basicConfig(level=args.loglevel,filename=args.logfile,format='%(asctime)s [%(levelname)s]: %(message)s')

outfile = args.outfile
_, oext = os.path.splitext(outfile)
if not oext: outfile += '.m4b'
infiles = [j for i in args.infiles for j in sorted(glob.glob(i))]

qaac = ['qaac','--threading']
qaac += args.qaacopts.split()
qaac += ['--concat', '-o', outfile]
qaac += infiles

print(qaac)

debug(subprocess.check_output(qaac))
