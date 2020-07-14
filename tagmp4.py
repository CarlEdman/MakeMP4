#!/usr/bin/python
# Version: 0.2
# Author: Carl Edman (email full name as one word at gmail.com)

prog='UpdateMP4'
version='0.2'
author='Carl Edman (CarlEdman@gmail.com)'

import argparse, shutil, os, os.path, subprocess, sys, json

from urllib.request import urlopen
from urllib.parse   import urlparse, urlunparse, urlencode
from urllib.error   import HTTPError

import mutagen
from mutagen.mp4    import MP4, MP4Cover, MP4Tags, MP4Chapters
from cetools        import *

def test_str(s):
  if not isinstance(s, str): return False
  if s.startswith('_') and s.endswith('_'): return False
  return True

def test_int(s):
  return isinstance(s, int)

def get_meta_local_tv(episode, ls):
  its = dict()

  if not test_int(episode): return its

  header = ls.pop(0).split('\t')

  header_norm = { 'Total':'Series Episode'
                , 'Series number':'Series Episode'
                , 'Nº':'Series Episode'
                , 'No. overall':'Series Episode'
                , '#':'Episode'
                , 'No.':'Episode'
                , 'No. in season':'Episode'
                , 'No. in Season':'Episode'
                , 'Episode number':'Episode'
                , 'Ep':'Episode'
                , 'Ep.':'Episode'
                , 'No. in series':'Episode'
                , 'No. in Series':'Episode'
                , 'Episode title':'Title'
                , 'Episode name':'Title'
                , 'Episode Title':'Title'
                , 'Episode Name':'Title'
                , 'Written by':'Writer'
                , 'Original Released':'Released'
                , 'Original air date':'Released'
                , 'Original airdate':'Released'
                , 'Original release date':'Released'
                , 'Release date':'Released'
                , 'Aired on':'Released'
                , 'Recorded on':'Released'
                , 'Released on':'Released'
                , 'Prod. code':'Production Code'
                , 'prod. code':'Production Code'
                , 'Prod.code':'Production Code'
                , 'PC':'Production Code'
                , 'Production number':'Production Code'
                , 'Directed by':'Director' }

  header = [ header_norm[h] if h in header_norm else h for h in header ]

  if 'Episode' not in header:
    warning(f'TV series file contains no Episode header.')
    return its

  cur = None
  ld = dict()
  for l in ls:
    ds = l.split('\t')
    if len(ds) == len(header):
      cur = {k:v for k, v in zip(header, ds)}
      if 'Episode' in cur:
        ld[int(cur['Episode'])] = cur
        del cur['Episode']
    elif cur == None:
      warning(f'TV series file does not start with a valid data line.')
      return its
    elif 'Description' in cur:
      cur['Description'] += f'  {l}'
    else:
      cur['Description'] = l

  if episode not in ld:
    warning(f'TV series file does not contain episode {episode}.')
    return its

  for k, v in ld[episode].items():
    v = v.lstrip('.').strip()
    if v.startswith('"') and v.endswith('"'): v=v[1:-1]
    if k == 'Title': its['song'] = v
    elif k == 'Writer': its['writer'] = v
    elif k == 'Production Code': its['episodeid'] = v
    elif k == 'Released' and (m := re.search(r'\b([12]\d\d\d)\b',v)): its['year']=int(m[0])
    elif k == 'Description': its['description']=v
    elif 'comment' in its: its['comment'] += f';{k}: {v}'
    else: its['comment'] = f'{k}: {v}'

  return its


