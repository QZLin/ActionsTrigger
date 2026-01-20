import argparse
import logging

from RestApi import list_tags, AttrDict, ResultData


def handle(args: dict, unit_data: dict):
    logging.debug(args)
    args = AttrDict.from_dict(args)
    tags = list_tags(args.repo)
    if len(tags) == 0:
        return ResultData(False)
    last = tags[0]
    logging.debug(last)
    if 'last_tag' in unit_data and unit_data['last_tag'] == last['name']:
        return ResultData(False, unit_data)
    else:
        unit_data['last_tag'] = last['name']
        return ResultData(True, unit_data)


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('repo')

    handle(parser.parse_args().__dict__, {})
