#! python3
import argparse
import glob
import logging
import pathlib
import pwd
import subprocess
import os
import shutil
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
version = '0.7'
author = 'Carl Edman (CarlEdman@gmail.com)'
desc = 'Convert video files to mkv files (incorporating separate subtitles, chapters & posters).'

(cols, lines) = shutil.get_terminal_size(fallback=(0,0))
args = None
logger = None

try:
  import coloredlogs
except ImportError:
  coloredlogs = None

exts_vid = {
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
  '.xml',
  '.chapters',
  '.chapters.xml'
}

log_colors = {
  logging.DEBUG: '37;44',
  logging.INFO: '47;34',
  logging.WARNING: '30;91',
  logging.ERROR: '47;31',
  logging.CRITICAL: '37;41',
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

  logger.warning(f'No uid recognized for "{x}", not setting.')
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

  logger.warning(f'No gid recognized for "{x}", not setting.')
  return None

def set_stat(f: pathlib.Path) -> bool:
  # if os.name == 'nt':
  #   return True
  if not f.exists():
    logger.debug(f'"{f}" does not exists, skipping')
    return False

  s = f.stat()

  mode = s.st_mode
  if f.is_file() and args.file_mode is not None:
    mode = args.file_mode
  elif f.is_dir() and args.dir_mode is not None:
    mode = args.dir_mode
  if (s.st_mode & modemask) != (mode & modemask):
    logger.info(f'Changing "{f}" mode from {oct(s.st_mode)} to {oct(mode)}.')
    f.chmod(mode)

  uid = args.uid or s.st_uid
  gid = args.gid or s.st_gid
  if s.st_uid != uid or s.st_gid != gid:
    logger.info(f'Changing "{f}" owner:group from {s.st_uid}:{s.st_gid} to {uid}:{gid}.')
    os.chown(f, uid, gid)

  return True

def updel(f: pathlib.Path) -> None:
  try:
    f.unlink()
  except Exception:
    return

  for p in f.parents:
    try:
      p.rmdir()
    except Exception:
      return

def doit(vidfile: pathlib.Path) -> bool:
  todo = args.force
  vidname = path2quotedstring(vidfile)
  backup_vidfile = False
  if args.monitor and cols>0:
    print('\033[s', '\033[0K', textwrap.shorten(str(vidfile), width=cols-10, placeholder='\u2026'), '\033[u', end='\r')

  if not vidfile.exists():
    logger.debug(f'{vidname} does not exists, skipping...')
    return False

  vidstat = vidfile.stat()
  set_stat(vidfile)

  if vidfile.is_dir():
    set_stat(vidfile)
    if not args.recurse:
      return False
    logger.debug(f'Recursing on {vidname} ...')
    return max(map(doit, sorted(list(vidfile.iterdir()), key=sortkey)), default=False)

  if not vidfile.is_file() or vidfile.suffix.lower() not in exts_vid:
    logger.debug(f'{vidname} is not recognized video file, skipping')
    return False

  mkvfile = vidfile.with_suffix('.mkv')
  if args.titlecase:
    mkvfile = mkvfile.with_stem(to_title_case(mkvfile.stem))
  tempfile = mkvfile.with_stem(mkvfile.stem + '-temp')
  if tempfile.exists():
    logger.warning(f'{tempfile} already exists')
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
    if f.suffix in exts_chapter and f.name.startswith(vidfile.stem)
  ]

  todo |= len(chaps) > 0
  for c in chaps:
    delfiles.add(c)
    cl += ['--chapters', c]

  subs = []
  subs += [
    f
    for f in sibs
    if f.is_file() and f.suffix in exts_sub and f.name.startswith(vidfile.stem)
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

    sufs = [s3
      for s1 in t.name.split('.')
      for s2 in s1.split('_')
      for s3 in s2.split(',')
    ]

    iso6392 = None
    logger.debug(t, sufs)
    for s in sufs:
      if s in iso6392tolang:
        iso6392 = s
      elif s in iso6391to6392:
        iso6392 = iso6391to6392[s]
      elif s in lang2iso6392:
        iso6392 = lang2iso6392[s]
      logger.debug(f'{s} -> {iso6392}')

    if not iso6392:
      iso6392 = args.default_language
      logger.warning(f'Cannot identify language for {t}, defaulting to {iso6392}')

    cl += ['--language', f'0:{iso6392}', '--track-name', f'0:{t.stem.removeprefix(vidfile.stem).strip(" ._")}', t]

  posters = [f for f in sibs if f.suffix.lower() in posterexts2mime and f.stem.lower() in stems_poster]

  for f in posters:
    todo = True
    findelfiles.add(f)
    cl += [
      '--attachment-mime-type', posterexts2mime[f.suffix],
      '--attachment-description', basestem(f).stem,
      '--attachment-name', to_title_case(f.stem) if args.titlecase else f.stem,
      '--attach-file', f,
    ]

  if not todo:
    logger.debug(
      f'"{mkvfile}" is already in MKV format, there are no subtitles, chapters, or posters to integrate, languages are already set, and "--force" was not set: skipping...'
    )
    return True

  logger.info(paths2quotedstring(cl))
  if not args.dryrun:
    try:
      subprocess.run(list(map(str, cl)),
                     check=True,
                     capture_output=True,
                     text=True)
    except subprocess.CalledProcessError as e:
      logger.info(f'{e.stdout}\n{e.stderr}\n{e}\n')
      backup_vidfile = True
      failures.append(vidfile)
      if e.returncode == 0:
        logger.warning('Error raised, but returncode == 0 ...')
      elif e.returncode == 1:
        if args.overwrite:
          logger.warning('Proceeding, backing up, and overwriting source file ...')
        else:
          logger.warning('Proceeding and preserving files ...')
      else:
        updel(tempfile)
        logger.error('Skipping ...')
        return False
    except KeyboardInterrupt as e:
      failures.append(vidfile)
      updel(tempfile)
      raise e

  if backup_vidfile:
    backupfile = vidfile.with_suffix('.bak' + vidfile.suffix)
    logger.info(f'mv {path2quotedstring(vidfile)} {path2quotedstring(backupfile)}')
    if not args.dryrun:
      try:
        vidfile = vidfile.rename(backupfile)
      except FileNotFoundError as e:
        logger.error(f'Original file "{vidfile}" not found, skipping: {e}')
        failures.append(mkvfile)
        return False

  logger.info(f'mv {path2quotedstring(tempfile)} {path2quotedstring(mkvfile)}')
  if not args.dryrun:
    tempfile.replace(mkvfile)

  try:
    if not args.dryrun:
      os.utime(mkvfile, ns=(vidstat.st_atime_ns, vidstat.st_mtime_ns))
      mkvfile.chmod(vidstat.st_mode)
  except Exception as e:
    logger.error(f'Failed to set ownership and permissions for "{mkvfile}", skipping: {e}')
    failures.append(vidfile)
    return False

  successes.append(vidfile)

  if vidfile.exists() and mkvfile.exists() and not vidfile.samefile(mkvfile) and not backup_vidfile:
    delfiles.add(vidfile)

  if args.nodelete or backup_vidfile or not delfiles:
    return True

  logger.info(f'rm {paths2quotedstring(delfiles)}')
  if not args.dryrun:
    for i in delfiles:
      updel(i)

  return True


if __name__ == '__main__':
  parser = argparse.ArgumentParser(
    fromfile_prefix_chars='@', prog=prog, epilog='Written by: ' + author)
  parser.add_argument(
    '-n',
    '--no-delete',
    dest='nodelete',
    action='store_true',
    help='do not delete source files (e.g., video, subtitles, chapters, or posters) after conversion to MKV.')
  parser.add_argument(
    '-t',
    '--title-case',
    dest='titlecase',
    action='store_true',
    help='rename files to proper title case.')
  parser.add_argument(
    '-f',
    '--force',
    dest='force',
    action='store_true',
    help='force remuxing without any apparent need.')
  parser.add_argument(
    '-l',
    '--languages',
    dest='languages',
    action='store',
    help='keep only audio and subtitle tracks in the given language ISO639-2 codes; prefix with ! to discard only these.')
  parser.add_argument(
    '--uid',
    dest='uid',
    type=uid_type,
    action='store',
    default=None,
    help='if set, vidfiles will have their uid changed.')
  parser.add_argument(
    '--gid',
    dest='gid',
    type=gid_type,
    action='store',
    default=None,
    help='if set, vidfiles will have their gid changed.')
  parser.add_argument(
    '--file-mode',
    dest='file_mode',
    type=octal_type,
    action='store',
    default=None,
    help='if set, vidfiles mode will be changed.')
  parser.add_argument(
    '--dir-mode',
    '--directory-mode',
    dest='dir_mode',
    type=octal_type,
    action='store',
    default=None,
    help='if set, folders mode will be changed.')
  parser.add_argument(
    '--default-language',
    dest='default_language',
    action='store',
    default='eng',
    choices=iso6392tolang.keys(),
    help='ISO6392 language code to use by default for subtitles.')
  parser.add_argument(
    '-R',
    '--recurse',
    dest='recurse',
    action=argparse.BooleanOptionalAction,
    default=False,
    help='recurse into subdirectories of arguments.')
  parser.add_argument(
    '-M', '--monitor',
    dest='monitor',
    action=argparse.BooleanOptionalAction,
    default=False,
    help='print paths as they are examined.')
  parser.add_argument(
    '-O', '--overwrite',
    dest='overwrite',
    action=argparse.BooleanOptionalAction,
    default=False,
    help='If there is an error in remuxing, nevertheless replace the original and rename it to *.bak.')
  parser.add_argument('-d', '--dryrun', '--dry-run',
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
  parser.add_argument(
    'paths',
    nargs='+',
    type=pathlib.Path,
    help='paths to be operated on.')
  parser.set_defaults(loglevel=logging.WARN)

  for level, color in log_colors.items():
    logging.addLevelName(
      level, f'\x1b[{color}m{logging.getLevelName(level)}'
    )

  args = parser.parse_args()
  if args.dryrun and args.loglevel > logging.INFO:
    args.loglevel = logging.INFO
  logger = logging.getLogger(__name__)
  if args.overwrite and args.nodelete:
    logger.warning('--overwrite and --no-delete flags are incompatible, yet both are set.')

  if coloredlogs:
    coloredlogs.install(level=args.loglevel,
      fmt='%(asctime)s %(levelname)s: %(message)s')
  else:
    logging.basicConfig(level=args.loglevel,
      format='%(asctime)s %(levelname)s: %(message)s\x1b[1;0m' )

  if not max(map(doit, args.paths), default=False):
    logger.warning(f'No valid video files found for paths{" (need to recurse?)" if not args.recurse else ""} arguments: {", ".join(map(str, args.paths))}')

  if args.monitor and cols>0:
    print('\033[s', '\033[0K', '\033[u', end='\r')

  if not args.nodelete and findelfiles:
    logger.info(f'rm {paths2quotedstring(findelfiles)}')
    if not args.dryrun:
      for i in findelfiles:
        updel(i)

  if failures:
    w = '\n'.join([ "Encountered issues with:" ] + [ f'    {f}' for f in failures ] )
    logger.warning(w)
    exit(1)

  exit(0)
