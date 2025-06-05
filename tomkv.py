#!python3
import argparse
import teletype
import glob
import logging
import logging.handlers
import pathlib
import subprocess
import os

from cetools import (
  basestem,
  lang2iso6392,
  iso6392tolang,
  iso6391to6392,
  files2quotedstring,
  sortkey,
  to_title_case,
)

prog = 'tomkv'
version = '0.4'
author = 'Carl Edman (CarlEdman@gmail.com)'
desc = 'Convert video files to mkv files (incorporating separate subtitles & posters).'

parser = None
args = None
log = logging.getLogger()

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

subexts = {
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
  '.apng': 'image/apnge',
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

posterstems = {
  'cover',
  'poster',
}

chapexts = {'.chapters', '.chapters.xml'}

findelfiles = set()
successes = []
failures = []

def doit(vidfile: pathlib.Path) -> bool:
  if vidfile.is_dir():
    if not args.recurse:
      return False
    log.debug(f'Recursing on "{vidfile}" ...')
    return max(map(doit, sorted(list(vidfile.iterdir()), key=sortkey)), default=False)

  if vidfile.suffix.lower() not in videxts or not vidfile.is_file():
    log.debug(f'"{vidfile}" is not recognized video file, skipping')
    return False

  vidstat = os.stat(vidfile)

  mkvfile = vidfile.with_suffix('.mkv')
  
  if args.titlecase:
    mkvfile = mkvfile.with_stem(to_title_case(mkvfile.stem))

  tempfile = mkvfile.with_stem(mkvfile.stem + '-temp')

  if mkvfile.exists() and not vidfile.samefile(mkvfile):
    log.warning(f'"{mkvfile}" already exists')
    failures.append(mkvfile)
    return False

  cl = ['mkvmerge', '--stop-after-video-ends', '-o', tempfile]

  if args.languages:
    cl += ['--audio-tracks', args.languages, '--subtitle-tracks', args.languages]

  cl += [vidfile]

  delfiles = set()

  todo = args.force
  todo = todo | (mkvfile != vidfile)
  todo = todo or bool(args.languages)
  
  for e in chapexts:
    chapfile = vidfile.with_suffix(e)
    if chapfile.exists():
      todo = True
      delfiles.add(chapfile)
      cl += ['--chapters', chapfile]

  for f in sorted(list(vidfile.parent.iterdir()), key=sortkey):
    # if f.is_dir() and f.name.lower() in { "sub", "subs" }:
    #   g = f / vidfile.name
    #   h = g.with_suffix(".srt")
    #   if h.exists() and h.is_file():
    #     f = h
    #   pass
    if not f.is_file():
      continue
    if f.suffix in subexts and f.stem.startswith(vidfile.stem):
      todo = True
      delfiles.add(f)
      if f.suffix in exts_skip:
        continue

      sufs = [s.lstrip('.') for s in f.suffixes]
      sufs = [t for s in sufs for t in s.split()]
      sufs = [t for s in sufs for t in s.split('_')]
      sufs = [t for s in sufs for t in s.split(',')]

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
        log.warning(f'Cannot identify language for {f}, defaulting to {iso6392}')

      name = f.stem.removeprefix(vidfile.stem).strip(' ._')
      cl += [ '--language', f'0:{iso6392}', '--track-name', f'0:{name}', f ]
      todo = True

    elif f.suffix.lower() in posterexts2mime and f.stem.lower() in posterstems:
      todo = True
      findelfiles.add(f)
      cl += [
        '--attachment-mime-type', posterexts2mime[f.suffix],
        '--attachment-description', basestem(f).stem,
        '--attachment-name', to_title_case(f.stem) if args.titlecase else f.stem,
        '--attach-file', f,
      ]

  if not todo:
    log.debug(
      f'"{mkvfile}" is already in MKV format, there are no subtitles, chapters, or posters to integrate, languages are already set, and "--force" was not set: skipping...'
    )
    return False

  log.info(files2quotedstring(cl))
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

  log.info(f'mv {files2quotedstring([tempfile, mkvfile])}')
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
      os.utime(mkvfile,
               ns=(vidstat.st_atime_ns, vidstat.st_mtime_ns))
      os.chmod(mkvfile, vidstat.st_mode)
      os.chown(mkvfile, vidstat.st_uid, vidstat.st_gid)
    except Exception as e:
      log.error(f'Failed to set ownership and permissions for "{mkvfile}", skipping: {e}')
      failures.append(vidfile)
      return False

  successes.append(vidfile)

  if vidfile.exists() and mkvfile.exists() and not vidfile.samefile(mkvfile):
    delfiles.add(vidfile)

  if args.nodelete or mkvmerge_warning or not delfiles:
    return True

  log.info(f'rm {files2quotedstring(delfiles)}')
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
  parser.add_argument(
    '-d',
    '--dryrun',
    dest='dryrun',
    action='store_true',
    help='do not perform operations, but only print them.',
  )
  parser.add_argument('--version', action='version', version='%(prog)s ' + version)
  parser.add_argument(
    '--verbose',
    dest='loglevel',
    action='store_const',
    const=logging.INFO,
    help='print informational (or higher) log messages.',
  )
  parser.add_argument(
    '--debug',
    dest='loglevel',
    action='store_const',
    const=logging.DEBUG,
    help='print debugging (or higher) log messages.',
  )
  parser.add_argument(
    '--taciturn',
    dest='loglevel',
    action='store_const',
    const=logging.ERROR,
    help='only print error level (or higher) log messages.',
  )
  parser.add_argument(
    '--log', dest='logfile', action='store', help='location of alternate log file.'
  )
  parser.add_argument(
    'paths', nargs='+', help='paths to be operated on; may include wildcards (if glob is set); directories convert content (if recurse is set).'
  )
  parser.set_defaults(loglevel=logging.WARN)

  args = parser.parse_args()
  if args.dryrun and args.loglevel > logging.INFO:
    args.loglevel = logging.INFO

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

#  c = curses.initscr()
#  print(c)

  ps = args.paths
  if args.glob:
    ps = ( f for p in ps for f in glob.iglob(p) )
  ps = map(pathlib.Path, ps)
  if not max(map(doit, ps), default=False):
    log.warning(f'No valid video files found for paths (need to glob and/or recurse?) arguments: {' '.join(args.paths)}')

  if not args.nodelete and findelfiles:
    log.info(f'rm {files2quotedstring(findelfiles)}')
    if not args.dryrun:
      for i in findelfiles:
        if i.exists():
          i.unlink()
