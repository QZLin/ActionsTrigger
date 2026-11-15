import unittest

from actions_trigger.rest_api import AttrDict


class AttrDictTestCase(unittest.TestCase):
    def test_attribute_access(self):
        a = AttrDict()
        a.test = 1
        print(a)
        self.assertEqual(a['test'], 1)

    def test_from_dict(self):
        a = AttrDict.from_dict({'test': 2})
        self.assertEqual(a.test, 2)
        self.assertIsNone(a.missing)


if __name__ == '__main__':
    unittest.main()
