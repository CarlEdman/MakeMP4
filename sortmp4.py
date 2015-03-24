#!/usr/bin/python
# -*- coding: latin-1 -*-

prog='SortMP4'
version='0.3'
author='Carl Edman (CarlEdman@gmail.com)'

import shutil, os, os.path, argparse, logging, subprocess
from cetools import *
from regex import *

parser = argparse.ArgumentParser(description='Sort mp4s from current directory to target subdirectories',fromfile_prefix_chars='@',prog=prog,epilog='Written by: '+author)
parser.add_argument('-v','--verbose',dest='loglevel',action='store_const', const=logging.INFO)
parser.add_argument('-d','--debug',dest='loglevel',action='store_const', const=logging.DEBUG)
parser.set_defaults(loglevel=logging.WARN)
parser.add_argument('--version', action='version', version='%(prog)s '+version)
parser.add_argument('--target', action='store', default= 'Y:\\')
args = parser.parse_args()
logging.basicConfig(level=args.loglevel,format='%(asctime)s [%(levelname)s]: %(message)s')

def move(f,dir):
  if not os.path.exists(dir):
    os.mkdir(dir)
  if os.path.exists(os.path.join(dir,f)):
    warning('{} already in {}, skipping.'.format(f,dir))
    return
  info("Moving {} to {}".format(f,dir))
  try:
    shutil.move(f,dir)
  except:
    os.remove(os.path.join(dir,f))
    raise

for f in reglob(r'.*\.(mp4|m4r|m4b)'):
  ifo=subprocess.check_output(['mp4info',f]).decode(errors='ignore')
  if not rser(r'^(?m)\s*Media Type:\s*(.*)$',ifo):
    warning('No Media Type in {}, skipping.'.format(f))
    continue
  type=rget(0).strip()
  if not rser(r'^(?m)\s*Genre:\s*(.*)$',ifo):
    warning('No Genre in {}, skipping.'.format(f))
    continue
  genre=rget(0).strip()
  if not rser(r'^(?m)\s*(Short|Long) Description:\s*(.*)$',ifo):
    warning('No Description in {}, skipping.'.format(f))
    continue
  if not rser(r'^(?m)\s*Cover Art pieces:\s*(.*)$',ifo):
    warning('No Cover Art in {}, skipping.'.format(f))
    continue
  
  if type=='TV Show':
    if not rser(r'(?m)^\s*TV Show:\s*(.*)$',ifo):
      warning('No tv show "{}" in {}.'.format(f))
      continue
    move(f,os.path.join(args.target,'TV',alphabetize(rget(0))))
  elif type=='Movie':
    dir=os.path.join(args.target,'Movies',genre)
    if not os.path.isdir(dir):
      warning('Genre "{}" in {} not recognized, skipping.'.format(genre,f))
      continue
    if rser(r'^.*\(\d+\)\s*(.*)\.\w+$',f):
      sub=rget(0)
      if sub=="" or sub.startswith('pt. '):
        pass
      elif sub.startswith('Trailer'):
        dir=os.path.join(dir,'Trailers')
      else:
        dir=os.path.join(dir,'Extras')
    move(f,dir)
  elif type=='Audio Book':
    move(f,os.path.join(args.target,'Books'))
  elif type=='Ringtone':
    dir=os.path.join(args.target,'Music','Ringtones')
    move(f,dir)
  else:
    warning('Media Type "{}" in {} not recognized, skipping.'.format(type,f))
    continue
