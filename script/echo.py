from RestApi import ResultData


def handle(args):
    print(args['content'])
    return ResultData(True)
