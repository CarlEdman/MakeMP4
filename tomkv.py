#! python3
import argparse
import glob
import logging
import logging.handlers
import pathlib
import pwd
import subprocess
import os
import shutil
import sys
import textwrap

from cetools import (
  basestem,
  lang2iso6392,
  iso6392tolang,
  iso6391to6392,
  path2quotedstring,
  paths2quotedstring,
  sortkey,
  to_title_case,
)

prog = 'tomkv'
version = '0.6'
author = 'Carl Edman (CarlEdman@gmail.com)'
desc = 'Convert video files to mkv files (incorporating separate subtitles, chapters & posters).'

(cols, lines) = shutil.get_terminal_size(fallback=(0,0))
parser = None
args = None
log = logging.getLogger(__name__)

try:
  import coloredlogs
  coloredlogs.install(logger=log)
except ImportError:
  pass

videxts = {
  '.264',
  '.265',
  '.avi',
  '.divx',
  '.flv',
  '.h264',
  '.h265',
  '.m4v',
  '.mkv',
  '.mov',
  '.mp4',
  '.mpg',
  '.smi',
  '.ts',
  '.webm',
  '.wmv'
}

exts_sub = {
  '.ass',
  '.idx',
  '.srt',
  '.sup',
  '.vtt',
}

exts_skip = {
  '.sub',
}

posterexts2mime = {
  '.apng': 'image/apng',
  '.avif': 'image/avif',
  '.bmp': 'image/bmp',
  '.emf': 'image/emf',
  '.gif': 'image/gif',
  '.heic': 'image/heic',
  '.heif': 'image/heif',
  '.jpeg': 'image/jpeg',
  '.jpg': 'image/jpeg',
  '.png': 'image/png',
  '.svg': 'image/svg',
  '.svg+xml': 'image/svg+xml',
  '.tiff': 'image/tiff',
  '.webp': 'image/webp',
  '.wmf': 'image/wmf',
}

stems_poster = {
  'cover',
  'poster',
}

exts_chapter = {
  '.chapters',
  '.chapters.xml'
}

findelfiles = set()
successes = []
failures = []
modemask = 0o7777

def octal_type(x):
  return int(x, 8)

def uid_type(x):
  try:
    return pwd.getpwnam(x).pw_uid
  except KeyError:
    pass

  try:
    return int(x)
  except KeyError:
    pass

  log.warning(f'No uid recognized for "{x}", not setting.')
  return None

def gid_type(x):
  try:
    return pwd.getpwnam(x).pw_gid
  except KeyError:
    pass

  try:
    return int(x)
  except KeyError:
    pass

  log.warning(f'No gid recognized for "{x}", not setting.')
  return None

def set_stat(f: pathlib.Path) -> bool:
  if os.name == 'nt':
    return True
  if not f.exists():
    log.debug(f'"{f}" does not exists, skipping')
    return False

  s = f.stat()

  mode = s.st_mode
  if f.is_file() and args.file_mode is not None:
    mode = args.file_mode
  elif f.is_dir() and args.dir_mode is not None:
    mode = args.dir_mode
  if (s.st_mode & modemask) != (mode & modemask):
    log.info(f'Changing "{f}" mode from {oct(s.st_mode)} to {oct(mode)}.')
    f.chmod(mode)

  uid = args.uid or s.st_uid
  gid = args.gid or s.st_gid
  if s.st_uid != uid or s.st_gid != gid:
    log.info(f'Changing "{f}" owner:group from {s.st_uid}:{s.st_gid} to {uid}:{gid}.')
    os.chown(f, uid, gid)

  return True

def doit(vidfile: pathlib.Path) -> bool:
  todo = args.force
  vidname = path2quotedstring(vidfile)
  if cols>0:
    # print('\r', ansi.cursor.erase_line, textwrap.shorten(vidname, width=cols-1, placeholder='\u2026'), end='')
    # print('\r', '\033[0K', end='')
    # print('\r', '\033[0K', end='')
    print('\033[s', '\033[0K', textwrap.shorten(vidname, width=cols-10, placeholder='\u2026'), '\033[u', end='\r')

