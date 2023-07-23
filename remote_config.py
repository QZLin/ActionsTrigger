import argparse
import logging
import os.path

import requests

from rest_api import get_release_by_tag


def download(url, target):
    r = requests.get(url)
    with open(target, 'wb') as f:
        f.write(r.content)
        logging.info(f'write to {target}')


def fetch_release(repo) -> list:
    data = get_release_by_tag(repo, 'store-config')
    if data is None:
        logging.info('no available online config')
        return []
    if len(data['assets']) > 0:
        return data['assets']
    else:
        logging.info('empty online config')
        return []


def get_config(repo, allow_override=False):
    assets = fetch_release(repo)
    logging.info([x['name'] for x in assets])
    for x in assets:
        url = x['browser_download_url']
        name = x['name']
        target = f'config/{name}'
        if not allow_override and os.path.exists(target):
            logging.warning(f'skip {target} because file existed and override is not allowed')
            continue
        download(url, target)


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('repo')
    parser.add_argument('--allow-override', action='store_true')

    args = parser.parse_args()
    get_config(args.repo, args.allow_override)
