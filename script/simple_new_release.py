import argparse
import json
import logging

import requests

from rest_api import list_releases
from utils import RData, AttrDict


def handle(args):
    logging.debug(args)
    args = AttrDict.from_dict(args)

    releases = list_releases(args.repo)
    latest = None
    for x in releases:
        if args.allow_prerelease:
            latest = x
            break
        if not x['prerelease']:
            latest = x
            break
    if latest is None:
        logging.warning(f'no release was found for {args.repo}#pre:{bool(args.allow_prerelease)}')
    print(latest)
    if latest is not None and args.last_tag != latest['tag_name']:
        print(latest['tag_name'])
        print('true')
        return RData(True, {'last_tag': latest['tag_name']})
    print('false')
    return RData(False)


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('repo')
    parser.add_argument('--allow-prerelease', action='store_true')

    handle(parser.parse_args().__dict__)
