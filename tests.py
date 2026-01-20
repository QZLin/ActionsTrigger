import logging
import unittest

logging.basicConfig(format='[%(asctime)s %(levelname)s] [%(funcName)s]: %(message)s', datefmt='%H:%M:%S')
logging.getLogger().setLevel(logging.DEBUG)


class MyTestCase(unittest.TestCase):
    def test_attr_dict(self):
        from RestApi import AttrDict
        a = AttrDict()
        a.test = 1
        print(a)
        self.assertEqual(a['test'], 1)

    def test_curl_hash_changed(self):
        from script.curl_hash_changed import handle
        data = {
            'url': 'https://example.com/',
            'headers': {}
        }
        unit_data = {}
        rd = handle(data, unit_data)
        print(rd.unit_data)
        self.assertTrue(rd.ok)
        rd2 = handle(data, rd.unit_data)
        print(rd2.unit_data)
        self.assertFalse(rd2.ok)


if __name__ == '__main__':
    unittest.main()