#    enter_am_mode
#    clr_eol
#    exit_am_mode

#    print('\033[?7l','\033[0K', textwrap.shorten(vidname, width=cols-10, placeholder='\u2026'), '\033[u', end='\r')

  if not vidfile.exists():
    log.debug(f'{vidname} does not exists, skipping')
    return False

  vidstat = vidfile.stat()
  set_stat(vidfile)

  if vidfile.is_dir():
    set_stat(vidfile)
    if not args.recurse:
      return False
    log.debug(f'Recursing on {vidname} ...')
    return max(map(doit, sorted(list(vidfile.iterdir()), key=sortkey)), default=False)

  if not vidfile.is_file() or vidfile.suffix.lower() not in videxts:
    log.debug(f'{vidname} is not recognized video file, skipping')
    return False

  mkvfile = vidfile.with_suffix('.mkv')
  if args.titlecase:
    mkvfile = mkvfile.with_stem(to_title_case(mkvfile.stem))
  tempfile = mkvfile.with_stem(mkvfile.stem + '-temp')

  if mkvfile.exists() and not vidfile.samefile(mkvfile):
    mkvname = path2quotedstring(mkvfile)
    log.warning(f'{mkvname} already exists')
    failures.append(mkvfile)
    return False

  cl = ['mkvmerge', '--stop-after-video-ends', '-o', tempfile]

  if args.languages:
    cl += ['--audio-tracks', args.languages, '--subtitle-tracks', args.languages]

  cl += [vidfile]

  delfiles = set()

  todo |= mkvfile != vidfile
  todo |= bool(args.languages)

  sibs = sorted(list(vidfile.parent.iterdir()), key=sortkey)

  chaps = []
  chaps += [
    f for f in sibs
    if f.suffix in exts_chapter and f.startswith(vidfile.stem)
  ]

  todo |= len(chaps) > 0
  for c in chaps:
    delfiles.add(c)
    cl += ['--chapters', c]

  subs = []
  subs += [
    f
    for f in sibs
    if f.is_file() and f.suffix in exts_sub and f.startswith(vidfile.stem)
  ]
  subs += [
    f
    for s in sibs
    if s.is_dir() and s.name.lower() in {'sub', 'subs'}
    for t in s.iterdir()
    if t.is_dir() and t.name.startswith(vidfile.stem)
    for f in t.iterdir()
    if f.suffix in exts_sub
  ]
  subs += [
    f
    for s in sibs
    if s.is_dir() and s.name.lower() in {'sub', 'subs'}
    for f in s.iterdir()
    if f.is_file()
  ]

  todo |= len(subs) > 0
  for t in subs:
    delfiles.add(t)
    if t.suffix in exts_skip:
      continue

    sufs = (s.lstrip('.') for s in t.suffixes)
    sufs = (t for s in sufs for t in s.split())
    sufs = (t for s in sufs for t in s.split('_'))
    sufs = (t for s in sufs for t in s.split(','))

    iso6392 = None
    logging.debug(sufs)
    for s in sufs:
      if s in iso6392tolang:
        iso6392 = s
      elif s in iso6391to6392:
        iso6392 = iso6391to6392[s]
      elif s in lang2iso6392:
        iso6392 = lang2iso6392[s]
      logging.debug(f'{s} -> {iso6392}')

    if not iso6392:
      iso6392 = args.default_language
      log.warning(f'Cannot identify language for {t}, defaulting to {iso6392}')

    name = t.stem.removeprefix(vidfile.stem).strip(' ._')
    cl += ['--language', f'0:{iso6392}', '--track-name', f'0:{name}', t]

  posters = []
  posters += [ f
    for f in sibs if f.suffix.lower() in posterexts2mime and f.stem.lower() in stems_poster
  ]

  todo |= len(posters) > 0
  for f in posters:
    findelfiles.add(f)
    cl += [
      '--attachment-mime-type', posterexts2mime[f.suffix],
      '--attachment-description', basestem(f).stem,
      '--attachment-name', to_title_case(f.stem) if args.titlecase else f.stem,
      '--attach-file', f,
    ]

  if not todo:
    log.warning(
      f'"{mkvfile}" is already in MKV format, there are no subtitles, chapters, or posters to integrate, languages are already set, and "--force" was not set: skipping...'
    )
    return False

  log.info(paths2quotedstring(cl))
  mkvmerge_warning = False
  if not args.dryrun:
    try:
      subprocess.run(list(map(str, cl)),
                     check=True,
                     capture_output=True,
                     text=True)
    except subprocess.CalledProcessError as e:
      if e.returncode == 1:
        log.info(e.stdout)
        log.warning(f'{e.stderr}\n{e}\nProceeding and preserving files ...')
        mkvmerge_warning = True
        failures.append(vidfile)
      else:
        if tempfile.exists():
          tempfile.unlink(missing_ok=True)
        log.info(e.stdout)
        log.error(f'{e.stderr}\n{e}\nSkipping ...')
        failures.append(vidfile)
        return False
    except KeyboardInterrupt as e:
      failures.append(vidfile)
      if tempfile.exists():
        tempfile.unlink(missing_ok=True)
      raise e

  log.info(f'mv {path2quotedstring(tempfile)} {path2quotedstring(mkvfile)}')
  if not args.dryrun:
    if mkvmerge_warning:
      backupfile = mkvfile.with_stem(mkvfile.stem + '-backup')
      try:
        mkvfile.rename(backupfile)
      except FileNotFoundError as e:
        log.error(f'Temp mkvfile "{mkvfile}" not found, skipping: {e}')
        failures.append(vidfile)
        return False

    tempfile.replace(mkvfile)
    try:
      os.utime(mkvfile, ns=(vidstat.st_atime_ns, vidstat.st_mtime_ns))
      mkvfile.chmod(vidstat.st_mode)
    except Exception as e:
      log.error(f'Failed to set ownership and permissions for "{mkvfile}", skipping: {e}')
      failures.append(vidfile)
      return False

  successes.append(vidfile)

  if vidfile.exists() and mkvfile.exists() and not vidfile.samefile(mkvfile):
    delfiles.add(vidfile)

  if args.nodelete or mkvmerge_warning or not delfiles:
    return True

  log.info(f'rm {paths2quotedstring(delfiles)}')
  if not args.dryrun:
    for i in delfiles:
      i.unlink(missing_ok=True)

  return True


