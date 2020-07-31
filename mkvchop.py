#!/usr/bin/python

prog='mkvchop'
version='0.4'
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
  chaps=dict()
  for l in subprocess.check_output(['mkvextract', 'chapters', '--simple', args.infile], universal_newlines = True).splitlines():
    if m := re.fullmatch(r'CHAPTER(\d+)=(.*)',l) and (t := to_float(m[2])):
       chaps[int(m[1])]=t

  splits=[]
  chap=None
  for s in args.split:
    if m := re.fullmatch(r'\d+',s):
      chap=int(m[0])
      if chap not in chaps:
        log.warning(f'Chapter {chap:d} not in "{args.infile}"')
        sys.exit(-1)
      splits.append(chaps[chap])
    elif m := re.fullmatch(r'\+(\d+)',s):
      i=int(m[1])
      if not chap:
        log.warning(f'No previous chapter for increment +{i:d} not in "{args.infile}"')
      chap+=i
      while chap in chaps:
        splits.append(chaps[chap])
        chap+=i
    elif t := to_float(s):
      splits.append(t)

  timecodes=",".join(unparse_time(s) for s in splits)

  log.debug(subprocess.check_output(['mkvmerge','--split','timecodes:'+timecodes,'-o','Temp-%06d.mkv',args.infile]))

  if splits[0] != 0.0:
    os.remove('Temp-000001.mkv')

  for tf,ff in zip(reglob(r'Temp-\d{6}\.mkv'),(args.outfiles.format(i) for i in range(args.start,sys.maxsize))):
    chaptimes=[]
    chapnames=[]
    for l in subprocess.check_output(['mkvextract', 'chapters', '--simple', tf], universal_newlines = True).splitlines():
      if m := re.fullmatch(r'CHAPTER(\d+)=(.*)',l) and (t := to_float(m[2])):
        chaptimes.append(t)
      elif m := re.fullmatch(r'^CHAPTER(\d+)NAME=(.*)$',l):
        chapnames.append(m[1])
    chapchange=False

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
      chapfile=tf+'.chap.txt'
      with open(chapfile,'w') as cf:
        for no,cn,ct in zip(range(sys.maxsize),chapnames,chaptimes):
          cf.write(f'CHAPTER{no:02d}={unparse_time(ct)}\n')
          cf.write(f'CHAPTER{no:02d}NAME={cn}\n')

      log.debug(subprocess.check_output(['mkvmerge','--output', ff, '--chapters', chapfile, '--no-chapters', tf]))
      os.remove(tf+'.chap.txt')
      os.remove(tf)
    else:
      os.rename(tf,ff)

if __name__ == '__main__':
  parser = argparse.ArgumentParser(fromfile_prefix_chars='@',prog=prog,epilog='Written by: '+author)
  parser.add_argument('--version', action='version', version='%(prog)s '+version)
  parser.add_argument('-s', '--start', type=int, default=1, help='initial value of index for outfiles (default: %(default)d)')
  parser.add_argument('--debug', action='store_true', default=False, help='output debugging messages')
  parser.add_argument('infile', type=str, help='mkv file to be chopped up')
  parser.add_argument('outfiles', type=str, help='mkv files to be created with decimal {} formatter')
  parser.add_argument('split', nargs='+', metavar='timecodeOrChapter', help='splitting points; may be either integer (for timecode from chapter number), +integer (to generate additional cutting points at regular chapter intervals starting at the last chapter given), float (for timecode in seconds), or hh:mm:ss.ms (for timecode in alternate format)')

  args = parser.parse_args()

  log.setLevel(0)
  logformat = logging.Formatter('%(asctime)s [%(levelname)s]: %(message)s')

  slogger=logging.StreamHandler()
  slogger.setLevel(args.loglevel)
  slogger.setFormatter(logformat)
  log.addHandler(slogger)

  main()
