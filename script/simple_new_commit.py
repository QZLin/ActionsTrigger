import argparse
import json
import logging

import requests

from RestApi import headers, ResultData, AttrDict


def handle(args: dict, unit_data: dict) -> ResultData:
    logging.info(__name__)
    args = AttrDict.from_dict(args)
    assert args.repo
    assert args.branch
    r = requests.get(f'https://api.github.com/repos/{args.repo}/branches',
                     headers=headers)
    r_data = json.loads(r.content)
    branch_filtered = [x for x in r_data if x['name'] == args.branch]

    rd = ResultData(False, unit_data)
    if len(branch_filtered) != 1:
        print('false')
        raise RuntimeError(branch_filtered)
    branch_data = branch_filtered[0]
    if 'last_commit_sha' not in unit_data or branch_data['commit']['sha'] != unit_data['last_commit_sha']:
        print('true')
        rd.unit_data['last_commit_sha'] = branch_data['commit']['sha']
        rd.ok = True
    else:
        print('false')
        rd.ok = False
    return rd


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('repo')
    parser.add_argument('branch')
    parser.add_argument('last_commit_sha')

    handle(parser.parse_args().__dict__, {})
