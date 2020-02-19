#!/usr/bin/python
# A subclass of ConfigParser with advanced features

from cetools import *

from configparser import ConfigParser, RawConfigParser
from os.path import exists, isfile, getmtime, getsize, join, basename, splitext, abspath, dirname
from fractions import Fraction
from weakref import WeakValueDictionary, finalize

class AdvConfig(RawConfigParser):
  """A subclass of RawConfigParser for with advanced features"""
  _configs = WeakValueDictionary()

  def __new__(cls, filename):
    if filename in AdvConfig._configs:
      n=AdvConfig._configs[filename]
      n.sync()
    else:
      n=super(AdvConfig,cls).__new__(cls)
      AdvConfig._configs[filename]=n
      finalize(n, n.sync)
    return n

  def __init__(self,filename):
    if hasattr(self,'mtime'): return
    super().__init__(allow_no_value=True)
    self.filename=filename
    self.currentsection=None
    self.modified=False
    self.mtime=-1
    self.sync()

  def sync(self):
    if not exists(self.filename):
      with open(self.filename, 'wt', encoding='utf-8') as fp: self.write(fp)
    elif self.modified:
      if self.mtime<getmtime(self.filename):
        warning('Overwriting external edits in "{}"'.format(self.filename))
      with open(self.filename, 'wt', encoding='utf-8') as fp: self.write(fp)
    elif self.mtime<getmtime(self.filename):
      with open(self.filename, 'rt', encoding='utf-8') as fp: self.read_file(fp)
    self.mtime=getmtime(self.filename)
    self.modified=False

  def setsection(self,sect):
    if not self.has_section(sect):
      self.add_section(sect)
      self.modified=True
    self.currentsection=sect

  def getsection(self):
    return self.currentsection

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
    if not section: section=self.currentsection
    if not section: raise configparser.NoSectionError('No Current Section Set')

    oval=RawConfigParser.get(self,section,option) if self.has_option(section,option) else None
    nval=self.valtostr(value)
    if oval and oval==nval: return
    RawConfigParser.set(self,section,option,nval)
    self.modified=True

  def items(self,section=None):
    if not section: section=self.currentsection
    if not section: raise configparser.NoSectionError('No Current Section Set')
    return RawConfigParser.items(self,section)

  def get(self,option,default=None,section=None):
    if not section: section=self.currentsection
    if not section: raise configparser.NoSectionError('No Current Section Set')
    if self.hasno(option, section): return default
    return self.strtoval(RawConfigParser.get(self,section,option))

  def has(self,option,section=None):
    if not section: section=self.currentsection
    if not section: raise configparser.NoSectionError('No Current Section Set')
    if not self.has_option(section,option): return False
    i = RawConfigParser.get(self,section,option)
    if i == None: return False
    if i =='': return False
    if i.startswith(r'$') or i.endswith(r'$'): return False
    return True

  def hasno(self,option,section=None):
    return not self.has(option,section)
