import unittest
from unittest import mock

from actions_trigger import main
from actions_trigger.rest_api import ResultData


class FakeHandler:
    """Stands in for one of the ``script`` modules."""

    def __init__(self, ok: bool = True, data: dict | None = None):
        self.ok = ok
        self.data = data or {}
        self.seen: list[dict] = []

    def handle(self, args: dict, unit_data: dict) -> ResultData:
        self.seen.append(dict(args))
        if self.ok:
            unit_data.update(self.data)  # conditions and actions may mutate the state
        return ResultData(self.ok, dict(self.data))


class SimpleHandlerTestCase(unittest.TestCase):
    def run_unit(self, args: dict, modules: dict[str, FakeHandler], unit_data: dict | None = None) -> dict:
        update_values = mock.Mock()
        notices: list[str] = []
        warnings: list[str] = []
        errors: list[str] = []

        def resolve(name: str) -> FakeHandler:
            return modules[name]

        with mock.patch.object(main, 'get_unit_data', return_value=dict(unit_data or {})), \
                mock.patch.object(main, 'update_values', update_values), \
                mock.patch.object(main, 'load_handler', side_effect=resolve), \
                mock.patch.object(main.ActionsCmd, 'notice', side_effect=notices.append), \
                mock.patch.object(main.ActionsCmd, 'warning', side_effect=warnings.append), \
                mock.patch.object(main.ActionsCmd, 'error', side_effect=errors.append):
            main.simple_handler('UNIT', args)

        return {'update': update_values, 'notices': notices, 'warnings': warnings, 'errors': errors}


class ActionsListTestCase(SimpleHandlerTestCase):
    def test_runs_every_action_of_the_list(self):
        cond = FakeHandler(ok=True)
        first = FakeHandler(ok=True, data={'first': 1})
        second = FakeHandler(ok=True, data={'second': 2})
        args = {'condition': {'name': 'cond'}, 'actions': [{'name': 'first'}, {'name': 'second'}]}

        out = self.run_unit(args, {'cond': cond, 'first': first, 'second': second})

        self.assertEqual(len(first.seen), 1)
        self.assertEqual(len(second.seen), 1)
        out['update'].assert_called_once_with('UNIT', '{"first": 1, "second": 2}')
        self.assertIn('#UNIT executed 2/2 action(s)', out['notices'])
        self.assertEqual(out['errors'], [])

    def test_each_action_receives_its_own_args(self):
        first = FakeHandler(ok=True)
        second = FakeHandler(ok=True)
        args = {
            'condition': {'name': 'cond'},
            'actions': [
                {'name': 'first', 'repo': 'a/b'},
                {'name': 'second', 'repo': 'c/d', 'branch': 'sync'},
            ],
        }

        self.run_unit(args, {'cond': FakeHandler(ok=True), 'first': first, 'second': second})

        self.assertEqual(first.seen, [{'name': 'first', 'repo': 'a/b'}])
        self.assertEqual(second.seen, [{'name': 'second', 'repo': 'c/d', 'branch': 'sync'}])

    def test_failing_action_does_not_stop_the_others(self):
        failing = FakeHandler(ok=False)
        succeeding = FakeHandler(ok=True, data={'done': True})
        args = {'condition': {'name': 'cond'}, 'actions': [{'name': 'failing'}, {'name': 'succeeding'}]}

        out = self.run_unit(args, {'cond': FakeHandler(ok=True), 'failing': failing, 'succeeding': succeeding})

        self.assertEqual(len(succeeding.seen), 1)
        out['update'].assert_called_once_with('UNIT', '{"done": true}')
        self.assertIn('#UNIT executed 1/2 action(s)', out['notices'])
        self.assertIn('#UNIT action failing failed', out['warnings'])

    def test_skips_actions_when_condition_is_false(self):
        action = FakeHandler(ok=True, data={'done': True})
        args = {'condition': {'name': 'cond'}, 'actions': [{'name': 'action'}]}

        out = self.run_unit(args, {'cond': FakeHandler(ok=False), 'action': action})

        self.assertEqual(action.seen, [])
        out['update'].assert_not_called()
        self.assertIn('#UNIT skipped', out['notices'])

    def test_single_action_mapping_is_accepted(self):
        action = FakeHandler(ok=True)
        args = {'condition': {'name': 'cond'}, 'actions': {'name': 'action'}}

        out = self.run_unit(args, {'cond': FakeHandler(ok=True), 'action': action})

        self.assertEqual(len(action.seen), 1)
        self.assertTrue(any('should be a list' in w for w in out['warnings']))

    def test_invalid_entries_are_skipped(self):
        action = FakeHandler(ok=True)
        args = {
            'condition': {'name': 'cond'},
            'actions': [{'name': 'action'}, {'repo': 'no-name'}, 'not-a-mapping'],
        }

        out = self.run_unit(args, {'cond': FakeHandler(ok=True), 'action': action})

        self.assertEqual(len(action.seen), 1)
        self.assertEqual(len(out['errors']), 2)
        self.assertTrue(any('actions[1]' in e for e in out['errors']))
        self.assertTrue(any('actions[2]' in e for e in out['errors']))

    def test_actions_must_be_a_list(self):
        args = {'condition': {'name': 'cond'}, 'actions': 'echo'}

        out = self.run_unit(args, {'cond': FakeHandler(ok=True)})

        out['update'].assert_not_called()
        self.assertTrue(any('must be a list' in e for e in out['errors']))

    def test_action_and_actions_prefers_actions(self):
        only_action = FakeHandler(ok=True)
        listed = FakeHandler(ok=True)
        args = {'condition': {'name': 'cond'}, 'action': {'name': 'single'}, 'actions': [{'name': 'listed'}]}

        out = self.run_unit(args, {'cond': FakeHandler(ok=True), 'single': only_action, 'listed': listed})

        self.assertEqual(only_action.seen, [])
        self.assertEqual(len(listed.seen), 1)
        self.assertTrue(any('both action and actions' in w for w in out['warnings']))

    def test_no_action_defined(self):
        args = {'condition': {'name': 'cond'}}

        out = self.run_unit(args, {'cond': FakeHandler(ok=True)})

        out['update'].assert_not_called()
        self.assertTrue(any('neither action nor actions' in e for e in out['errors']))

    def test_empty_actions_list_runs_nothing(self):
        cond = FakeHandler(ok=True)
        out = self.run_unit({'condition': {'name': 'cond'}, 'actions': []}, {'cond': cond})

        self.assertEqual(cond.seen, [])  # nothing to do, so the condition is not even evaluated
        out['update'].assert_not_called()

    def test_null_actions_runs_nothing(self):
        cond = FakeHandler(ok=True)
        out = self.run_unit({'condition': {'name': 'cond'}, 'actions': None}, {'cond': cond})

        self.assertEqual(cond.seen, [])
        out['update'].assert_not_called()


