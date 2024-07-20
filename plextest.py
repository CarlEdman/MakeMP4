from plexapi.server import PlexServer

plex = PlexServer()

# Example 1: List all unwatched movies.
movies = plex.library.section('Movies')
for video in movies.search(unwatched=True):
    print(video.title)
