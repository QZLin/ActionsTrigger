import importlib
import os

import yaml

from RestApi import ResultData, create_value, get_actions_value, json, logging, update_values, ActionsCmd

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper


def get_unit_data(unit_id, actions_values=None) -> dict:
    if actions_values is None:
        actions_values = get_actions_value()
    v = [x for x in actions_values if x['name'] == unit_id]
    if len(v) == 1:
        v_content = v[0]['value']
        return json.loads(v_content) if v_content != 'null' else {}
    else:
        create_value(unit_id)
        return {}


def simple_handler(unit_id, args):
    origin_unit_data = get_unit_data(unit_id)
    unit_data = origin_unit_data.copy()

    cond_module = importlib.import_module(f'script.{args["condition"]["name"]}')
    cond_result: ResultData = cond_module.handle(args['condition'], unit_data)

    if cond_result.ok:
        action_module = importlib.import_module(f'script.{args["action"]["name"]}')
        act_result: ResultData = action_module.handle(args['action'], unit_data)
        if act_result.ok:
            unit_data.update(act_result.unit_data)
        ActionsCmd.notice(f'#{unit_id} executed')
    else:
        ActionsCmd.notice(f'#{unit_id} skipped')
    if origin_unit_data != unit_data:
        new_value = json.dumps(unit_data)
        logging.info(new_value)
        update_values(unit_id, new_value)
    else:
        logging.debug('unit data unchanged')


def main():
    for x in next(os.walk('config'))[2]:
        conf_path = f'config/{x}'
        logging.info(conf_path)
        ActionsCmd.notice(conf_path)
        with open(conf_path) as f:
            data = yaml.load(f, Loader)
        if data is None:
            ActionsCmd.warning('Empty conf')
            continue
        for unit_id, args in data.items():
            unit_id = unit_id.upper()
            ActionsCmd.info(f'{unit_id}#{args["type"]}')

            if 'type' not in args:
                ActionsCmd.error('key type must exist')
                continue

            if args['type'] == 'simple':
                simple_handler(unit_id, args)
            else:
                ActionsCmd.error(f'Unimplemented handler {args["type"]}')


if __name__ == '__main__':
    logging.basicConfig(format='[%(asctime)s %(levelname)s] [%(funcName)s]: %(message)s', datefmt='%H:%M:%S')
    if os.path.exists('_DEBUG'):
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)
    main()
