#!/usr/bin/python
# -*- coding: latin-1 -*-
# Version: 0.1
# Author: Carl Edman (email full name as one word at gmail.com)

prog='mp4plexname'
version='0.1'
author='Carl Edman (CarlEdman@gmail.com)'

import os, re, os.path, argparse, warnings, logging, glob

def plexRename(dir):
  if not(os.path.exists(dir)):
    warnings.warn('{} does not exist, skipping.'.format(dir))
    return

  if not(os.path.isdir(dir)):
    warnings.warn('{} is not a directory, skipping.'.format(dir))
    return

  base = os.path.basename(dir)
  pat = re.compile(r'^' + re.escape(base) + r' S(?P<season>\d+)(E(?P<episode>\d+))?(V(?P<volume>\d+))?(\s+(?P<name>.*))?\.(?P<ext>mkv|mp4|avi)$')

  nr = []
  rb = 0
  for fn in os.listdir(dir):
    if fn in ["Thumbs.db"]:
      continue
    file = os.path.join(dir, fn)
    if not(os.path.isfile(file)):
      warnings.warn('{} is not a file, skipping.'.format(fn))
      continue
    mat = pat.fullmatch(fn)
    if mat == None:
      warnings.warn('{} does not match pattern, skipping.'.format(fn))
      continue
    d = mat.groupdict()
    if d['episode'] == None and d['volume'] == None:
      nr.append((fn, d['season'], d['name'], d['ext']))
    elif int(d['season']) == 0:
      rb = max(rb, int(d['episode'])+1)
    else:
      pass

  for ((ofn,oseason,oname,oext),ep) in zip(nr,range(rb, rb+len(nr))):
    pre = 'Season '+str(oseason)+' '
    if not oname.startswith(pre): oname = pre + oname
    nfn = '{} S0E{:02d} {}.{}'.format(base, ep, oname, oext)
    ofile = os.path.join(dir, ofn)
    nfile = os.path.join(dir, nfn)
    if os.path.exists(nfile):
      warnings.warn('{} already exists, skipping.'.format(nfile))
    if args.dryrun:
      print('mv "{}" "{}"'.format(ofile, nfile))
    else:
      os.rename(ofile, nfile)


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Rename TV show extras Plex perferred format.')
  parser.add_argument('--version', action='version', version='%(prog)s ' + version)
  parser.add_argument('--dryrun', dest='dryrun', action='store_true', help='do not perform operations, but only print them.')
  parser.add_argument('dirs', nargs='+', help='directories to be operated on')
  parser.add_argument('-v','--verbose',dest='loglevel',action='store_const', const=logging.INFO)
  parser.add_argument('-d','--debug',dest='loglevel',action='store_const', const=logging.DEBUG)
  parser.add_argument('-l','--log',dest='logfile',action='store')
  parser.set_defaults(loglevel=logging.WARN)
  args = parser.parse_args()
  logging.basicConfig(level=args.loglevel,filename=args.logfile,format='%(asctime)s [%(levelname)s]: %(message)s')

  for gd in args.dirs:
    for d in glob.iglob(gd):
      plexRename(d)
