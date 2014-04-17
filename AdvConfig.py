#!/usr/bin/python
# -*- coding: latin-1 -*-
# A subclass of ConfigParser with advanced features

from configparser import ConfigParser
from os.path import exists, isfile, getmtime, getsize, join, basename, splitext, abspath, dirname
from fractions import Fraction
from weakref import WeakValueDictionary

class AdvConfig(ConfigParser):
  """A subclass of ConfigParser for with advanced features"""
  _configs=WeakValueDictionary()
  
  def __new__(cls,filename):
    if filename in AdvConfig._configs:
      n=AdvConfig._configs[filename]
      n.sync()
    else:
      n=super(AdvConfig,cls).__new__(cls)
      AdvConfig._configs[filename]=n      
    return n
  
  def __init__(self,filename):
    if hasattr(self,'mtime'): return 
    ConfigParser.__init__(self,allow_no_value=True)
    self.filename=filename
    self.currentsection=None
    self.modified=False
    self.mtime=-1
    self.sync()
  
  def __del__(self):
    self.sync()
    del AdvConfig._configs[self.filename]
    return ConfigParser.__del__(self)
  
  def sync(self, dirty=False):
    if not exists(self.filename):
#      print('Writing new: '+self.filename)
      with open(self.filename, 'w') as fp: self.write(fp)
    elif dirty or self.modified:
      if self.mtime<getmtime(self.filename):
        warn('Overwriting external edits in "{}"'.format(self.filename))
#      print('Overwriting: '+self.filename)
      with open(self.filename, 'w') as fp: self.write(fp)
    elif self.mtime<getmtime(self.filename):
      with open(self.filename, 'r') as fp: self.read_file(fp)
#      print('Reading: '+self.filename)
    self.mtime=getmtime(self.filename)
    self.modified=False

  def setsection(self,sect):
    if not self.has_section(sect):
      self.add_section(sect)
      self.modified=True
    self.currentsection=sect
  
  @staticmethod
  def valtostr(v):
#    if isinstance(v,list): return ';'.join([self.valtostr(i) for i in v])
    if isinstance(v,bool): return "Yes" if v else "No"
    if isinstance(v,int): return str(v)
    if isinstance(v,float): return str(v)
    if isinstance(v,Fraction): return str(v.numerator)+'/'+str(v.denominator)
    if isinstance(v,str): return v.strip()
    return repr(v)
  
  @staticmethod
  def strtoval(s):
    if s.lower() in ['yes', 'true', 'on']: return True
    if s.lower() in ['no', 'false', 'off']: return False
    if s[0]=='"' and s[-1]=='"': return s.strip('"')
#    if s.find(';')>=0: return [self.strtoval(i) for i in s.split(';')]
    if s.lstrip('-').strip('0123456789')=='': return int(s)
    if s.lstrip('-').strip('0123456789')=='.': return float(s)
    if s.lstrip('-').strip('0123456789')=='/': return Fraction(s)
    if s.lstrip('-').strip('0123456789')==':': return Fraction(int(s[:s.index(':')]),int(s[s.index(':')+1:]))
    return s
  
  def set(self,option,value=None,section=None):
    if not section:
      if not self.currentsection: raise configparser.NoSectionError('No Current Section Set')
      section=self.currentsection
    
    oval=ConfigParser.get(self,section,option) if self.has_option(section,option) else None
    nval=self.valtostr(value)
    if oval and oval==nval: return
    ConfigParser.set(self,section,option,nval)
    self.modified=True
  
  def items(self,section=None):
    if not section:
      if not self.currentsection: raise configparser.NoSectionError('No Current Section Set')
      section=self.currentsection
    return ConfigParser.items(self,section)
  
  def get(self,option,default=None,section=None):
    if not section:
      if not self.currentsection: raise configparser.NoSectionError('No Current Section Set')
      section=self.currentsection
    if not self.has_option(section,option) or ConfigParser.get(self,section,option)=='': return default
    return self.strtoval(ConfigParser.get(self,section,option))
  
  def has(self,option,section=None):
    if not section:
      if not self.currentsection: raise configparser.NoSectionError('No Current Section Set')
      section=self.currentsection
    return self.has_option(section,option) and ConfigParser.get(self,section,option)
  
  def hasno(self,option,section=None):
    return not self.has(option,section)
