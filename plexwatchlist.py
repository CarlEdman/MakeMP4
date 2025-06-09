#!python3
from plex_api_client import PlexAPI
from plex_api_client.models import operations

with PlexAPI(
  access_token='9YzwMW8tMr6X7hh9JgXy',
) as plex_api:
  res = plex_api.watchlist.get_watch_list(
    request={
      'filter_': operations.Filter.AVAILABLE,
      'x_plex_token': '9YzwMW8tMr6X7hh9JgXy',
    }
  )

  assert res.object is not None

  # Handle response
  print(res.object)