class SingleActionTestCase(SimpleHandlerTestCase):
    def test_legacy_single_action_still_runs(self):
        action = FakeHandler(ok=True, data={'done': True})
        args = {'condition': {'name': 'cond'}, 'action': {'name': 'action'}}

        out = self.run_unit(args, {'cond': FakeHandler(ok=True), 'action': action})

        self.assertEqual(len(action.seen), 1)
        out['update'].assert_called_once_with('UNIT', '{"done": true}')
        self.assertIn('#UNIT executed 1/1 action(s)', out['notices'])
        self.assertEqual(out['warnings'], [])


class RunLoopTestCase(unittest.TestCase):
    """A broken unit must not stop the run; the report records it."""

    def run_dir(self, yaml_text: str, modules: dict) -> main.RunReport:
        import tempfile
        from pathlib import Path as _Path

        def resolve(name: str):
            return modules[name]

        with tempfile.TemporaryDirectory() as tmp:
            (_Path(tmp) / 'units.yaml').write_text(yaml_text, encoding='utf-8')
            with mock.patch.object(main, 'load_handler', side_effect=resolve), \
                    mock.patch.object(main, 'get_unit_data', return_value={}), \
                    mock.patch.object(main, 'update_values'), \
                    mock.patch.object(main.ActionsCmd, 'notice'), \
                    mock.patch.object(main.ActionsCmd, 'error'):
                return main.run(_Path(tmp))

    def test_broken_unit_does_not_stop_the_others(self):
        class Boom:
            def handle(self, args, unit_data):
                raise RuntimeError('upstream exploded')

        report = self.run_dir(
            'broken:\n  type: simple\n  condition:\n    name: boom\n  action:\n    name: ok\n'
            'fine:\n  type: simple\n  condition:\n    name: ok\n  action:\n    name: writes\n',
            {'boom': Boom(), 'ok': FakeHandler(ok=True), 'writes': FakeHandler(ok=True, data={'seen': 1})},
        )

        self.assertEqual(list(report.failed), ['BROKEN'])
        self.assertIn('RuntimeError', report.failed['BROKEN'])
        self.assertEqual(list(report.outcomes), ['FINE'])
        self.assertEqual(report.states, {'FINE': {'seen': 1}})
        self.assertTrue(report.changed)

    def test_report_exposes_state_hashes(self):
        report = self.run_dir(
            'one:\n  type: simple\n  condition:\n    name: ok\n  action:\n    name: ok\n',
            {'ok': FakeHandler(ok=True)},
        )

        self.assertEqual(report.states, {'ONE': {}})
        self.assertEqual(report.fingerprint, report.origin_fingerprint)
        self.assertFalse(report.changed)
        self.assertEqual(report.failed, {})


if __name__ == '__main__':
    unittest.main()
