from RestApi import ResultData


def handle(args: dict, unit_data: dict):
    print(args['content'])
    return ResultData(True)
