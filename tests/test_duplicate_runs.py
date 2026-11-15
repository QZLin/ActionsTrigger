import unittest
from unittest import mock

from actions_trigger import duplicate_runs


class FingerprintTestCase(unittest.TestCase):
    def test_same_key_information_hashes_equally(self):
        self.assertEqual(duplicate_runs.fingerprint({'A': {'sha': '1'}, 'B': {}}),
                         duplicate_runs.fingerprint({'B': {}, 'A': {'sha': '1'}}))

    def test_different_key_information_hashes_differently(self):
        self.assertNotEqual(duplicate_runs.fingerprint({'A': {'sha': '1'}}),
                            duplicate_runs.fingerprint({'A': {'sha': '2'}}))
        self.assertNotEqual(duplicate_runs.fingerprint({'A': {}}), duplicate_runs.fingerprint({}))


class BookkeepingTestCase(unittest.TestCase):
    """The REST layer is mocked; no request leaves the test."""

    def setUp(self):
        self.values: dict[str, str] = {}
        self.deleted: list[int] = []
        self.delete_ok = True

        def fake_delete(repo, run_id):
            if not self.delete_ok:
                return False
            self.deleted.append(run_id)
            return True

        patchers = [
            mock.patch.object(duplicate_runs.settings, 'repository', return_value='o/r'),
            mock.patch.object(duplicate_runs, 'repo_values',
                              side_effect=lambda repo: [{'name': k, 'value': v}
                                                        for k, v in self.values.items()]),
            mock.patch.object(duplicate_runs, 'create_value',
                              side_effect=lambda name: self.values.__setitem__(name, 'null')),
            mock.patch.object(duplicate_runs, 'update_values',
                              side_effect=lambda name, value: self.values.__setitem__(name, value)),
            mock.patch.object(duplicate_runs, 'delete_workflow_run', side_effect=fake_delete),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def windows(self) -> dict[str, list]:
        return duplicate_runs.load_windows()

    def prune(self, state_hash: str, previous_hash: str, run_id: int, *, dry_run: bool = False):
        return duplicate_runs.prune(state_hash, previous_hash, run_id=run_id, event='schedule',
                                    dry_run=dry_run)


class PruneTestCase(BookkeepingTestCase):
    def test_run_that_changes_the_key_information_is_kept_and_booked(self):
        result = self.prune('hash-a', 'hash-old', 100)

        self.assertEqual(result.action, 'kept')
        self.assertEqual(self.windows()['hash-a'], [100, None])
        self.assertEqual(self.deleted, [])

    def test_first_duplicate_of_a_state_is_booked(self):
        result = self.prune('hash-a', 'hash-a', 200)

        self.assertEqual(result.action, 'recorded-first')
        self.assertEqual(self.windows()['hash-a'], [200, 200])
        self.assertEqual(self.deleted, [])

    def test_second_duplicate_becomes_the_latest_without_deleting(self):
        self.prune('hash-a', 'hash-a', 200)
        result = self.prune('hash-a', 'hash-a', 300)

        self.assertEqual(result.action, 'recorded')
        self.assertEqual(self.windows()['hash-a'], [200, 300])
        self.assertEqual(self.deleted, [])

    def test_further_duplicates_replace_the_previous_latest(self):
        self.prune('hash-a', 'hash-a', 200)
        self.prune('hash-a', 'hash-a', 300)

        result = self.prune('hash-a', 'hash-a', 400)

        self.assertEqual(result.action, 'deleted')
        self.assertEqual(result.deleted, 300)
        self.assertEqual(result.first, 200)
        self.assertEqual(self.deleted, [300])
        self.assertEqual(self.windows()['hash-a'], [200, 400])

    def test_earliest_run_of_a_state_survives_many_duplicates(self):
        self.prune('hash-a', 'hash-a', 200)
        for run_id in (300, 400, 500):
            self.prune('hash-a', 'hash-a', run_id)

        self.assertEqual(self.deleted, [300, 400])
        self.assertEqual(self.windows()['hash-a'], [200, 500])

    def test_runs_that_changed_the_key_information_are_never_deleted(self):
        # 100 discovered the state, 110 and 120 were duplicates, 130 discovered it again
        self.prune('hash-a', 'hash-old', 100)
        self.prune('hash-a', 'hash-a', 110)
        self.prune('hash-a', 'hash-a', 120)
        self.prune('hash-a', 'hash-old', 130)

        # the discovery run is still the earliest, only the stale duplicate was kept
        self.assertEqual(self.windows()['hash-a'], [100, 120])
        self.assertEqual(self.deleted, [110])

    def test_each_state_keeps_its_own_window(self):
        self.prune('hash-a', 'hash-a', 200)
        self.prune('hash-a', 'hash-a', 300)
        self.prune('hash-b', 'hash-a', 400)  # change: new state, nothing deleted
        self.prune('hash-b', 'hash-b', 500)
        self.prune('hash-b', 'hash-b', 600)

        # only state b produced a duplicate to drop; a's latest (#300) stays until
        # a duplicate of state a shows up again
        self.assertEqual(self.deleted, [500])
        self.assertEqual(self.windows()['hash-a'], [200, 300])
        self.assertEqual(self.windows()['hash-b'], [400, 600])

    def test_reverting_to_an_earlier_state_reuses_its_window(self):
        self.prune('hash-a', 'hash-old', 100)
        self.prune('hash-a', 'hash-a', 110)
        self.prune('hash-b', 'hash-a', 200)
        # upstream reverted to the state of hash-a
        self.prune('hash-a', 'hash-b', 300)

        self.assertEqual(self.windows()['hash-a'], [100, 110])
        self.assertEqual(self.deleted, [])

        self.prune('hash-a', 'hash-a', 400)
        self.assertEqual(self.windows()['hash-a'], [100, 400])
        self.assertEqual(self.deleted, [110])

    def test_failed_delete_still_moves_the_latest_marker(self):
        self.prune('hash-a', 'hash-a', 200)
        self.prune('hash-a', 'hash-a', 300)
        self.delete_ok = False

        result = self.prune('hash-a', 'hash-a', 400)

        self.assertEqual(result.action, 'deleted')
        self.assertIsNone(result.deleted)
        self.assertEqual(self.windows()['hash-a'], [200, 400])

    def test_dry_run_touches_nothing(self):
        self.prune('hash-a', 'hash-a', 200)
        self.prune('hash-a', 'hash-a', 300)
        before = dict(self.values)

        result = self.prune('hash-a', 'hash-a', 400, dry_run=True)

        self.assertEqual(result.action, 'deleted')
        self.assertEqual(self.values, before)
        self.assertEqual(self.deleted, [])

    def test_other_events_are_ignored(self):
        with mock.patch.object(duplicate_runs, 'repo_values') as repo_values:
            result = duplicate_runs.prune('hash-a', 'hash-a', run_id=300, event='workflow_dispatch')

        self.assertEqual(result.action, 'skipped')
        self.assertIn('workflow_dispatch', result.describe())
        repo_values.assert_not_called()

    def test_missing_run_id_is_ignored(self):
        with mock.patch.object(duplicate_runs, 'repo_values') as repo_values:
            result = duplicate_runs.prune('hash-a', 'hash-a', run_id=None, event='schedule')

        self.assertEqual(result.action, 'skipped')
        repo_values.assert_not_called()

    def test_unparsable_bookkeeping_starts_empty(self):
        self.values[duplicate_runs.DUP_VAR] = 'not json'

        result = self.prune('hash-a', 'hash-a', 200)

        self.assertEqual(result.action, 'recorded-first')
        self.assertEqual(self.windows()['hash-a'], [200, 200])

    def test_oldest_windows_are_evicted(self):
        self.values[duplicate_runs.DUP_VAR] = duplicate_runs.json.dumps(
            {f'hash-{i}': [i, i] for i in range(duplicate_runs.MAX_WINDOWS + 5)})

        self.prune('hash-new', 'hash-new', 900)

        windows = self.windows()
        self.assertEqual(len(windows), duplicate_runs.MAX_WINDOWS)
        self.assertIn('hash-new', windows)
        self.assertNotIn('hash-0', windows)


class DescribeTestCase(unittest.TestCase):
    def test_describe_mentions_the_runs_and_the_state(self):
        text = duplicate_runs.PruneResult('deleted', run_id=400, hash='abcdef0123456789',
                                          first=200, deleted=300).describe()
        self.assertIn('#400', text)
        self.assertIn('#200', text)
        self.assertIn('#300', text)
        self.assertIn('abcdef012345', text)

    def test_describe_skip_reason(self):
        text = duplicate_runs.PruneResult('skipped', reason='event is push, not schedule').describe()
        self.assertIn('skipped', text)
        self.assertIn('push', text)


class CliTestCase(BookkeepingTestCase):
    def test_status_prints_the_windows(self):
        self.prune('hash-a', 'hash-a', 200)
        self.prune('hash-a', 'hash-a', 300)

        with mock.patch('builtins.print') as fake_print:
            self.assertEqual(duplicate_runs.main(['--status']), 0)

        printed = ' '.join(str(c.args[0]) for c in fake_print.call_args_list)
        self.assertIn('hash-a', printed)
        self.assertIn('200', printed)
        self.assertIn('300', printed)

    def test_cli_treats_the_run_as_unchanged_by_default(self):
        with mock.patch.object(duplicate_runs, 'prune',
                               return_value=duplicate_runs.PruneResult('recorded')) as prune:
            self.assertEqual(duplicate_runs.main(['--hash', 'hash-a', '--run-id', '300']), 0)

        prune.assert_called_once_with('hash-a', 'hash-a', run_id=300, event=None, dry_run=False)

    def test_cli_forwards_the_previous_hash_and_dry_run(self):
        with mock.patch.object(duplicate_runs, 'prune',
                               return_value=duplicate_runs.PruneResult('kept')) as prune:
            duplicate_runs.main(['--hash', 'hash-a', '--previous-hash', 'hash-b', '--dry-run'])

        self.assertEqual(prune.call_args.args, ('hash-a', 'hash-b'))
        self.assertTrue(prune.call_args.kwargs['dry_run'])


if __name__ == '__main__':
    unittest.main()
