import importlib
import os

import yaml

from rest_api import *
from utils import *

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper


def simple_handler(id_, args):
    this_repo_values = values()
    v = [x for x in this_repo_values if x['name'] == id_]
    if len(v) == 1:
        v_content = v[0]['value']
        unit_data = json.loads(v_content) if v_content != 'null' else {}
    else:
        create_value(id_)
        unit_data = {}

    to_update = {}
    cond_module = importlib.import_module(f'script.{args["condition"]["name"]}')
    merged_data = unit_data.copy()
    merged_data.update(args['condition'])
    r: ResultData = cond_module.handle(merged_data)
    to_update.update(r.data)

    if r.result:
        action_module = importlib.import_module(f'script.{args["action"]["name"]}')
        merged_data = unit_data.copy()
        merged_data.update(args['action'])
        r2 = action_module.handle(merged_data)
        to_update.update(r2.data)
    else:
        logging.info('condition not reached')
    new_unit_data = unit_data.copy()
    new_unit_data.update(to_update)
    if unit_data != new_unit_data:
        new_value = json.dumps(new_unit_data)
        logging.info(new_value)
        update_values(id_, new_value)
    else:
        logging.info('unit data not changed')


def main():
    for x in next(os.walk('config'))[2]:
        path_ = f'config/{x}'
        logging.info(path_)
        with open(path_) as f:
            data = yaml.load(f, Loader)
        if data is None:
            continue
        for id_, args in data.items():
            id_ = id_.upper()
            logging.info(f'{id_}#{args["type"]}')
            if args['type'] == 'simple':
                simple_handler(id_, args)


if __name__ == '__main__':
    logging.basicConfig(format='[%(asctime)s %(levelname)s] [%(funcName)s]: %(message)s', datefmt='%H:%M:%S')
    if os.path.exists('_DEBUG'):
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)
    main()
