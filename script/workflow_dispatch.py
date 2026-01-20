import argparse
import json
import logging

import requests

from RestApi import headers, ResultData


# https://docs.github.com/rest/actions/workflows#create-a-workflow-dispatch-event
def handle(args: dict, unit_data: dict) -> ResultData:
    logging.info(__name__)
    try:
        requests.post(f'https://api.github.com/repos/{args["repo"]}/actions/workflows/{args["id"]}/dispatches',
                      headers=headers,
                      data=json.dumps({'ref': args['branch']}))
        return ResultData(True)
    except Exception as e:
        logging.error(e)
    return ResultData(False,unit_data)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('repo')
    parser.add_argument('branch')
    parser.add_argument('id')

    handle(parser.parse_args().__dict__,{})
