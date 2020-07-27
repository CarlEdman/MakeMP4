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

class DefaultDict(collections.UserDict):
  """A subclass of Userdict for use by SyncConfig"""

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)

  def __getitem__(self, key):
    return self.data[key] if key in self.data else None

  def __setitem__(self, key, item):
#   log,debug((key, type(key), item, type(item)))
    if item is None:
      if key not in self.data: return
      del self.data[key]
    else:
      if key in self.data and self.data[key] == item: return
      self.data[key] = item

  def additem(self, key):
    self.data[key] = DefaultDict()

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

    try:
      if isinstance(v, Fraction):
        return v
      elif isinstance(v, float):
        [ num, denom ] = float(v).as_integer_ratio()
        return Fraction(int(num),int(denom))
      elif isinstance(v, str) and ':' in v:
        [ num, denom ] = v.split(':')
        return Fraction(int(num),int(denom))
      elif isinstance(v, str) and '/' in v:
        [ num, denom ] = v.split('/')
        return Fraction(int(num),int(denom))
    except ValueError:
      return None
    return None

  def getlist(self, key):
    if key not in self.data: return []
    v = self.data[key]
    return v.split(';')

  def getset(self, key):
    if key not in self.data: return []
    v = self.data[key]
    return set(v.split(';'))


class TitleHandler(logging.Handler):
  """
  A handler class which writes logging records, appropriately formatted,
  to the windows' title bar.
  """

  def __init__(self):
    logging.Handler.__init__(self)

  def flush(self):
    pass

  def emit(self, record):
    if os.name == 'nt':
      ctypes.windll.kernel32.SetConsoleTitleA(self.format(record).encode(encoding='cp1252', errors='ignore'))

def nice(niceness):
  '''Nice for Windows Processes.  Nice is a value between -3-2 where 0 is normal priority.'''
  if hasattr(os, 'nice'):
    return os.nice(niceness) # pylint: disable=no-member
  elif os.name == 'nt':
    pcs = [win32process.IDLE_PRIORITY_CLASS, win32process.BELOW_NORMAL_PRIORITY_CLASS,
        win32process.NORMAL_PRIORITY_CLASS, win32process.ABOVE_NORMAL_PRIORITY_CLASS,
        win32process.HIGH_PRIORITY_CLASS, win32process.REALTIME_PRIORITY_CLASS]
    pri = pcs[max(0, min(2-niceness, len(pcs)-1))]

    pid = win32api.GetCurrentProcessId()
    handle = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, True, pid)
    win32process.SetPriorityClass(handle, pri)

def dict_inverse(d):
  '''Create an inverse dict from a dict.'''

  return { v:k for k,v in d.items() }

def alphabetize(s):
  s=s.strip().rstrip('.')
  if s.startswith("The "): s=s[4:]
  elif s.startswith("A "): s=s[2:]
  elif s.startswith("An "): s=s[3:]
  return s

def romanize(s):
  rom = { "M": 1000, "CM": 900, "D": 500, "CD": 400, "C": 100, "XC": 90,
          "L": 50, "XL": 40, "X": 10, "IX": 9, "V": 5, "IV": 4, "I": 1 }
  t = s
  r = 0
  for k, v in rom.items():
    while t.startswith(k):
      t = t[len(k):]
      r += v
  return s if t else r

def sortkey(s):
  '''A sorting key for strings that alphabetizes and orders numbers correctly.'''

  s = alphabetize(s)
  # TODO: Sort Spelled-out numerals correctly?
  s=re.sub(r'\b[IVXLCDM]+\b',lambda m: str(romanize(m[0])) if m[0]!="I" else s,s)
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
    log.warning(f'File "{file}" already worklocked')
    return False
  open(file+worklock,'w').truncate(0)
  return True

def work_unlock(file):
  if not file:
    return False
  if not os.path.exists(file+worklock):
    log.warning('File "{file}" not worklocked')
    return False
  if os.path.getsize(file+worklock) != 0:
    log.error(f'Worklock for "{file}" not empty!')
    return False
  os.remove(file+worklock)

def work_locked(file):
  return os.path.exists(file+worklock)

def work_lock_delete():
  for l in os.listdir(os.getcwd()):
    if not l.endswith(worklock): continue
    if os.path.getsize(l) != 0:
       log.error(f'Worklock "{l}" not empty!')
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