def get_meta_local_movie(ls):
  its = dict()

  beg_trans = { 'Cast':'Actors'
              , 'Director':'Director'
              , 'Availability':'Availability'
              , 'Language':'Language'
              , 'Format':'Format'
              , 'Moods':'Moods'
              }

  genre_trans = { 'Musicals':'Musical'
                , 'Animes':'Anime'
                , 'Operas':'Opera'
                , 'Westerns':'Western'
                , 'Classics':'Classics'
                , 'Thrillers':'Thriller'
                , 'Cartoons':'Animation'
                , 'Period Pieces':'History'
                , 'Dramas':'Drama'
                , 'Musical':'Musical'
                , 'Anime':'Anime'
                , 'Opera':'Opera'
                , 'Western':'Western'
                , 'Classic':'Classics'
                , 'Thriller':'Thriller'
                , 'Cartoon':'Animation'
                , 'Period Piece':'History'
                , 'Drama':'Drama'
                , 'Sci-Fi':'Science Fiction'
                , 'Fantasy':'Fantasy'
                , 'Horror':'Horror'
                , 'Documentary':'Documentary'
                , 'Documentaries':'Documentary'
                , 'Superhero':'Superhero'
                , 'Comedy':'Comedy'
                , 'Comedies':'Comedy'
                , 'Crime':'Crime'
                , 'Romantic':'Romance'
                , 'Animation':'Animation'
                , 'Action':'Action'
                , 'Adventure':'Adventure'
                }

  comment = []
  for l in ls:
    if (m:=re.fullmatch(r'(?P<year>[12]\d\d\d)\s*(?P<rating>G|PG-13|PG|R|NC-17|UR|NR|TV-14|TV-MA)\s*(?:(?P<hours>\d+)h)?\s*(?:(?P<minutes>\d+)m)?\s*(?P<format>.*)',l)):
      its['year'] = int(m.group('year'))
      its['rating'] = m.group('rating')
      its['duration'] = (3600*float(m.group('hours')) if m.group('hours') else 0) + (60*float(m.group('minutes')) if m.group('minutes') else 0)
      if m.group('format'):  comment.append(f'Format: {m.group("format")}')
    elif (m := re.fullmatch(r'This movie is\s.*',l)):
      desc.append(l)
    elif (m := re.fullmatch(r'Genres?\s*:*\s*(.*)',l)):
      genres = [ genre_trans[w.strip()] for w in m[1].split(',') if w.strip() in genre_trans ]
      if genres:
        its['genre']=genres[0]
      else:
        its['genre']=m[1]
    elif (m := re.fullmatch(r'Writers?\s*:*\s*(.*)',l)):
      if 'writer' in its:
        its['writer'] += f';{m[1]}'
      else:
        its['writer'] = m[1]
    elif (m := re.fullmatch(r'(\S*)\s*:*\s*(.*)',l)) and m[1] in beg_trans:
      comment.append(f'{beg_trans[m[1]]}: {m[2]}')
    elif 'description' in its:
      its['description'] += f'  {l}'
    elif 'title' in its:
      its['description'] = l
    else:
      its['title'] = l

  its['comment'] = ';'.join(comment)
  return its

@export
def get_meta_local(title, season, episode, descpath):
  try:
    with open(os.path.join(descpath),'rt', encoding='utf-8') as f:
      ls = []
      for l in f:
        l=re.sub(r'\s*\[(\d+|[a-z])\]\s*','',l) # Strip footnotes
        l=re.sub(r'\s+-+\s+',r'—',l) # insert proper em-dashes
        l=re.sub(r'Add to Google Calendar','',l) # Google calendar links
        l=re.sub(r'[\u200A]','',l) # Remove hair space, ...
        l=l.strip() # Strip leading and trailing whitespace
        if l=="": continue
        if re.fullmatch(r'^(Rate [12345] stars)+(Rate not interested)?(Clear)?',l): continue
        if re.fullmatch(r'[0-5]\.[0-9]',l): continue
        if re.fullmatch(r'Movie Details',l): continue
        if re.fullmatch(r'Overview\s*Details(\s*Series)?',l): continue
        if re.fullmatch(r'At Home',l): continue
        if re.fullmatch(r'In Queue',l): continue
        if re.fullmatch(r'',l): continue
        ls.append(l)
  except OSError:
    ls = []

  if not ls: return dict()
  return get_meta_local_tv(episode, ls) if season else get_meta_local_movie(ls)

