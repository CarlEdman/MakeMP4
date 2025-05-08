#!python3
from plexapi.server import PlexServer

plex = PlexServer()

# Example 1: List all unwatched movies.
movies = plex.library.section("Movies")
for video in movies.search(year=1999):
  print(video.title, video.sourceURI)
