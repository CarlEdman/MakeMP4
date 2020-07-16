#!/usr/bin/python
# Various utility functions

import os
import os.path
import time
import re
import logging
import logging.handlers

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

def reglob(pat):
  '''A replacement for glob.glob which uses regular expressions and sorts numbers up to 10 digits correctly.'''
  (dir, filepat) = os.path.split(pat)
  if os.name == 'nt': filepat = r'(?i)' + filepat
  files = (os.path.join(dir,f) for f in os.listdir(dir) if re.fullmatch(filepat, f))
  return sorted(files, key=sortkey)

def sanitize_filename(s):
  trans = str.maketrans('','',r':"/\:*?<>|'+r"'")
  return s.translate(trans)

def parse_time(s):
  m = re.fullmatch(r'(?P<neg>-)?(?=(?P<hrs>\d+):)?(?=(?P<mins>\d+):)?(?P<secs>\d+(\.\d*)?)', s)
  if not m: return m
  t =         float(m['secs'])
  t +=   60.0*float(m['mins']) if 'mins' in m else 0
  t += 3600.0*float(m['hrs']) if 'hrs' in m else 0
  if neg in m: t = -t
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
    warning('File "' + file + '" already worklocked')
    return False
  open(file+worklock,'w').truncate(0)
  return True

def work_unlock(file):
  if not file:
    return False
  if not os.path.exists(file+worklock):
    warning('File "' + file + '" not worklocked')
    return False
  if os.path.getsize(file+worklock) != 0:
    error('Worklock for "' + file + '" not empty!')
    return False
  os.remove(file+worklock)

def work_locked(file):
  return os.path.exists(file+worklock)

def work_lock_delete():
  for l in os.listdir(os.getcwd()):
    if not l.endswith(worklock): continue
    if os.path.getsize(l) != 0:
       error('Worklock for "' + file + '" not empty!')
       continue
    os.remove(l)
    f = l[:-len(worklock)]
    if not os.path.exists(f):
      warning('No file existed for worklock "' + l + '"')
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
