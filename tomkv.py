#!/usr/bin/python3
import argparse
import glob
import logging
import logging.handlers
import pathlib
import subprocess

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
version = '0.2'
author = 'Carl Edman (CarlEdman@gmail.com)'
desc = 'Convert video files to mkv files (incorporating separate subtitles).'

parser = None
args = None
log = logging.getLogger()

videxts = {
  '.mp4',
  '.mkv',
  '.avi',
  '.mpg',
  '.m4v',
  '.mp3',
}

subexts = {
  '.srt',
  '.idx',
  '.ass',
  '.sub',
  '.sup',
}

subexts_bad = {
  '.sub',
}


def tomkv(vidfile: pathlib.Path):
  if vidfile.suffix not in videxts or not vidfile.is_file():
    log.warning(f'"{vidfile}" is not recognized video file, skipping')
    return
  mkvfile = vidfile.with_suffix('.mkv')
  if args.titlecase:
    mkvfile = mkvfile.with_stem(to_title_case(mkvfile.stem))

  tempfile = mkvfile.with_stem(mkvfile.stem + '-temp')

  if vidfile != mkvfile and mkvfile.exists():
    log.warning(f'"{mkvfile}" exists')
    return
  subfiles = []
  for subfile in vidfile.parent.iterdir():
    if not subfile.is_file():
      continue
    if subfile.suffix not in subexts:
      continue
    if subfile.suffix in subexts_bad:
      log.warning(
        f'"{subfile}" not in recognized subtitle format.  Try to convert to, e.g., srt using, e.g., https://subtitletools.com/).'
      )
      continue
    if basestem(subfile) != basestem(vidfile):
      continue
    subfiles.append(subfile)

  if vidfile == mkvfile and not subfiles:
    log.warning(
      f'"{mkvfile}" is already in MKV format and there are no subtitles to integrate, skipping.'
    )
    return

  cl = [
    'mkvmerge',
    '--stop-after-video-ends',
    '-o', 
    str(tempfile),
  ]

  if args.striplang:
    cl += [
      '-a',
      args.striplang,
      '-s',
      args.striplang,
    ]

  cl += [str(vidfile)]
  for subfile in sorted(subfiles, key=sortkey):
    suffixes = [s.lstrip('.') for s in subfile.suffixes]
    suffixes = [t for s in suffixes for t in s.split()]
    suffixes = [t for s in suffixes for t in s.split('_')]
    suffixes = [t for s in suffixes for t in s.split(',')]

    iso6392 = None
    for s in suffixes:
      if s in iso6392tolang:
        iso6392 = s
      elif s in iso6391to6392:
        iso6392 = iso6391to6392[s]
      elif s in lang2iso6392:
        iso6392 = lang2iso6392[s]

    if not iso6392:
      iso6392 = "eng"
      log.warning(f'Cannot identify language for {subfile}, defaulting to {iso6392}')

    cl += ['--language', f'0:{iso6392}', str(subfile)]

  log.info(files2quotedstring(cl))
  if not args.dryrun:
    try:
      subprocess.run(cl, check=True, capture_output=True, text=True)
    except KeyboardInterrupt as e:
      log.error(f'{e} Interrupted ...')
      tempfile.unlink(missing_ok=True)
      log.error(f'{e}\nSkipping ...')
    except subprocess.CalledProcessError as e:
      log.error(f'{e}\nMoving on ...')
      return

  log.info(f'mv {files2quotedstring([tempfile, mkvfile])}')
  if not args.dryrun:
    tempfile.replace(mkvfile)

  if args.nodelete:
    return

  log.info(f'rm {files2quotedstring([vidfile])}')
  if not args.dryrun:
    vidfile.unlink()

  if subfiles:
    log.info(f'rm {files2quotedstring(subfiles)}')
    for s in subfiles:
      if not args.dryrun:
        s.unlink()

if __name__ == '__main__':
  parser = argparse.ArgumentParser(
    fromfile_prefix_chars='@', prog=prog, epilog='Written by: ' + author
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
    '--dryrun',
    dest='dryrun',
    action='store_true',
    help='do not perform operations, but only print them.',
  )
  parser.add_argument(
    '--no-delete',
    dest='nodelete',
    action='store_true',
    help='do not delete source files (video and subtitles) after conversion to MKV.',
  )
  parser.add_argument(
    '--title-case',
    dest='titlecase',
    action='store_true',
    help='rename files to proper title case.',
  )
  parser.add_argument(
    '--strip-lang',
    dest='striplang',
    action='store',
    help='Remove audio and subtitle tracks in the given language ISO639-2 code.',
  )
  parser.add_argument(
    'paths', nargs='+', help='paths to be operated on; may include wildcards.'
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

  ig = [pathlib.Path(d) for gd in args.paths for d in glob.iglob(gd)]
  if len(ig) == 0:
    log.warning(f'No paths matching {args.paths}, skipping.')
    exit()

  for d in ig:
    tomkv(d)
