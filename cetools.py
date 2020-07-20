#!/usr/bin/python
# Various utility functions

import collections
import logging
import logging.handlers
import os
import os.path
import re
import time
import weakref

from configparser import ConfigParser
from weakref import WeakValueDictionary, finalize
from fractions import Fraction


if os.name == 'nt':
  import ctypes
  import win32api
  import win32process
  import win32con

log = logging.getLogger()

def export(func):
  if '__all__' not in func.__globals__:
    func.__globals__['__all__'] = []
  func.__globals__['__all__'].append(func.__name__)
  return func

class SyncDict(collections.UserDict):
  """A subclass of Userdict for use by SyncConfig"""

  def __init__(self, config):
    super().__init__()
    self.config = config
    self.modified = False

  def __getitem__(self, key):
    if key in self.data:
      return self.data[key]
    return None

  def __setitem__(self, key, item):
    if item is None:
      if key not in self.data: return
      del self.data[key]
      self.modified = True
      return
    
    if not isinstance(item, str): item = str(item)
    if self.data[key] == item: return

    self.data[key] = item
    self.modified = True

  def getstr(self, key):
    if key not in self.data: return None
    v = self.data[key]
    if isinstance(v, str) and v[0]=='_' and v[-1]=='_': return None
    return v

  def getint(self, key):
    if key not in self.data: return None
    v = self.data[key]
    try:
      return int(v)
    except ValueError:
      return None

  def getfloat(self, key):
    if key not in self.data: return None
    v = self.data[key]

    if ':' in v:
      try:
        [ num, denom ] = v.split(':')
        return float(int(num)/int(denom))
      except ValueError:
        return None
    
    if '/' in v:
      try:
        [ num, denom ] = v.split('/')
        return float(int(num)/int(denom))
      except ValueError:
        return None
    
    try:
      return float(v)
    except ValueError:
      return None

  def getfraction(self, key):
    if key not in self.data: return None
    v = self.data[key]
    
    if ':' in v:
      try:
        [ num, denom ] = v.split(':')
        return Fraction(int(num),int(denom)) 
      except ValueError:
        return None
    if '/' in v:
      try:
        [ num, denom ] = v.split('/')
        return Fraction(int(num),int(denom)) 
      except ValueError:
        return None
    
    try:
      [ num, denom ] = float(v).as_integer_ratio()
      return Fraction(int(num),int(denom)) 
    except ValueError:
      return None

  def getlist(self, key):
    if key not in self.data: return []
    v = self.data[key]
    return v.split(';')

  def getset(self, key):
    if key not in self.data: return []
    v = self.data[key]
    return set(v.split(';'))

class SyncConfig(ConfigParser):
  """A subclass of ConfigParser with automatic syncing to files"""
  _configs = weakref.WeakValueDictionary()

  def __new__(cls, filename):
    if filename in SyncConfig._configs:
      n = SyncConfig._configs[filename]
      n.sync()
    else:
      n = super(SyncConfig, cls).__new__(cls)
      SyncConfig._configs[filename]=n
      weakref.finalize(n, n.sync)
    return n

  def __init__(self, filename):
    if hasattr(self, 'filename') and self.filename == filename: return
    self.filename = filename
    self.dict_type = SyncDict
    super().__init__(allow_no_value=True)
    self.sync()

  def sync(self):
    if not os.path.exists(self.filename):
      with open(self.filename, 'wt', encoding='utf-8') as fp: self.write(fp)
      self.mtime=os.path.getmtime(self.filename)
      return

    sects_modified = False
    for s in self.sections():
      if self[s].modified:
        sects_modified = True
        self[s].modified = False

    file_modified = self.mtime < os.path.getmtime(self.filename)

    if sects_modified:
      if file_modified:
        log.warning(f'Overwriting external edits in "{self.filename}"')
      with open(self.filename, 'wt', encoding='utf-8') as f:
        self.write(f)
    elif file_modified:
      with open(self.filename, 'rt', encoding='utf-8') as f:
        self.read_file(f)


class TitleHandler(logging.Handler):
  """
  A handler class which writes logging records, appropriately formatted,
  to the windows' title bar.
  """

  def __init__(self):
    """
    Initialize the handler.
    """

    logging.Handler.__init__(self)

  def flush(self):
    """
    Flushes the stream.  (A noop for this handler)
    """

    pass

  def emit(self, record):
    """
    Emit a record.

    If a formatter is specified, it is used to format the record.
    The record is then written to the title bar of the current window.
    """

    if os.name == 'nt':
      ctypes.windll.kernel32.SetConsoleTitleA(self.format(record).encode(encoding='cp1252', errors='ignore'))

