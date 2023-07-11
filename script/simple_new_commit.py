import argparse
import json
import logging

import requests

from rest_api import headers
from utils import RData, AttrDict


def handle(data):
    logging.info(__name__)
    data = AttrDict.from_dict(data)
    r = requests.get(f'https://api.github.com/repos/{data.repo}/branches',
                     headers=headers)
    r_data = json.loads(r.content)
    branch_filtered = [x for x in r_data if x['name'] == data.branch]

    rd = RData(False)
    if len(branch_filtered) != 1:
        print('false')
        raise RuntimeError(branch_filtered)
    branch_data = branch_filtered[0]
    if 'last_commit_sha' not in data.keys() or branch_data['commit']['sha'] != data.last_commit_sha:
        print('true')
        rd.data['last_commit_sha'] = branch_data['commit']['sha']
        rd.result = True
    else:
        print('false')
        rd.result = False
    return rd


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('repo')
    parser.add_argument('branch')
    parser.add_argument('last_commit_sha')

    handle(parser.parse_args().__dict__)
