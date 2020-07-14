#!/usr/bin/python
# An object to simplify using regular expression tests

import re
import os

class RegEx:
  """A class serving as front-end for the regular expression library"""

  def __init__(self, text=None, regex=None):
    self.text = text
    self.regex = regex
    if self.text and self.regex:
      self.match = re.search(self.regex,self.text)
    else:
      self.match = None

  def __call__(self, regex=None, text=None):
    if text:
      self.text = text
      self.match = None
    if regex:
      self.regex = regex
      self.match = None
    if self.text and self.regex:
      self.match = re.search(self.regex,self.text)
    return True if self.match else False

  def __str__(self):
    return ''.join(('RegEx(',self.text if self.text else '',',',self.regex if self.regex else '',')'))

  def __repr__(self):
    return ''.join(('RegEx(',repr(self.text),',',repr(self.regex),')'))

  def __bool__(self):
    return True if self.match else False

  def __getattr__(self, name):
    if not self.match:
      raise AttributeError('No valid match')
    d = self.match.groupdict()
    if not d:
      raise AttributeError('No named groups')
    return d[name]

#  def __len__(self):
#    if not self.match:
#      raise AttributeError('No valid match')
#    return len(self.match.groups())

  def __getitem__(self, key):
    if not self.match:
      raise KeyError('No valid match')
    if isinstance(key,int):
      return self.match[key+1]
    elif isinstance(key,str):
      return self.match.groupdict()[key]
    else:
      raise TypeError('Keys must be strings or integers')

#  def __setitem__(self, key):
#    raise TypeError('Cannot assign groups')
#
#  def __delitem__(self, key):
#    raise TypeError('Cannot delete groups')
