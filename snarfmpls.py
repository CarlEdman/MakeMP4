#!/usr/bin/python

import os.path
import glob
import argparse

prog='SnarfMPLS'
version='0.1'
author='Carl Edman (CarlEdman@gmail.com)'

parser = argparse.ArgumentParser(description='Read mpls and spit out their m2ts.')
parser.add_argument('--version', action='version', version='%(prog)s '+version)
parser.add_argument('dir', type=str, help='directory to search for mpls')
args = parser.parse_args()

for fn in glob.glob(os.path.join(args.dir,'*.mpls')):
  with open(fn,'rb') as f:
    c=f.read()
  ms=os.path.basename(fn)[:-5]+":"
  p=c.find(b'M2TS')
  while (p>=6):
    ms+=c[p-5:p].decode()+","
    p=c.find(b'M2TS',p+1)
  print(ms[:-1])