@export
def get_meta_omdb(title, season, episode, artpath,
                  omdb_id, omdb_status, omdb_key):
  its = dict()
  if not omdb_key: return its
  if omdb_status and (200<=omdb_status<300 or 400<=omdb_status<500): return its

  q = { 'plot':'full', 'apikey': omdb_key }

  if omdb_id:
    q['i'] = omdb_id
  elif season and episode:
    q['t'] = title
    q['type'] = 'episode'
    q['Season'] = str(season)
    q['Episode'] = str(episode)
  elif season:
    q['t'] = title
    q['type'] = 'series'
    q['Season'] = str(season)
  else:
    q['t'] = title
    q['type'] = 'movie'

  u = urlunparse(['http','www.omdbapi.com', '/', '', urlencode(q), ''])
  try:
    with urlopen(u) as f:
      its['omdb_status']=f.getcode()
      j = json.loads(f.read().decode('utf-8'))
  except HTTPError as e:
    its['omdb_status']=e.code
    j = None

  if not j: return

  genre_trans = { 'Animation':'CGI'
                , 'Musical':'Musical'
                , 'Documentary':'Documentary'
                , 'Romance':'Romance'
                , 'Horror':'Horror'
                , 'Sci-Fi':'Science Fiction'
                , 'Fantasy':'Fantasy'
                , 'Western':'Western'
                , 'Mystery':'Mystery'
                , 'Crime':'Crime'
                , 'Family':'Children'
                , 'Adventure':'Adventure'
                , 'Action':'Action'
                , 'Thriller':'Thriller'
                , 'War':'History'
                , 'History':'History'
                , 'Biography':'History'
                , 'Drama':'Drama'
                , 'Music':'Opera'
                , 'Sitcom':'Comedy'
                , 'Comedy':'Comedy'
                , 'Film-Noir':'Thriller'
                # , 'Game-Show':'XXX'
                # , 'News':'XXX'
                # , 'Reality-TV':'XXX'
                # , 'Sport':'XXX'
                # , 'Talk-Show':'XXX'
                }

  int_trans = { 'Year':'year'
              , 'Episode':'episode'
              , 'Season':'season'
              , 'totalSeasons':'totalSeasons'
              }

  str_trans = { 'Director':'director'
              , 'Writer':'writer'
              , 'Production':'network'
              , 'imdbID':'imdb_id'
              , 'seriesID': 'imdb_series_id'
              , 'Rated':'rating'
              }

  desc_trans = { 'Plot':''
               }

  comment_trans = { 'Country': 'Country: '
                  , 'DVD':'DVD Release: '
                  , 'Awards':'Awards: '
                  , 'BoxOffice':'Boxoffice: '
                  , 'Language':'Language: '
                  , 'Metascore':'Metascore: '
                  , 'Rated':'Rating: '
                  , 'Released':'Released:'
                  , 'Runtime':'Runtime: ' # To duration?
                  , 'Website':'Web Site: '
                  , 'totalSeasons':'Total Seasons: '
                  , 'Actors':'Actors: '
                  }

  skip_trans =  { ''
                , 'Episodes'
                , 'Response'
                , 'imdbRating'
                , 'imdbVotes'
                , 'Poster'
                }

  description = []
  comment = []

  for k,v in j.items():
    if v=='N/A':
      continue
    elif k=='Error':
      warning(f'{title}: IMDB Error "{v}"')
    elif k=='Type': # "movie" or "episode"
      its['type']= 'movie' if v=='movie' else 'tvshow'
    elif k=='Title':
      if season and episode:
        if v==f"Episode #{season}.{episode}": continue
        its['song']=v
      else:
        its['show']=v
    elif k=='Genre':
      genres = [ genre_trans[w.strip()] for w in v.split(',') if w.strip() in genre_trans ]
      if genres:
        its['genre']=genres[0]
      else:
        warning(f'{title}: No genres recognized in IMDB "{v}"')
    elif k in skip_trans:
      pass
    elif k in int_trans:
      its[int_trans[k]]=int(v)
    elif k in str_trans:
      its[str_trans[k]]=str(v)
    elif k in desc_trans:
      if (d := desc_trans[k]+re.sub(r'\s+-+\s+',r'—',v)) in description:
        continue
      if desc_trans[k]:
        description.append(d)
      else:
        description.insert(0, d)
    elif k in comment_trans:
      v = v.rstrip('.')
      if (c := comment_trans[k] + v) in comment: continue
      comment.append(c)
    elif k=='Ratings':
      for r in v:
        if (t := f'{r["Source"]} Rating: {r["Value"]}') in comment:
          continue
        comment.append(t)
    elif k=='Poster':
      imdb_poster = v
    else:
      warning(f'{title}: Unrecognized IMDB "{k}" = "{v}"')

  its['comment']=';'.join(comment)
  its['description']=';'.join(description)

  if not artpath or os.path.exists(artpath): return its

  if 'Poster' in j:
    u = j['Poster']
  elif 'imdb_id' in its:
    q = { 'h':'1000', 'i':its['imdb_id'], 'apikey': omdb_key }
    u = urlunparse(['http','img.omdbapi.com', '/', '', urlencode(q), ''])
  else:
    return its

  try:
    with urlopen(u) as f, open(artpath,'wb') as g:
      its['omdb_status']=f.getcode()
      shutil.copyfileobj(f, g)
  except HTTPError as e:
    its['omdb_status']=e.code

  return its

