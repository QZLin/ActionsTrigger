import unittest

import requests

from actionstrigger.script.curl_hash_changed import handle


class CurlHashChangedTestCase(unittest.TestCase):
    URL = 'https://example.com/'

    def _handle(self, data, unit_data):
        """Run the handler, skipping the test when the network is unavailable."""
        try:
            return handle(data, unit_data)
        except requests.RequestException as e:  # the check needs outbound network
            self.skipTest(f'network unavailable: {e}')

    def test_reports_change_only_once(self):
        data = {
            'url': self.URL,
            'headers': {}
        }
        rd = self._handle(data, {})
        print(rd.unit_data)
        self.assertTrue(rd.ok)
        rd2 = self._handle(data, rd.unit_data)
        print(rd2.unit_data)
        self.assertFalse(rd2.ok)


if __name__ == '__main__':
    unittest.main()
