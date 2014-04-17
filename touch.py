#!/usr/bin/python
# -*- coding: latin-1 -*-
# Version: 1.0
# Author: Carl Edman (email full name as one word at gmail.com)

import os, sys, glob

for a in sys.argv[1:]:
	for f in glob.glob(a):
		os.utime(f,None)
