#!/usr/bin/python
# -*- coding: latin-1 -*-
# Various utility functions

import os, os.path, re, logging, logging.handlers

loggername = 'DEFAULT'

def debug(*args):
  logging.getLogger(loggername).debug(*args)

def info(*args):
  logging.getLogger(loggername).info(*args)

def warning(*args):
  logging.getLogger(loggername).warning(*args)

def error(*args):
  logging.getLogger(loggername).error(*args)

def critical(*args):
  logging.getLogger(loggername).critical(*args)

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
        
        if os.name != 'nt': return
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleA(self.format(record).encode())

def startlogging(logfile,loglevel):
  logger = logging.getLogger(loggername)
  logger.setLevel(logging.DEBUG)
  logformat = logging.Formatter('%(asctime)s [%(levelname)s]: %(message)s')
  if logfile:
    flogger=logging.handlers.WatchedFileHandler(logfile)
    flogger.setLevel(logging.DEBUG)
    flogger.setFormatter(logformat)
    logger.addHandler(flogger)
  
  tlogger=TitleHandler()
  tlogger.setLevel(logging.DEBUG)
  tlogger.setFormatter(logformat)
  logger.addHandler(tlogger)
  
  slogger=logging.StreamHandler()
  slogger.setLevel(loglevel)
  slogger.setFormatter(logformat)
  logger.addHandler(slogger)
  #logging.basicConfig(level=args.loglevel,filename=args.logfile,format='%(asctime)s [%(levelname)s]: %(message)s')
  
def nice(niceness):
  '''Nice for Windows Processes.  Nice is a value between -3-2 where 0 is normal priority.'''
  
  if os.name != 'nt': return os.nice(niceness)
  
  import win32api,win32process,win32con
  
  priorityclasses = [win32process.IDLE_PRIORITY_CLASS,
      win32process.BELOW_NORMAL_PRIORITY_CLASS,
      win32process.NORMAL_PRIORITY_CLASS,
      win32process.ABOVE_NORMAL_PRIORITY_CLASS,
      win32process.HIGH_PRIORITY_CLASS,
      win32process.REALTIME_PRIORITY_CLASS]
  pid = win32api.GetCurrentProcessId()
  handle = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, True, pid)
  if niceness<-3: win32process.SetPriorityClass(handle, priorityclasses[5])
  elif niceness>2: win32process.SetPriorityClass(handle, priorityclasses[0])
  else: win32process.SetPriorityClass(handle, priorityclasses[2-niceness])

def reglob(pat,dir='.'):
  '''A replacement for glob.glob which uses regular expressions and sorts numbers up to 10 digits correctly.'''
  
  return sorted([f if dir=='.' else os.path.join(dir,f) for f in os.listdir(dir) if re.search(r'^' + pat + r'$',f)],key=(lambda s:re.sub(r'\d+',lambda m: m.group(0).zfill(10),s)))

def secsToParts(s):
  '''Convert a number of seconds (given as float) into a tuple of (neg (string), hours (int), mins (int), secs (int), msecs (int)).'''
  
  neg = "-" if s<0 else ""
  secs, msecs= divmod(int(abs(s)*1000),1000)
  mins, secs = divmod(secs,60)
  hours, mins = divmod(mins,60)
  return (neg,hours,mins,secs,msecs)

def partsToSecs(p):
  '''Convert a tuple of (neg (string), hours (int), mins (int), secs (int), msecs (int)) into a number of seconds (given as float).'''
  
  neg,hours,mins,secs,msecs=p
  return (-1 if neg=='-' else 1)*(float(msecs)/1000+secs+(mins+hours*60)*60)

def dict_inverse(d):
  '''Create an inverse dict from a dict.'''
  
  return { v:k for k,v in d.items()}

rmat=None
def rser(p,s):
  global rmat
  m = re.search(p,s)
  if m:
    rmat=m.groups()
    return True
  else:
    rmat=None
    return False
def rget(n=None):
  global rmat
  return rmat if n==None else rmat[n]

workfile='working_on'
def workfile_set(file):
  print('Set: ' + file)
  if not file: return
  if os.path.exists(workfile):
    with open(workfile,'r') as f: ofile=f.read()
    error('New worklock "' + file + '" set while worklock still exists for "' + ofile + '"')
    os.remove(workfile)
  with open(workfile,'w') as f: f.write(file)

def workfile_unset(file):
  print('Unset: ' + file)
  if not file: return
  if os.path.exists(workfile):
    with open(workfile,'r') as f: ofile=f.read()
    if ofile!=file:
      error('Creating worklock for "' + file + '" while worklock still exists for "' + ofile + '"')
  else:
    error('Non-existing worklock unset for "' + file + '" while no old worklock exists')
  os.remove('working_on')

def workfile_clear():
  print('Clear')
  if not os.path.exists('working_on'): return False
  with open('working_on','r') as f: file=f.read()
  if '/'.find(file) == -1:
    if os.path.exists(file): os.remove(file)
  else:
    error('Attempted to clear worklock for path "' + file + '"')
  os.remove('working_on')
  return True
