#!/usr/bin/python

prog='mkvchop'
version='0.5'
author='Carl Edman (CarlEdman@gmail.com)'
desc='Chop an mkv file into subfiles at timecodes or chapters.'

import argparse
import logging
import math
import os
import os.path
import re
import subprocess
import sys

from cetools import * # pylint: disable=unused-wildcard-import

parser = None
args = None
log = logging.getLogger()

def main():
  chaptimes = {}
  chapnames = {}
  namechaps = {}
  for l in subprocess.check_output(['mkvextract', 'chapters', '--simple', args.infile], universal_newlines = True).splitlines():
    if (m := re.fullmatch(r'CHAPTER(\d+)=(.*)',l)) is not None and \
          (i := int(m[1])) is not None and \
          (t := to_float(m[2])) is not None:
        chaptimes[i]=t
    elif (m := re.fullmatch(r'CHAPTER(\d+)NAME=(.*)',l)) is not None  and \
          (i := int(m[1])) is not None:
      chapnames[i]=m[2]
      namechaps[m[2]]=i
    else:
      log.warning(f'mkv chapter line "{l}" not parsable.')

  splits=[]
  chap=None
  for s in args.split:
    if s in namechaps:
      chap=namechaps[s]
      splits.append(chaptimes[chap])
    elif m := re.fullmatch(r'\d+',s):
      chap=int(m[0])
      if chap not in chaptimes:
        log.warning(f'Chapter {chap:d} not in "{args.infile}"')
        sys.exit(-1)
      splits.append(chaptimes[chap])
    elif m := re.fullmatch(r'\+(\d+)',s):
      i=int(m[1])
      if not chap:
        log.warning(f'No previous chapter for increment +{i:d} not in "{args.infile}"')
      chap+=i
      while chap in chaptimes:
        splits.append(chaptimes[chap])
        chap+=i
    elif t := to_float(s):
      splits.append(t)

  if splits[0] != 0.0:
    splits.insert(0,0.0)
  timecodes=",".join(unparse_time(s) for s in splits)

  chaptimes=list(chaptimes.values())
  chapnames=list(chapnames.values())

  ffs = [args.outfiles.format(i) for i in range(args.start,args.start+len(splits))]
  tfs = [f'Temp-{t:06d}.mkv' for t in range(1,1+len(splits))]
  brks = ', '.join(f + "@" + unparse_time(s) for (f,s) in zip(ffs, splits))
  log.info(f'Spliting {args.infile} into {brks}')
  if args.dryrun:
    return
  else:
    log.debug(subprocess.check_output(['mkvmerge','--split','timecodes:'+timecodes,'-o','Temp-%06d.mkv',args.infile]))

  for tf, ff in zip(tfs,ffs):
    chapchange=False
    for l in subprocess.check_output(['mkvextract', 'chapters', '--simple', tf], universal_newlines = True).splitlines():
      if (m := re.fullmatch(r'CHAPTER(\d+)=(.*)',l)) and \
        (i := int(m[1])) is not None and \
        (t := to_float(m[2])) is not None:
        chaptimes[i]=t
      elif (m := re.fullmatch(r'CHAPTER(\d+)NAME=(.*)',l)) and \
        (i := int(m[1])) is not None:
        chapnames[i]=m[2]

    if len(chaptimes)>=2 and chaptimes[1]-chaptimes[0]<1.0:
      chaptimes[1]=chaptimes[0]
      chaptimes=chaptimes[1:]
      chapnames=chapnames[1:]
      chapchange=True

    if len(chaptimes)>=3 and chaptimes[-1]-chaptimes[-2]<1.0:
      chaptimes=chaptimes[:-1]
      chapnames=chapnames[:-1]
      chapchange=True

    if chapchange:
      for no,cn,ct in zip(range(sys.maxsize),chapnames,chaptimes):
        log.info(f'Creating {ff} chapter {no} {cn}={unparse_time(ct)}')
      chapfile=tf+'.chap.txt'
      with open(chapfile,'w') as cf:
        for no,cn,ct in zip(range(sys.maxsize),chapnames,chaptimes):
          cf.write(f'CHAPTER{no:02d}={unparse_time(ct)}\n')
          cf.write(f'CHAPTER{no:02d}NAME={cn}\n')

      log.debug(subprocess.check_output(['mkvmerge','--output', ff, '--chapters', chapfile, '--no-chapters', tf]))
      os.remove(tf+'.chap.txt')
      os.remove(tf)
    else:
      log.info(f'Not modifying {ff} chapters')
      os.rename(tf,ff)

if __name__ == '__main__':
  parser = argparse.ArgumentParser(fromfile_prefix_chars='@',prog=prog,epilog='Written by: '+author)
  parser.add_argument('--version', action='version', version='%(prog)s '+version)
  parser.add_argument('--dryrun', dest='dryrun', action='store_const', const=True, default=False, help='dryrun only; do not modify file')
  parser.add_argument('-s', '--start', type=int, default=1, help='initial value of index for outfiles (default: %(default)d)')
  parser.add_argument('infile', type=str, help='mkv file to be chopped up')
  parser.add_argument('outfiles', type=str, help='mkv files to be created with decimal {} formatter')
  parser.add_argument('split', nargs='+', metavar='timecodeOrChapter', help='splitting points; may be either integer (for timecode from chapter number), +integer (to generate additional cutting points at regular chapter intervals starting at the last chapter given), float (for timecode in seconds), or hh:mm:ss.ms (for timecode in alternate format)')
  parser.add_argument('-v','--verbose',dest='loglevel',action='store_const', const=logging.INFO)
  parser.add_argument('-d','--debug',dest='loglevel',action='store_const', const=logging.DEBUG)
  parser.set_defaults(loglevel=logging.WARN)

  args = parser.parse_args()
  if args.dryrun: args.loglevel = min(args.loglevel,logging.INFO)

  log.setLevel(0)
  slogger=logging.StreamHandler()
  slogger.setLevel(args.loglevel)
  slogger.setFormatter(logging.Formatter('[%(levelname)s] %(asctime)s: %(message)s'))
  log.addHandler(slogger)

  main()

