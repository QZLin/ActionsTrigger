import unittest


class MyTestCase(unittest.TestCase):
    def test_attr_dict(self):
        from RestApi import AttrDict
        a = AttrDict()
        a.test = 1
        print(a)
        self.assertEqual(a['test'], 1)


if __name__ == '__main__':
    unittest.main()
