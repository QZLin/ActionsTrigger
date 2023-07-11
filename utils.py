from dataclasses import dataclass, field


@dataclass
class ResultData:
    result: bool
    data: dict = field(default_factory=dict)


class AttrDict(dict):
    @staticmethod
    def from_dict(v: dict) -> 'AttrDict':
        r = AttrDict()
        r.update(v)
        return r

    def __getattr__(self, item):
        return self[item] if item in self.keys() else None

    def __setattr__(self, key, value):
        self[key] = value


RData = ResultData
if __name__ == '__main__':
    a = AttrDict()
    a.test = 1
    print(a, a.test)
