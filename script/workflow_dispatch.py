import argparse
import json
import logging

import requests

from RestApi import headers, RData


# https://docs.github.com/rest/actions/workflows#create-a-workflow-dispatch-event
def handle(args):
    logging.info(__name__)
    try:
        requests.post(f'https://api.github.com/repos/{args["repo"]}/actions/workflows/{args["id"]}/dispatches',
                      headers=headers,
                      data=json.dumps({'ref': args['branch']}))
        return RData(True)
    except Exception as e:
        logging.error(e)
    return RData(False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('repo')
    parser.add_argument('branch')
    parser.add_argument('id')

    handle(parser.parse_args().__dict__)
