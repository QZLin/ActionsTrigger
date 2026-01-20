import argparse
import logging

from RestApi import list_releases, AttrDict, ResultData


def handle(args: dict, unit_data: dict):
    logging.debug(args)
    args = AttrDict.from_dict(args)
    assert args.repo
    assert args.allow_prerelease

    releases = list_releases(args.repo)
    latest = None
    for x in releases:
        if args.allow_prerelease:
            latest = x
            break
        if not x['prerelease']:
            latest = x
            break
    if latest is None:
        logging.warning(f'no release was found for {args.repo}#pre:{bool(args.allow_prerelease)}')
    logging.debug(latest)
    if latest is not None and unit_data['last_tag'] != latest['tag_name']:
        logging.debug(latest['tag_name'])
        logging.debug('true')
        unit_data['last_tag'] = latest['tag_name']
        return ResultData(True, unit_data)
    logging.debug('false')
    return ResultData(False)


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('repo')
    parser.add_argument('--allow-prerelease', action='store_true')

    handle(parser.parse_args().__dict__, {})
