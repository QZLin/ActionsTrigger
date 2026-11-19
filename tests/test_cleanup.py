import unittest
from unittest import mock

from actions_trigger import cleanup


def run(run_id, created, conclusion='success'):
    return cleanup.WorkflowRun(run_id, created, 'completed', conclusion, 'schedule')


class CleanupLogicTestCase(unittest.TestCase):
    def test_segments_keep_first_and_last_and_delete_middle(self):
        items = [
            cleanup.RunClassification(run(1, '2026-01-01T00:00:00Z'), True, ('#A executed 1/1 action(s)',)),
            cleanup.RunClassification(run(2, '2026-01-01T00:05:00Z'), False, ('#A skipped',)),
            cleanup.RunClassification(run(3, '2026-01-01T00:10:00Z'), False, ('#A skipped',)),
            cleanup.RunClassification(run(4, '2026-01-01T00:15:00Z'), False, ('#A skipped',)),
            cleanup.RunClassification(run(5, '2026-01-01T00:20:00Z'), True, ('#A executed 1/1 action(s)',)),
            cleanup.RunClassification(run(6, '2026-01-01T00:25:00Z'), False, ('#A skipped',)),
        ]

        segments = cleanup.unchanged_segments(items)

        self.assertEqual([[x.id for x in s] for s in segments], [[2, 3, 4], [6]])
        self.assertEqual([x.id for x in cleanup.candidate_runs(items)], [3])

    def test_unknown_and_failed_runs_break_safe_segments(self):
        items = [
            cleanup.RunClassification(run(1, '2026-01-01T00:00:00Z'), False, ()),
            cleanup.RunClassification(run(2, '2026-01-01T00:05:00Z', 'failure'), False, ()),
            cleanup.RunClassification(run(3, '2026-01-01T00:10:00Z'), False, ('#A skipped',)),
            cleanup.RunClassification(run(4, '2026-01-01T00:15:00Z'), False, ('#A skipped',)),
        ]

        self.assertEqual([x.id for x in cleanup.candidate_runs(items)], [])

    def test_changed_annotation_is_not_a_duplicate(self):
        item = cleanup.RunClassification(run(1, '2026-01-01T00:00:00Z'), True,
                                         ('#A executed 1/1 action(s)', '#B skipped'))
        self.assertEqual(cleanup.candidate_runs([item]), [])

    def test_classify_failed_does_not_request_annotations(self):
        failed = run(1, '2026-01-01T00:00:00Z', 'failure')
        with mock.patch.object(cleanup, 'run_annotations') as annotations:
            result = cleanup.classify_run('o/r', failed)
        annotations.assert_not_called()
        self.assertEqual(result.unit_annotations, ())


class ApiWorkflowTestCase(unittest.TestCase):
    def test_list_runs_follows_pagination_and_ignores_in_progress(self):
        first = mock.Mock(status_code=200)
        first.json.return_value = {'workflow_runs': [
            {'id': 2, 'created_at': '2026-01-02T00:00:00Z', 'status': 'completed',
             'conclusion': 'success', 'event': 'schedule'},
            {'id': 3, 'created_at': '2026-01-03T00:00:00Z', 'status': 'in_progress',
             'conclusion': None, 'event': 'schedule'},
        ]}
        first.headers = {'Link': '<next-url>; rel="next"'}
        second = mock.Mock(status_code=200)
        second.json.return_value = {'workflow_runs': [{
            'id': 1, 'created_at': '2026-01-01T00:00:00Z', 'status': 'completed',
            'conclusion': 'success', 'event': 'schedule'}]}
        second.headers = {}

        with mock.patch.object(cleanup, '_get', side_effect=[first, second]):
            result = cleanup.list_scheduled_runs('o/r')

        self.assertEqual([x.id for x in result], [1, 2])

    def test_annotations_are_collected_from_all_jobs(self):
        jobs = mock.Mock(status_code=200)
        jobs.json.return_value = {'jobs': [{'id': 10}, {'id': 11}]}
        ann1 = mock.Mock(status_code=200)
        ann1.json.return_value = [{'message': '#A skipped'}]
        ann2 = mock.Mock(status_code=200)
        ann2.json.return_value = [{'message': '#B executed 1/1 action(s)'}]

        with mock.patch.object(cleanup, '_get', side_effect=[jobs, ann1, ann2]):
            result = cleanup.run_annotations('o/r', 1)

        self.assertEqual(result, ['#A skipped', '#B executed 1/1 action(s)'])

    def test_cleanup_dry_run_does_not_delete(self):
        runs = [run(i, f'2026-01-01T00:{i:02d}:00Z') for i in range(1, 4)]
        classifications = [cleanup.RunClassification(x, False, ('#A skipped',)) for x in runs]
        with mock.patch.object(cleanup, 'list_scheduled_runs', return_value=runs), \
                mock.patch.object(cleanup, 'classify_run', side_effect=classifications), \
                mock.patch.object(cleanup, 'delete_workflow_run') as delete:
            result = cleanup.cleanup('o/r')

        self.assertTrue(result.dry_run)
        self.assertEqual([x.id for x in result.candidates], [2])
        delete.assert_not_called()

    def test_cleanup_delete_mode_deletes_candidates(self):
        runs = [run(i, f'2026-01-01T00:{i:02d}:00Z') for i in range(1, 4)]
        classifications = [cleanup.RunClassification(x, False, ('#A skipped',)) for x in runs]
        with mock.patch.object(cleanup, 'list_scheduled_runs', return_value=runs), \
                mock.patch.object(cleanup, 'classify_run', side_effect=classifications), \
                mock.patch.object(cleanup, 'delete_workflow_run', return_value=True) as delete:
            result = cleanup.cleanup('o/r', delete=True)

        self.assertFalse(result.dry_run)
        self.assertEqual(result.deleted, [2])
        delete.assert_called_once_with('o/r', 2)

    def test_before_filters_runs(self):
        runs = [run(1, '2026-01-01T00:00:00Z'), run(2, '2026-01-03T00:00:00Z')]
        with mock.patch.object(cleanup, 'list_scheduled_runs', return_value=runs), \
                mock.patch.object(cleanup, 'classify_run', return_value=cleanup.RunClassification(runs[0], False, ('#A skipped',))):
            result = cleanup.cleanup('o/r', before='2026-01-02T00:00:00Z')

        self.assertEqual(result.scanned, 1)


if __name__ == '__main__':
    unittest.main()
