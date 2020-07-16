#!/usr/bin/python

prog='mp4plexname'
version='0.3'
author='Carl Edman (CarlEdman@gmail.com)'
desc='Rename TV show extras Plex perferred format.'

import os
import re
import os.path
import argparse
import logging
import logging.handlers
import glob

parser = None
args = None
log = logging.getLogger()

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
      pre = f'Season {season:d} '
      if not name.startswith(pre): name = pre + name
    nr[base + ' S0E{:02d} ' + name] = fn

  if not nrany:
     log.warning(f'No appropriate files in {dir}, skipping.')
     return

  for (nfn, ep) in zip(sorted(nr.keys()),range(1,len(nr)+1)):
    ofile = os.path.join(dir, nr[nfn])
    nfile = os.path.join(dir, nfn.format(ep))
    if ofile==nfile: continue
    if os.path.exists(nfile):
      log.warning(f'{nfile} already exists, skipping.')
    log.info(f'mv "{ofile}" "{nfile}"')
    if args.dryrun: continue
    os.rename(ofile, nfile)

def main():
  for gd in args.dirs:
    ig = [d for d in glob.iglob(gd) if os.path.isdir(d)]
    if len(ig)==0:
      log.warning(f'No directories matching {gd}, skipping.')
      continue
    for d in ig: plexRename(d)

if __name__ == '__main__':
  parser = argparse.ArgumentParser(fromfile_prefix_chars='@',prog=prog,epilog='Written by: '+author)
  parser.add_argument('--version', action='version', version='%(prog)s ' + version)
  parser.add_argument('--dryrun', dest='dryrun', action='store_true', help='do not perform operations, but only print them.')
  parser.add_argument('dirs', nargs='+', help='directories to be operated on')
  parser.add_argument('-v','--verbose',dest='loglevel',action='store_const', const=logging.INFO)
  parser.add_argument('-d','--debug',dest='loglevel',action='store_const', const=logging.DEBUG)
  parser.add_argument('-l','--log',dest='logfile',action='store')
  parser.set_defaults(loglevel=logging.WARN)

  args = parser.parse_args()
  if args.dryrun and args.loglevel > logging.INFO: args.loglevel = logging.INFO

  logformat = logging.Formatter('%(asctime)s [%(levelname)s]: %(message)s')

  if args.logfile:
    flogger=logging.handlers.WatchedFileHandler(args.logfile, 'a', 'utf-8')
    flogger.setLevel(logging.DEBUG)
    flogger.setFormatter(logformat)
    log.addHandler(flogger)

  slogger=logging.StreamHandler()
  slogger.setLevel(args.loglevel)
  slogger.setFormatter(logformat)
  log.addHandler(slogger)

  main()