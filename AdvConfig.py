#!/usr/bin/python
# A subclass of ConfigParser with advanced features

import os.path

from fractions import Fraction
from weakref import WeakValueDictionary, finalize
from configparser import RawConfigParser, NoSectionError

from cetools import *

log = logging.getLogger()

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
    if not os.path.exists(self.filename):
      with open(self.filename, 'wt', encoding='utf-8') as fp: self.write(fp)
    elif self.modified:
      if self.mtime<os.path.getmtime(self.filename):
        log.warning('Overwriting external edits in "{}"'.format(self.filename))
      with open(self.filename, 'wt', encoding='utf-8') as fp: self.write(fp)
    elif self.mtime<os.path.getmtime(self.filename):
      with open(self.filename, 'rt', encoding='utf-8') as fp: self.read_file(fp)
    self.mtime=os.path.getmtime(self.filename)
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
    if isinstance(v,pathlib.PurePath): return v.as_posix()
    if isinstance(v,str):
      if v.strip('-0123456789./: ')=='':
        return f'"{v}"'
      else:
        return v.strip()
    return repr(v)

  @staticmethod
  def strtoval(s):
    if len(s)>1 and s[0]==s[-1]=='_': return None
    if len(s)>1 and s[0]==s[-1]=='"': return s[1:-1]
#    if s.find(';')>=0: return [self.strtoval(i) for i in s.split(';')]
    if s.lstrip('-').strip('0123456789')=='': return int(s)
    if s.lstrip('-').strip('0123456789')=='.': return float(s)
    if s.lstrip('-').strip('0123456789')=='/': return Fraction(s)
    if s.lstrip('-').strip('0123456789')==':': return Fraction(int(s[:s.index(':')]),int(s[s.index(':')+1:]))
    if s.lower() in { 'yes', 'true', 'on'}: return True
    if s.lower() in { 'no', 'false', 'off'}: return False
    return s

  def set(self,opt,nval=None,section=None):
    if not section: section=self.currentsection
    if not section: raise NoSectionError('No Current Section Set')
    if RawConfigParser.has_option(self, section, opt):
      sval = RawConfigParser.get(self,section,opt)
      if nval == sval: return
      oval = self.strtoval(sval)
    else:
      oval = None
    if oval == nval: return
    if not nval and oval is None: return

    self.modified=True
    if nval:
      RawConfigParser.set(self,section,opt,self.valtostr(nval))
    else:
      RawConfigParser.remove_option(self,section,opt)
    log.debug(f'{section} {opt}: {oval}({type(oval)}) => {nval}({type(nval)})')

  def items(self,section=None):
    if not section: section=self.currentsection
    if not section: raise NoSectionError('No Current Section Set')
    return dict(RawConfigParser.items(self,section))

  def item_defs(self, defs, section=None):
    if not section: section=self.currentsection
    if not section: raise NoSectionError('No Current Section Set')
    for opt, nval in defs.items():
      oval = self.get(opt, section = section)
      if oval == nval: continue
      if not nval and oval is None: continue
      if oval: continue
      log.debug(f'{section} {opt}: => {nval}{type(nval)}')
      self.set(opt, nval, section=section)

  def get(self, opt, default=None, section=None):
    if not section: section=self.currentsection
    if not section: raise NoSectionError('No Current Section Set')
    if self.hasno(opt, section): return default
    return self.strtoval(RawConfigParser.get(self, section, opt))

  def has(self,opt,section=None):
    if not section: section=self.currentsection
    if not section: raise NoSectionError('No Current Section Set')
    if not self.has_option(section,opt): return False
    i = RawConfigParser.get(self,section,opt)
    if i == None: return False
    if i =='': return False
    if i.startswith(r'_') and i.endswith(r'_'): return False
    return True

  def hasno(self,opt,section=None):
    return not self.has(opt,section)
