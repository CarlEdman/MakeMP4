#!/usr/bin/python
# Various utility functions

import argparse
import json
import logging
import logging.handlers
import os
import pathlib
import re
import time
import yaml
import pathlib

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
  '''Strip leading articles from string or filename.'''

  s=str(s)
  if s.startswith("The "): s=s[4:]
  elif s.startswith("A "): s=s[2:]
  elif s.startswith("An "): s=s[3:]
  return s

def romanize(inp, strict=False):
  '''Interpret string as roman numeral.'''

  rom = [
    ("M", 1000, 1000),
    ("CM", 900, 1),
    ("D", 500, 1),
    ("CD", 400, 1),
    ("C", 100, 3),
    ("XC", 90, 1),
    ("L", 50, 1),
    ("XL", 40, 1),
    ("X", 10, 3),
    ("IX", 9, 1),
    ("V", 5, 1),
    ("IV", 4, 1),
    ("I", 1, 3),
    ]
  restinp = inp
  totvalue = 0
  for symbol, value, maxrep in rom:
    rep = 0
    while restinp.startswith(symbol):
      rep += 1
      if strict and rep > maxrep: return inp
      restinp = restinp[len(symbol):]
      totvalue += value
    if len(restinp) == 0: return totvalue
  return inp

def sortkey(s):
  '''A sorting key for strings that alphabetizes and orders numbers correctly.'''

  s = alphabetize(s)
  # TODO: Sort Spelled-out numerals correctly?
  s=re.sub(r'\b[IVXLCDM]+\b',lambda m: str(romanize(m[0])) if m[0]!="I" else m[0],s)
  s=re.sub(r'\d+',lambda m: m[0].zfill(10),s)
  return s.casefold()

def reglob(filepat, dir = None):
  '''A replacement for glob.glob which uses regular expressions and sorts numbers up to 10 digits correctly.'''

  dir = pathlib.Path(dir) if dir else pathlib.Path.cwd()
  if os.name == 'nt': filepat = r'(?i)' + filepat
  return sorted((f for f in dir.iterdir() if re.fullmatch(filepat, f.name)), key=sortkey)

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
    nstate = { f: f.stat().st_mtime for d in dirs for f in d.iterdir() }
    if nstate != state: return nstate

    if os.name == 'nt':
      import win32file, win32event, win32con
      watches = win32con.FILE_NOTIFY_CHANGE_FILE_NAME | win32con.FILE_NOTIFY_CHANGE_ATTRIBUTES | win32con.FILE_NOTIFY_CHANGE_LAST_WRITE
      try:
        chs = [ win32file.FindFirstChangeNotification(str(d), 0, watches) for d in dirs ]
        while win32event.WaitForMultipleObjects(chs, 0, 1000) == win32con.WAIT_TIMEOUT: pass
      finally:
        for ch in chs: win32file.FindCloseChangeNotification(ch)
    else:
      time.sleep(10)

def sleep_inhibit():
  if os.name == 'nt':
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)

def sleep_uninhibit():
  if os.name == 'nt':
    ES_CONTINUOUS = 0x80000000
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)

def dirpath(p):
  p = pathlib.Path(p)
  if not p.exists():
    raise argparse.ArgumentTypeError(FileNotFoundError(p))
  if not p.is_dir():
    raise argparse.ArgumentTypeError(NotADirectoryError(p))
  return p

class DefDictEncoder(json.JSONEncoder):
  def default(self, obj):
    if isinstance(obj, pathlib.PurePath):
      return str(obj)
    # Let the base class default method raise the TypeError
    return super().default(self, obj)

class defdict(dict):
  '''A Dictionary which returns None on non-existing keys and tracks modified status.'''

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self._modified=False

  def __getitem__(self, key):
    if key not in self: return None
    value = super().__getitem__(key)
    if isinstance(value, str) and value !="" and (p:=pathlib.Path(value)).exists():
      value = p
    return value

  def __setitem__(self, key, value):
    '''n.b. Assigning None to a non-None value deletes it.'''

    if value is None:
      try:
        del self[key]
        self._modified = True
      except KeyError: pass
      return
    
    if isinstance(value, pathlib.PurePath):
      value = str(value)

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

def basestem(p : pathlib.Path) -> pathlib.Path:
  while True:
    o = p.with_suffix('')
    if o == p:
      return o
    p = o

