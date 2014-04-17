#!/usr/bin/python
# -*- coding: latin-1 -*-

import urllib.request
#f = urllib.request.urlopen('http://chapterdb.org/browse?title=Madagascar')
f = urllib.request.urlopen('http://dvd.netflix.com/Search?v1=Madagascar')
print(f.info())
print(f.read().decode('utf-8'))
