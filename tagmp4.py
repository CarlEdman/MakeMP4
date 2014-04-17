#!/usr/bin/python
# -*- coding: latin-1 -*-

prog='TagMP4'
version='0.1'
author='Carl Edman (CarlEdman@gmail.com)'

import shutil, re, shlex, os, codecs, argparse, ConfigParser, logging
from os.path import exists, isfile, getmtime, getsize, join, basename, splitext, abspath, dirname
from os import rename
from string import strip, digits, translate, upper
from logging import debug, info, warn, error, critical

def lfind(l,*ws):
  for w in ws:
    if w in l: return l.index(w)
  return -1

def update_description_tvshow(cfg,txt):
  tl=txt.splitlines()
  h=tl[0].split('\t')
  tl=tl[1:]
  i=lfind(h,"\xe2\x84\x96")
  if i<0: i=lfind('?')
  if i>=0: h[i]='Series Episode'
  
  epi=lfind(h,'#')
  if epi<0: return False # Fix
  sei=lfind(h,'Series Episode')
  tii=lfind(h,'Title')
  dei=lfind(h,'Description')
  if dei<0: dei=len(h)
  h.append('Description')
  i=1
  while i<len(tl):
    if '\t' not in tl[i]:
      tl[i-1]=tl[i-1]+'\t'+tl[i]
      tl[i]=''
    i+=1
  wri=lfind(h,'Written by','Writer')
  dai=lfind(h,'Original Airdate','Original air date','Original airdate','Airdate')
  pci=lfind(h,'Production code','Prod. code')
  
  for t in tl:
    if not t: continue
    l=t.split('\t')
    if l[epi]!=str(cfg.get('episode','*')): continue
    if 0<=tii<len(l) and l[tii] and cfg.hasno('song'):
      cfg.set('song',l[tii].strip('" '))
    if 0<=wri<len(l) and l[wri] and cfg.hasno('writer'):
      cfg.set('writer',re.sub('\s*&\s*','; ',l[wri]))
    if 0<=pci<len(l) and l[pci] and cfg.hasno('episodeid'):
      cfg.set('episodeid',l[pci].strip())
    if 0<=dai<len(l) and imps(r'\b([12]\d\d\d)\b',l[dai]) and cfg.hasno('year'):
      cfg.set('year',int(img[0]))
    if 0<=dei<len(l) and l[dei] and cfg.hasno('description'):
      cfg.set('description',l[dei])
    for i in range(len(l)):
      if i in [epi,tii,wri,pci,dei]: continue
      s=strip(l[i])
      if not s: continue
      s=strip(h[i])+': '+s
      if s not in cfg.get('comment',''): cfg.append('comment', s)

parser = argparse.ArgumentParser(description='Tag mp4s from standard i from .mkv, .mpg, .TiVo, or .vob files; convert video tracks to h264, audio tracks to aac; then recombine all tracks into properly tagged .mp4',fromfile_prefix_chars='@',prog=prog,epilog='Written by: '+author)
parser.add_argument('--version', action='version', version='%(prog)s '+version)
parser.add_argument('--format', action='store', help='format for mp4 files to be tagged with standard substitution for episode number.')
args = parser.parse_args()

    update_description(f)