@export
def set_meta_mutagen(outfile, its):
  try:
    mutmp4 = MP4(outfile)
  except mutagen.MutagenError:
    error(f'Opening "{outfile}" metadata with mutagen failed.')

  if mutmp4.tags is None: mutmp4.add_tags()
  t = mutmp4.tags

  if test_str(p := its.get('tool', '__')): t['©too'] = [ p ]
  else: warning(f'"{outfile}" has no tool')

  type2stik = { "music": 1, "audiobook": 2, "musicvideo": 6, "movie": 9,
    "tvshow": 10, "booklet": 11, "ringtone": 14 }
  if (p := its.get('type', '__')) in type2stik: t['stik'] = [ type2stik[p] ]
  else: warning(f'"{outfile}" has no type')

  rating2rtng = { }
  if (p := its.get('rating', '__')):
    t['rtng'] = (rating2rtng[q] for q in p.split(';') if q in rating2rtng)

  if test_str(p := its.get('genre', '__')): t['©gen'] = p.split(';')
  else: warning(f'"{outfile}" has no genre')

  if test_str(p := its.get('comment', '__')): t['©cmt'] = p.split(';')

  if test_int(p := its.get('year', '__')): t['©day'] = [ str(p) ]
  else: warning(f'"{outfile}" has no year')

  if test_str(p := its.get('description', '__')):
    if len(p)>255:
      t['desc'] = [ p[:255] ]
      t['ldes'] = [ p ]
    elif len(p)>0:
      t['desc'] = [ p ]
  else:
    warning(f'"{outfile}" has no description')

  if test_int(p := its.get('season', '__')): t['tvsn'] = [ p ]
  if test_int(p := its.get('episode', '__')): t['tves'] = [ p ]
  if test_str(p := its.get('episodeid', '__')): t['tven'] = [ p ]
  if test_str(p := its.get('artist', '__')): t['©ART'] = [ p ]
  if test_str(p := its.get('writer', '__')): t['©wrt'] = [ p ]
  if test_str(p := its.get('network', '__')): t['tvnn'] = [ p ]
  if its.get('hdvideo'): t['hdvd'] = [ 1 ]

  if not test_str(title := its.get('title','__')): title = None
  if not test_str(song := its.get('song','__')): song = None
  if not test_str(show := its.get('show','__')): show = None

  if title: t['tvsh'] = [ title ]
  elif show: t['tvsh'] = [ show ]

  if its.get('type')=='tvshow' and song: t['©nam'] = [ song ]
  elif title and song: t['©nam'] = [ f'{title}: {song}' ]
  elif title: t['©nam'] = [ title ]
  elif song: t['©nam'] = [ song ]

  ext2format = { '.jpg':MP4Cover.FORMAT_JPEG
               , '.jpeg':MP4Cover.FORMAT_JPEG
               , '.png':MP4Cover.FORMAT_PNG }
  if 'coverart' in its:
    cvrs = []
    for fn in its.get('coverart',"").split(";"):
      if (ext := os.path.splitext(fn)[1].casefold()) not in ext2format:
        warning(f'Cover "{fn}" for {outfile}" has invalid extension')
        continue
      with open(fn, 'rb') as f: cvrs.append(MP4Cover(f.read(), ext2format[ext]))
    t['covr'] = cvrs
  else:
    warning(f'"{outfile}" has no cover art')

  try:
    mutmp4.save()
  except mutagen.MutagenError:
    error(f'Saving "{outfile}" metadata with mutagen failed.')

