from ..rest_api import ResultData


def handle(args: dict, unit_data: dict):
    print(args['content'])
    return ResultData(True)
