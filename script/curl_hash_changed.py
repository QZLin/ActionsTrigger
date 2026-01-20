import argparse
import hashlib
import logging

import requests

from RestApi import ResultData


def handle(args: dict, unit_data: dict) -> ResultData:
    logging.info(__name__)
    assert args['url']
    args.setdefault('headers', None)
    r = requests.get(args['url'], headers=args['headers'])
    content = r.content
    logging.debug(content)
    sha256_hash = hashlib.sha256(content).hexdigest()
    logging.info(sha256_hash)

    rd = ResultData(False, unit_data)
    if 'last_hash' not in unit_data or sha256_hash != unit_data['last_hash']:
        unit_data['last_hash'] = sha256_hash
        rd.ok = True

    return rd


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('url')
    parser.add_argument('headers')

    handle(parser.parse_args().__dict__, {})