@export
def set_chapters_mutagen(outfile, its):
  if 'chapter_time' in its and 'chapter_name' in its:
    delay = its.get('chapter_delay',0.0)
    elong = its.get('chapter_elongation',1.0)

    cts = its['chapter_time']
    if is_instance(cts, float):
      cts = [cts*elong+delay]
    elif test_str(cts):
      breakpoint()
      cts = [float(i)*elong+delay for i in cts.split(';')]
    else:
      error(f'Chapter times "{cts}" for "{outfile}" are invalid')

    cns = its['chapter_name']
    if test_str(cns):
      cns = cns.split(';')
    else:
      error(f'Chapter names "{cns}" for "{outfile}" are invalid')

    #MP4Chapters(Chapter(start, title) for (start,title) in zip (cts, cns))
    warning(f'Chapter import for "{outfile}" not yet supported.')

@export
def set_meta_cmd(outfile, its):
  call=[ 'mp4tags', outfile ]

  if test_str(p := its.get('tool', '__')): call += [ '-tool' , p ]
  else: warning(f'"{outfile}" has no tool')

  if test_str(p := its.get('type', '__')): call += [ '-type' , p ]
  else: warning(f'"{outfile}" has no type')

  if test_str(p := its.get('genre', '__')): call += [ '-genre' , p ]
  else: warning(f'"{outfile}" has no genre')

  if test_str(p := its.get('comment', '__')): call += [ '-comment' , p ]

  if test_int(p := its.get('year', '__')): call += [ '-year' , str(p) ]
  else: warning(f'"{outfile}" has no year')

  if test_str(p := its.get('description', '__')):
    if len(p)>255: call += [ '-desc', p[:255], '-longdesc', p ]
    elif len(p)>0: call += [ '-desc' , p ]
  else: warning(f'"{outfile}" has no description')

  if test_int(p := its.get('season', '__')): call += [ '-season' , str(p) ]
  if test_int(p := its.get('episode', '__')): call += [ '-episode' , str(p) ]
  if test_str(p := its.get('episodeid', '__')): call += [ '-episodeid' , p ]
  if test_str(p := its.get('artist', '__')): call += [ '-artist' , p ]
  if test_str(p := its.get('writer', '__')): call += [ '-writer' , p ]
  if test_str(p := its.get('network', '__')): call += [ '-network' , p ]
  # if test_str(p := its.get('rating', '__')): call += [ '-rating' , p ]
  if its.get('hdvideo'): call += [ '-hdvideo' , '1']

  if not test_str(title := its.get('title','__')): title = None
  if not test_str(song := its.get('song','__')): song = None
  if not test_str(show := its.get('show','__')): show = None

  if title: call += [ '-show' , title]
  elif show: call += [ '-show' , show]

  if its.get('type')=='tvshow' and song: call += ['-song', song]
  elif title and song: call += ['-song', f'{title}: {song}']
  elif title: call += ['-song', title]
  elif song: call += ['-song', song]

  try:
    cp = subprocess.run(call, check=True, capture_output=True)
  except subprocess.CalledProcessError as cpe:
    with open(outfile, 'w') as f: f.truncate(0)
    error(f'Error code for {cpe.cmd}: {cpe.returncode} : {cpe.stdout} : {cpe.stderr}')

  if 'coverart' in its:
    call = [ 'mp4art', outfile ]
    for i in its.get('coverart',"").split(";"):
      call += [ '--add', i ]
    call += [ outfile ]
    try:
      cp = subprocess.run(call, check=True, capture_output=True)
    except subprocess.CalledProcessError as cpe:
      with open(outfile, 'w') as f: f.truncate(0)
    error(f'Error code for {cpe.cmd}: {cpe.returncode} : {cpe.stdout} : {cpe.stderr}')
  else:
    warning(f'"{outfile}" has no cover art')