if __name__ == '__main__':
  parser = argparse.ArgumentParser(
    fromfile_prefix_chars='@', prog=prog, epilog='Written by: ' + author
  )
  parser.add_argument(
    '-n',
    '--no-delete',
    dest='nodelete',
    action='store_true',
    help='do not delete source files (e.g., video, subtitles, chapters, or posters) after conversion to MKV.',
  )
  parser.add_argument(
    '-t',
    '--title-case',
    dest='titlecase',
    action='store_true',
    help='rename files to proper title case.',
  )
  parser.add_argument(
    '-f',
    '--force',
    dest='force',
    action='store_true',
    help='force remuxing without any apparent need.',
  )
  parser.add_argument(
    '-l',
    '--languages',
    dest='languages',
    action='store',
    help='keep audio and subtitle tracks in the given language ISO639-2 codes; prefix with ! to discard same.',
  )
  parser.add_argument(
    '--uid',
    dest='uid',
    type=uid_type,
    action='store',
    default=None,
    help='if set, vidfiles will have their uid changed.',
  )
  parser.add_argument(
    '--gid',
    dest='gid',
    type=gid_type,
    action='store',
    default=None,
    help='if set, vidfiles will have their gid changed.',
  )
  parser.add_argument(
    '--file-mode',
    dest='file_mode',
    type=octal_type,
    action='store',
    default=None,
    help='if set, vidfiles mode will be changed.',
  )
  parser.add_argument(
    '--dir-mode',
    '--directory-mode',
    dest='dir_mode',
    type=octal_type,
    action='store',
    default=None,
    help='if set, folders mode will be changed.',
  )
  parser.add_argument(
    '--default-language',
    dest='default_language',
    action='store',
    default='eng',
    choices=iso6392tolang.keys(),
    help='ISO6392 language code to use by default for subtitles.',
  )
  parser.add_argument(
    '-R',
    '--recurse',
    dest='recurse',
    action=argparse.BooleanOptionalAction,
    default=False,
    help='Recurse into subdirectories.',
  )
  parser.add_argument(
    '-G',
    '--glob',
    dest='glob',
    action=argparse.BooleanOptionalAction,
    default=False,
    help='Glob argument paths.',
  )
  parser.add_argument('-d', '--dryrun',
    dest='dryrun',
    action='store_true',
    help='do not perform operations, but only print them.')
  parser.add_argument('--version',
    action='version',
    version='%(prog)s ' + version)
  parser.add_argument('--verbose',
    dest='loglevel',
    action='store_const',
    const=logging.INFO,
    help='print informational (or higher) log messages.')
  parser.add_argument('--debug',
    dest='loglevel',
    action='store_const',
    const=logging.DEBUG,
    help='print debugging (or higher) log messages.')
  parser.add_argument('--taciturn',
    dest='loglevel',
    action='store_const',
    const=logging.ERROR,
    help='only print error level (or higher) log messages.')
  parser.add_argument('--log',
    dest='logfile',
    action='store', 
    help='location of alternate log file.')
  parser.add_argument(
    'paths', nargs='+', help='paths to be operated on; may include wildcards (if glob is set); directories convert content (if recurse is set).'
  )

  parser.set_defaults(loglevel=logging.WARN)
  for i in [
    (pathlib.Path.home() / '.config' / prog).with_suffix('.ini'),
    pathlib.Path(sys.argv[0]).with_suffix('.ini'),
    pathlib.Path(prog).with_suffix('.ini'),
    (pathlib.Path('..') / prog).with_suffix('.ini'),
  ]:
    if not i.exists():
      continue
    sys.argv.insert(1, f'@{i}')

  logging.addLevelName(logging.WARNING, "\033[1;31m%s\033[1;0m" % logging.getLevelName(logging.WARNING))
  logging.addLevelName(logging.ERROR, "\033[1;41m%s\033[1;0m" % logging.getLevelName(logging.ERROR))

  args = parser.parse_args()
  if args.dryrun and args.loglevel > logging.INFO:
    args.loglevel = logging.INFO

  print(args.loglevel)
  log.setLevel(0)
  logformat = logging.Formatter('%(asctime)s [%(levelname)s]: %(message)s')

  if args.logfile:
    flogger = logging.handlers.WatchedFileHandler(args.logfile, 'a', 'utf-8')
    flogger.setLevel(logging.DEBUG)
    flogger.setFormatter(logformat)
    log.addHandler(flogger)

  slogger = logging.StreamHandler()
  slogger.setLevel(args.loglevel)
  slogger.setFormatter(logformat)
  log.addHandler(slogger)

  ps = args.paths
  if args.glob:
    ps = ( f for p in ps for f in glob.iglob(p) )
  ps = map(pathlib.Path, ps)
  if not max(map(doit, ps), default=False):
    log.warning(f'No valid video files found for paths (need to glob and/or recurse?) arguments: {paths2quotedstring(ps)}')

  if not args.nodelete and findelfiles:
    log.info(f'rm {paths2quotedstring(findelfiles)}')
    if not args.dryrun:
      for i in findelfiles:
        if i.exists():
          i.unlink()