def nice(niceness):
  '''Nice for Windows Processes.  Nice is a value between -3-2 where 0 is normal priority.'''
  if os.name == 'nt':
    pcs = [win32process.IDLE_PRIORITY_CLASS, win32process.BELOW_NORMAL_PRIORITY_CLASS,
        win32process.NORMAL_PRIORITY_CLASS, win32process.ABOVE_NORMAL_PRIORITY_CLASS,
        win32process.HIGH_PRIORITY_CLASS, win32process.REALTIME_PRIORITY_CLASS]
    pri = pcs[max(0, min(2-niceness, len(pcs)-1))]

    pid = win32api.GetCurrentProcessId()
    handle = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, True, pid)
    win32process.SetPriorityClass(handle, pri)
  else:
    return os.nice(niceness)

def dict_inverse(d):
  '''Create an inverse dict from a dict.'''

  return { v:k for k,v in d.items()}

def alphabetize(s):
  s=s.strip()
  if s.startswith("The "): s=s[4:]
  elif s.startswith("A "): s=s[2:]
  elif s.startswith("An "): s=s[3:]

  if s.endswith("."): s=s[:-1]
  return s

def sortkey(s):
  '''A sorting key for strings that alphabetizes and orders numbers correctly.'''
  s = alphabetize(s)
  # TODO: Sort Roman Numerals Correctly?
  # TODO: Sort Spelled-out numerals correctly?
  s=re.sub(r'\d+',lambda m: m[0].zfill(10),s)
  return s.casefold()

def reglob(filepat, dir = None):
  '''A replacement for glob.glob which uses regular expressions and sorts numbers up to 10 digits correctly.'''
  if dir is None: dir = '.'
  if os.name == 'nt': filepat = r'(?i)' + filepat
  files = (os.path.join(dir,f) for f in os.listdir(dir) if re.fullmatch(filepat, f))
  return sorted(files, key=sortkey)

def sanitize_filename(s):
  trans = str.maketrans('','',r':"/\:*?<>|'+r"'")
  return s.translate(trans)

def parse_time(s):
  m = re.fullmatch(r'(?P<neg>-)?(?P<hrs>\d+):(?P<mins>\d+):(?P<secs>\d+(\.\d*)?)', s)
  if not m: return m
  t = float(m['secs'])
  if m['mins']: t += 60.0*float(m['mins'])
  if m['secs']: t += 3600.0*float(m['hrs'])
  if m['neg']:  t = -t
  return t

def unparse_time(t):
  return f'{"-" if t<0 else ""}{int(abs(t)/3600.0):02d}:{int(abs(t)/60.0)%60:02d}:{int(abs(t))%60:02d}:{int(abs(t)*1000.0)%1000:03d}'

def semicolon_join(s, t):
  if not isinstance(s, str): return t
  if not isinstance(t, str): return s
  return ';'.join(sorted(set(s.split(';')) | set(t.split(';'))))

worklock='.working'
def work_lock(file):
  if not file:
    return False
  if os.path.exists(file+worklock):
    log.warning('File "' + file + '" already worklocked')
    return False
  open(file+worklock,'w').truncate(0)
  return True

def work_unlock(file):
  if not file:
    return False
  if not os.path.exists(file+worklock):
    log.warning('File "' + file + '" not worklocked')
    return False
  if os.path.getsize(file+worklock) != 0:
    log.error('Worklock for "' + file + '" not empty!')
    return False
  os.remove(file+worklock)

def work_locked(file):
  return os.path.exists(file+worklock)

def work_lock_delete():
  for l in os.listdir(os.getcwd()):
    if not l.endswith(worklock): continue
    if os.path.getsize(l) != 0:
       log.error('Worklock for "' + file + '" not empty!')
       continue
    os.remove(l)
    f = l[:-len(worklock)]
    if not os.path.exists(f):
      log.warning('No file existed for worklock "' + l + '"')
      continue
    os.remove(f)

def sleep_change_directories(dirs,state=None):
  '''Sleep until any of the files in any of the dirs has changed.'''

  while True:
    nstate = { os.path.join(d,f): os.stat(os.path.join(d,f)) for d in dirs for f in os.listdir(d) }
    if nstate != state: return nstate

    if os.name == 'nt':
      import win32file, win32event, win32con
      watches = win32con.FILE_NOTIFY_CHANGE_FILE_NAME | win32con.FILE_NOTIFY_CHANGE_ATTRIBUTES | win32con.FILE_NOTIFY_CHANGE_LAST_WRITE
      try:
        chs = [ win32file.FindFirstChangeNotification(d, 0, watches) for d in dirs ]
        while win32event.WaitForMultipleObjects(chs, 0, 1000) == win32con.WAIT_TIMEOUT: pass
      finally:
        for ch in chs: win32file.FindCloseChangeNotification(ch)
    else:
      time.sleep(10)