@export
def set_chapters_cmd(outfile, its):
  chapterfile = os.path.splitext(outfile)[0]+'.chapters.txt'
  if os.path.exists(chapterfile) and getsize(chapterfile)!=0:
    warning(f'Adding chapters from existing config file "{chapterfile}"')
    try:
      cp = subprocess.run(['mp4chaps', '--import', outfile], check=True, capture_output=True)
    except subprocess.CalledProcessError as cpe:
      with open(outfile, 'w') as f: f.truncate(0)
      error(f'Error code for {cpe.cmd}: {cpe.returncode} : {cpe.stdout} : {cpe.stderr}')
    finally:
      return

  tempfile = os.path.join(os.path.split(outfile)[0],'tmp.mp4')
  chapterfile = os.path.splitext(tempfile)[0] + '.chapters.txt'
  if not os.path.exists(tempfile) and not os.path.exists(chapterfile) and 'chapter_time' in its and 'chapter_name' in its:
    delay=its.get('chapter_delay',0.0)
    elong=its.get('chapter_elongation',1.0)
    cns=[i.strip() for i in its['chapter_name'].split(';')]
    cts=[float(i)*elong+delay for i in its['chapter_time'].split(';')]

    with open(chapterfile,'wt', encoding='utf-8') as f:
      for (ct,cn) in zip(cts,cns):
        (neg,hours,mins,secs,msecs)=secsToParts(ct)
        if neg: continue
        f.write(f'{hours:02d}:{mins:02d}:{secs:02d}.{msecs:03d} ')
        f.write(f'{cn} ({hours*60+mins:d}m {secs:d}s)\n')

    try:
      os.rename(outfile, tempfile)
      cp = subprocess.run(['mp4chaps', '--import', tempfile], check=True, capture_output=True)
    except subprocess.CalledProcessError as cpe:
      with open(tempfile, 'w') as f: f.truncate(0)
      error(f'Error code for {cpe.cmd}: {cpe.returncode}')
    finally:
      os.rename(tempfile, outfile)
      os.remove(chapterfile)
      return

if __name__ == "__main__":
  if 'parser' not in globals():
    parser = argparse.ArgumentParser(description='Update Metadata in MP4 files based on filenames and external sources',fromfile_prefix_chars='@',prog=prog,epilog='Written by: '+author)

    parser.add_argument('--version', action='version', version='%(prog)s '+version)
    parser.add_argument('-v','--verbose',dest='loglevel',action='store_const', const=logging.INFO)
    parser.add_argument('-d','--debug',dest='loglevel',action='store_const', const=logging.DEBUG)
    parser.set_defaults(loglevel=logging.WARN)
    parser.add_argument('-l','--log',dest='logfile',action='store')
    parser.add_argument('files', nargs='*', metavar='FILES', help='files to update')
    parser.add_argument('--descdir',dest='descdir',action='store',help='directory for .txt files with descriptive data')
    parser.add_argument('--artdir',dest='artdir',action='store',help='directory for .jpg and .png cover art')
    parser.add_argument('--omdbkey',dest='omdbkey',action='store',help='your OMDB key to automatically retrieve posters')
    inifile=f'{os.path.splitext(sys.argv[0])[0]}.ini'
    if os.path.exists(inifile): sys.argv.insert(1,'@'+inifile)
    inifile=prog + '.ini'
    if os.path.exists(inifile): sys.argv.insert(1,'@'+inifile)
    inifile='..\\' + prog + '.ini'
    if os.path.exists(inifile): sys.argv.insert(1,'@'+inifile)
    args = parser.parse_args()
    print(args)
