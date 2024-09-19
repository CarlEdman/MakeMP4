#!/usr/bin/python

import glob
import os
import sys

for a in sys.argv[1:]:
  for f in glob.glob(a):
    os.utime(f, None)
