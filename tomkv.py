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
version = '0.3'
author = 'Carl Edman (CarlEdman@gmail.com)'
desc = 'Convert video files to mkv files (incorporating separate subtitles).'

parser = None
args = None
log = logging.getLogger()

videxts = {
  '.avi',
  '.m4v',
  '.mkv',
  '.mp3',
  '.mp4',
  '.mpg',
  '.ts',
}

subexts = {
  '.ass',
  '.idx',
  '.srt',
  '.sub',
  '.sup',
}

subexts_skip = {
  '.sub',
}

posterexts2mime = {
  'apng': 'image/apnge/',
  'avif': 'image/avif',
  'bmp': 'image/bmp',
  'emf': 'image/emf',
  'gif': 'image/gif',
  'heic': 'image/heic',
  'heif': 'image/heif',
  'jpeg': 'image/jpeg',
  'png': 'image/png',
  'svg+xml': 'image/svg+xml',
  'tiff': 'image/tiff',
  'webp': 'image/webp',
  'wmf': 'image/wmf',
}

posternames = {
  'cover',
  'poster',
  '',
}


def doit(vidfile: pathlib.Path):
  if vidfile.suffix not in videxts or not vidfile.is_file():
    log.warning(f'"{vidfile}" is not recognized video file, skipping')
    return
  mkvfile = vidfile.with_suffix('.mkv')
  if args.titlecase:
    mkvfile = mkvfile.with_stem(to_title_case(mkvfile.stem))

  tempfile = mkvfile.with_stem(mkvfile.stem + '-temp')

  if mkvfile.exists() and not vidfile.samefile(mkvfile):
    log.warning(f'"{mkvfile}" already exists')
  if mkvfile.exists() and not vidfile.samefile(mkvfile):
    log.warning(f'"{mkvfile}" already exists')
    return

  cl = ['mkvmerge', '--stop-after-video-ends', '-o', tempfile]

  if args.languages:
    cl += ['--audio-tracks', args.languages, '--subtitle-tracks', args.languages]

  cl += [vidfile]

  intfiles = []
  for f in sorted(list(vidfile.parent.iterdir()), key=sortkey):
    if not f.is_file():
      continue
    if f.suffix in subexts and basestem(f) == basestem(vidfile):
      intfiles.append(f)
      if f.suffix in subexts_skip:
        # log.warning(
        #   f'"{subfile}" not in recognized subtitle format.  Try to convert to, e.g., srt using, e.g., https://subtitletools.com/).'
        # )
        continue

      sufs = [s.lstrip('.') for s in f.suffixes]
      sufs = [t for s in sufs for t in s.split()]
      sufs = [t for s in sufs for t in s.split('_')]
      sufs = [t for s in sufs for t in s.split(',')]

      iso6392 = None
      for s in sufs:
        if s in iso6392tolang:
          iso6392 = s
        elif s in iso6391to6392:
          iso6392 = iso6391to6392[s]
        elif s in lang2iso6392:
          iso6392 = lang2iso6392[s]

      if not iso6392:
        iso6392 = args.default_language
        log.warning(f'Cannot identify language for {f}, defaulting to {iso6392}')

      cl += ['--language', f'0:{iso6392}', f]

      # elif f.suffix in posterexts2mime and basestem(f) == basestem(vidfile):
      # intfiles.append(f)
      #   cl += [
      #     '--attachment-mime-type', posterexts2mime[f.suffix],
      #     '--attachment-description', f,
      #     '--attachment-name', to_title_case(f.stem) if args.titlecase else f.stem,
      #     '--attach-file', f,
      #   ]

  if mkvfile.exists() and not intfiles and not args.languages and not args.force:
    log.warning(
      f'"{mkvfile}" is already in MKV format, there are no subtitles or posters to integrate, languages are already set, and "--force" was not set: skipping...'
    )
    return

  log.info(files2quotedstring(cl))
  if not args.dryrun:
    try:
      subprocess.run(list(map(str, cl)), check=True, capture_output=True, text=True)
    except Exception as e:
      tempfile.unlink(missing_ok=True)
      log.error(f'{e}: Skipping ...')
      return

  log.info(f'mv {files2quotedstring([tempfile, mkvfile])}')
  if not args.dryrun:
    tempfile.replace(mkvfile)

  if vidfile.exists() and mkvfile.exists() and not vidfile.samefile(mkvfile):
    intfiles.append(vidfile)

  if args.nodelete or not intfiles:
    return

  intfiles = set(intfiles)
  log.info(f'rm {files2quotedstring(intfiles)}')
  if not args.dryrun:
    for i in intfiles:
      i.unlink()


if __name__ == '__main__':
  parser = argparse.ArgumentParser(
    fromfile_prefix_chars='@', prog=prog, epilog='Written by: ' + author
  )
  parser.add_argument(
    '-n',
    '--no-delete',
    dest='nodelete',
    action='store_true',
    help='do not delete source files (e.g., video, subtitles, or posters) after conversion to MKV.',
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
    'paths', nargs='+', help='paths to be operated on; may include wildcards; directories convert content.'
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

  errand = False
  for f in (pathlib.Path(fd) for a in args.paths for fd in glob.iglob(a)):
    errand = True
    if f.is_dir():
      for f2 in f.iterdir():
        if f2.is_file() and f2.suffix in videxts:
          doit(f2)
          errand = True
    elif f.is_file():
      doit(f)
      errand = True

  if not errand:
    log.warning(f'No proper files matching {args.paths}.')
