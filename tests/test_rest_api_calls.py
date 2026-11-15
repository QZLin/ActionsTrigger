import json
import unittest
from unittest import mock

import requests

from actions_trigger import rest_api


def response(status: int, payload=None, headers=None) -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r._content = json.dumps(payload).encode() if payload is not None else b''
    r.headers.update(headers or {})
    return r


class RepoValuesTestCase(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(rest_api, 'api_headers', return_value={})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_follows_pagination(self):
        first = response(200, {'variables': [{'name': 'A', 'value': '1'}]},
                         {'Link': '<https://api.github.com/x?page=2>; rel="next", <...>; rel="last"'})
        second = response(200, {'variables': [{'name': 'B', 'value': '2'}]})

        with mock.patch.object(rest_api.requests, 'get', side_effect=[first, second]) as get:
            variables = rest_api.repo_values('o/r')

        self.assertEqual([x['name'] for x in variables], ['A', 'B'])
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args_list[0].kwargs['params'], {'per_page': 100})
        self.assertIsNone(get.call_args_list[1].kwargs['params'])

    def test_missing_variables_key_is_tolerated(self):
        with mock.patch.object(rest_api.requests, 'get', return_value=response(200, {})):
            self.assertEqual(rest_api.repo_values('o/r'), [])

    def test_error_raises_and_annotates(self):
        with mock.patch.object(rest_api.requests, 'get',
                              return_value=response(401, {'message': 'Requires authentication'})), \
                mock.patch.object(rest_api.ActionsCmd, 'error') as error:
            with self.assertRaises(rest_api.ApiError) as ctx:
                rest_api.repo_values('o/r')

        self.assertEqual(ctx.exception.status, 401)
        self.assertIn('Requires authentication', str(ctx.exception))
        error.assert_called_once()


class CreateValueTestCase(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(rest_api, 'api_headers', return_value={})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_created(self):
        with mock.patch.object(rest_api.requests, 'post', return_value=response(201, {})):
            rest_api.create_value('A')  # must not raise

    def test_existing_variable_is_not_an_error(self):
        with mock.patch.object(rest_api.requests, 'post',
                               return_value=response(409, {'message': 'Variable already exists'})):
            rest_api.create_value('A')  # 409 means it is already there

    def test_forbidden_is_reported(self):
        with mock.patch.object(rest_api.requests, 'post',
                               return_value=response(403, {'message': 'Resource not accessible'})), \
                mock.patch.object(rest_api.ActionsCmd, 'error'):
            with self.assertRaises(rest_api.ApiError):
                rest_api.create_value('A')


class UpdateValueTestCase(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(rest_api, 'api_headers', return_value={})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_no_content_is_success(self):
        with mock.patch.object(rest_api.requests, 'patch', return_value=response(204)):
            rest_api.update_values('A', '{}')

    def test_failure_raises(self):
        with mock.patch.object(rest_api.requests, 'patch', return_value=response(404, {'message': 'Not Found'})), \
                mock.patch.object(rest_api.ActionsCmd, 'error'):
            with self.assertRaises(rest_api.ApiError):
                rest_api.update_values('A', '{}')


class DeleteRunTestCase(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(rest_api, 'api_headers', return_value={})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_deleted(self):
        with mock.patch.object(rest_api.requests, 'delete', return_value=response(204)):
            self.assertTrue(rest_api.delete_workflow_run('o/r', 7))

    def test_already_gone(self):
        with mock.patch.object(rest_api.requests, 'delete', return_value=response(404, {'message': 'Not Found'})):
            self.assertFalse(rest_api.delete_workflow_run('o/r', 7))

    def test_forbidden(self):
        with mock.patch.object(rest_api.requests, 'delete',
                               return_value=response(403, {'message': 'Resource not accessible'})), \
                mock.patch.object(rest_api.ActionsCmd, 'error') as error:
            self.assertFalse(rest_api.delete_workflow_run('o/r', 7))

        error.assert_called_once()


class VariableNameTestCase(unittest.TestCase):
    def test_hyphens_become_underscores(self):
        self.assertEqual(rest_api.variable_name('DSH-WORKSPACE-MIGRATE'), 'DSH_WORKSPACE_MIGRATE')

    def test_legal_names_are_untouched(self):
        self.assertEqual(rest_api.variable_name('FORWARD2_SYNC'), 'FORWARD2_SYNC')

    def test_leading_digit_is_prefixed(self):
        self.assertEqual(rest_api.variable_name('2fa_check'), '_2fa_check')

    def test_storage_calls_use_the_sanitized_name(self):
        with mock.patch.object(rest_api, 'api_headers', return_value={}), \
                mock.patch.object(rest_api.requests, 'patch', return_value=response(204)) as patch, \
                mock.patch.object(rest_api, 'repository', return_value='o/r'):
            rest_api.update_values('MY-UNIT', '{}')

        self.assertTrue(patch.call_args.args[0].endswith('/actions/variables/MY_UNIT'))


if __name__ == '__main__':
    unittest.main()
