#!/usr/bin/python

prog='UpdateGoDaddy'
version='0.1'
author='Carl Edman (CarlEdman@gmail.com)'

from urllib.request import urlopen, Request
from urllib.parse import urlparse, urlunparse, urlencode

import json, sys, argparse, ssl

parser = argparse.ArgumentParser(description='Update GoDaddy DNS "A" Record.')
parser.add_argument('--version', action='version', version='%(prog)s ' + version)
# parser.add_argument('-v','--verbose',dest='loglevel',action='store_const', const=logging.INFO)
# parser.add_argument('-d','--debug',dest='loglevel',action='store_const', const=logging.DEBUG)
# parser.set_defaults(loglevel=logging.WARN)
parser.add_argument('name', type=str, default=None, help='GoDaddy DNS Name (fully-qualified).')
parser.add_argument('ip_address', nargs='?', type=str, default=None, help='GoDaddy DNS Address (defaults to current WAN address')
parser.add_argument('--key', '-k', type=str, default='9PtdFYTvYPP_PHqNR4ScQ6yLck6c5zBtpq', help='GoDaddy production key from https://developer.godaddy.com/keys/')
parser.add_argument('--secret', '-s', type=str, default='PHqV82w9d63HSkZFJzskwT', help='GoDaddy production secret from https://developer.godaddy.com/keys/')
parser.add_argument('--ttl', type=int, default=3600 , help='GoDaddy DNS TTL')
args = parser.parse_args()

(name,domain) = args.name.split('.',maxsplit=1)

if not domain:
  exit(1)

req = Request('https://api.godaddy.com/v1/domains/{}/records/A/{}'.format(domain,name))
if args.key and args.secret:
  req.add_header("Authorization", "sso-key {}:{}".format(args.key,args.secret))
req.add_header("Accept","application/json")

with urlopen(req) as f:
  j=json.loads(f.read().decode('utf-8'))
  print(f.getcode())

print(json.dumps(j,sort_keys=True,indent=3))

data = json.dumps([ { "data": args.ip_address if args.ip_address else "0.0.0.0", "ttl": args.ttl, "name": name, "type": "A" } ]).encode('utf-8')
print(data)
req = Request('https://api.godaddy.com/v1/domains/{}/records/A/{}'.format(domain,name), method='PUT', data=data)
if args.key and args.secret:
  req.add_header("Authorization", "sso-key {}:{}".format(args.key,args.secret))
req.add_header("Content-Type","application/json")

with urlopen(req) as f:
  j=json.loads(f.read().decode('utf-8'))
  print(f.getcode())

print(json.dumps(j,sort_keys=True,indent=3))
