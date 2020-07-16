#!/usr/bin/python

import os, sys, glob

for a in sys.argv[1:]:
  for f in glob.glob(a):
    os.utime(f,None)
