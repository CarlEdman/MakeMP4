#!/usr/bin/python
# Version: 0.1
# Author: Carl Edman (email full name as one word at gmail.com)

prog='mp4plexname'
version='0.1'
author='Carl Edman (CarlEdman@gmail.com)'

import os, re, os.path, argparse, warnings, logging, glob

def plexRename(dir):
  base = os.path.basename(dir)
  pat = re.compile(r'^' + re.escape(base) + r'\s+S(?P<season>\d+)(E(?P<episode>\d+(-\d+)?))?(V(?P<volume>\d+))?\s*(?P<name>.*\.(mkv|mp4|avi))$')

  nr = {}
  nrany = False
  for fn in os.listdir(dir):
    file = os.path.join(dir, fn)
    mat = pat.fullmatch(fn)
    if not(os.path.isfile(file)) or mat is None: continue
    nrany = True
    d = mat.groupdict()
    season = int(d['season'])
    episode = d['episode']
    volume = d['volume']
    name = d['name']
    if season>0 and (episode or volume): continue
    if season>0:
      pre = 'Season {:d} '.format(season)
      if not name.startswith(pre): name = pre + name
    nr[base + ' S0E{:02d} ' + name] = fn

  if not nrany:
     warnings.warn('No appropriate files in {}, skipping.'.format(dir))
     return

  for (nfn, ep) in zip(sorted(nr.keys()),range(1,len(nr)+1)):
    ofile = os.path.join(dir, nr[nfn])
    nfile = os.path.join(dir, nfn.format(ep))
    if ofile==nfile: continue
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
    ig = [d for d in glob.iglob(gd) if os.path.isdir(d)]
    if len(ig)==0:
      warnings.warn('No directories matching {}, skipping.'.format(gd))
      continue
    for d in ig: plexRename(d)
