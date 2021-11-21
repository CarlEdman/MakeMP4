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
  '''Decorator that causes function to be included in __all__.'''

  if '__all__' not in func.__globals__:
    func.__globals__['__all__'] = []
  func.__globals__['__all__'].append(func.__name__)
  return func

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
  '''Multi-platform nice.  Nice is a value between -3-2 where 0 is normal priority.'''

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
  '''Strip leading articles from string.'''

  s=s.strip().rstrip('.')
  if s.startswith("The "): s=s[4:]
  elif s.startswith("A "): s=s[2:]
  elif s.startswith("An "): s=s[3:]
  return s

def romanize(s):
  '''Interpret (loosely) string as roman numeral.'''

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
  '''Remove all characters disallowed in NTFS file name.'''

  trans = str.maketrans('','',r':"/\:*?<>|')
  return s.translate(trans)

def unparse_time(t):
  '''Return float argument as a time in "hours:minutes:seconds" string format.'''

  return f'{"-" if t<0 else ""}{int(abs(t)/3600.0):02d}:{int(abs(t)/60.0)%60:02d}:{int(abs(t))%60:02d}.{int(abs(t)*1000.0)%1000:03d}'

def add_to_list(l, v):
  if v is None: return l
  if not l: return [ v ]
  if v in l: return l
  l.append(v)
  return sorted(l)

def to_ratio_string(f, sep="/"):
  '''Return float argument as a fraction.'''

  (n,d) = Fraction(f).limit_denominator(10000).as_integer_ratio()
  return f'{n}{sep}{d}'

def to_float(s):
  '''Interpret argument as float in a variety of formats.'''

  try:
    return float(s)
  except ValueError:
    pass

  if isinstance(s, str):
    if m := re.fullmatch(r'(?P<neg>-)?(?P<hrs>\d+):(?P<mins>\d+):(?P<secs>\d+)([.,:](?P<msecs>\d*))?', s):
      t = int(m['secs'])
      if m['msecs']: t += int(m['msecs'])/(10.0**len(m['msecs']))
      if m['mins']: t += 60.0*int(m['mins'])
      if m['hrs']: t += 3600.0*int(m['hrs'])
      if m['neg']: t = -t
      return t

    if s.endswith('%'):
      try:
        return float(s[:-1])/100.0
      except ValueError:
        pass

    if len(t := s.split('/'))==2:
      try:
        return float(t[0])/float(t[1])
      except ValueError:
        pass

    if len(t := s.split(':'))==2:
      try:
        return float(t[0])/float(t[1])
      except ValueError:
        pass

  raise ValueError

def sleep_change_directories(dirs,state=None):
  '''Sleep until any of the files in any of the dirs has changed.'''

  while True:
    nstate = { os.path.join(d,f): os.stat(os.path.join(d,f)).st_mtime for d in dirs for f in os.listdir(d) }
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

class defdict(dict):
  '''Dictionary with None default value which tracks modified status.'''

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self._modified=False

  def __getitem__(self, key):
    return super().__getitem__(key) if key in self else None

  def __setitem__(self, key, value):
    '''n.b. Assigning None to a non-None value deletes it.'''

    if value is None:
      if key not in self or self[key] is None: return
      del self[key]
    else:
      if key in self and self[key] == value: return
      super().__setitem__(key, value)
    self._modified = True

  def modified(self):
    '''Check whether defdict (or any of its value defdicts) has been modified.'''

    if self._modified: return True

    # Note: generator, not list, to enable short-circuiting
    m = any(s.modified() for s in self.values() if isinstance(s, defdict))
    return m

  def modclear(self):
    '''Check whether defdict (or any of its value defdicts) has been modified
    and clear modification status.'''

    # Note: list, not generator, to prevent short-circuiting
    m = any([s.modclear() for s in self.values() if isinstance(s, defdict)])
    m = m or self._modified
    self._modified = False
    return m

