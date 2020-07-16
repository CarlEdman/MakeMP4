#!/usr/bin/python

prog='fixidx'
version='0.1'
author='Carl Edman (CarlEdman@gmail.com)'

import re

from cetools import *

d=0.0
e=1.0

with open('Batman Begins () Batman Mythology T03.idx', 'r') as i:
  ltime=0
  for l in i:
    if m:= re.fullmatch(r'(?P<beg>\s*timestamp:\s*)(?P<time>-?\d+:\d+:\d+:\d+(?=\.\d+)?)(?P<end>.*)',l):
      otime = parse_time(m['time'])
      ntime = otime*e+d
      if ntime<0: continue
      print(otime-ltime,otime)
      ltime=otime
      # print(f'{m["beg"]}{unparse_time(ntime)}{m["end"]}')
    else:
      print(l)
