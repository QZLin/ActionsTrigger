# import json
# import logging
#
# import requests
#
# from rest_api import *
# from secret.config import this_repo


# if __name__ == '__main__':
#     parser = argparse.ArgumentParser()
#     parser.add_argument('repo')
#     # parser.add_argument('token')
#     parser.add_argument('mode', choices=['get', 'set'])
#     parser.add_argument('name')
#     parser.add_argument('-v', '--value')
#     parser.add_argument('-j', '--json')
#
#     args = parser.parse_args()
#     if args.mode == 'get':
#         data = None
#     elif args.mode == 'set':
#         data = {"name": args.name, "value": args.value}
#     else:
#         exit(1)
#     requests.get(f'https://api.github.com/repos/{args.repo}/actions/variables',
#                  headers=basic_head,
#                  data=data)
