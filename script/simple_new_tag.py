import argparse
import json
import logging

import requests

from RestApi import list_tags, RData, AttrDict


def handle(args):
    logging.debug(args)
    args = AttrDict.from_dict(args)
    tags = list_tags(args.repo)
    if len(tags) == 0:
        return RData(False)
    last = tags[0]
    print(last)
    if args.last_tag == last['name']:
        return RData(False)
    else:
        return RData(True, {'last_tag': last['name']})


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('repo')

    handle(parser.parse_args().__dict__)
