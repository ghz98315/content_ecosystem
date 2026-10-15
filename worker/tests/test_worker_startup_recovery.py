import unittest
from unittest.mock import patch

import httpx
import main as worker


class WorkerStartupRecoveryTests(unittest.TestCase):
    def test_startup_retries_before_claiming(self):
        with patch.object(worker.config, 'require_config'), \
             patch.object(worker.config, 'WORKER_TASK_ID', ''), \
             patch.object(worker, 'recover_orphaned_stages', side_effect=[httpx.ConnectError('offline'), []]) as recover, \
             patch.object(worker, 'tick', side_effect=KeyboardInterrupt) as tick, \
             patch.object(worker.db, 'reset_client') as reset, \
             patch.object(worker.time, 'sleep') as sleep:
            worker.main()
        self.assertEqual(recover.call_count, 2)
        tick.assert_called_once()
        reset.assert_called_once()
        sleep.assert_called_once_with(2)

    def test_completion_check_network_failure_retries(self):
        with patch.object(worker.config, 'require_config'), \
             patch.object(worker.config, 'WORKER_TASK_ID', 'task'), \
             patch.object(worker, 'recover_orphaned_stages', return_value=[]) as recover, \
             patch.object(worker, 'tick', return_value=False), \
             patch.object(worker, 'scoped_worker_is_finished', side_effect=[httpx.ConnectError('offline'), True]), \
             patch.object(worker.db, 'reset_client') as reset, \
             patch.object(worker.time, 'sleep') as sleep:
            worker.main()
        recover.assert_called_once()
        reset.assert_called_once()
        sleep.assert_called_once_with(2)

    def test_startup_backoff_is_bounded(self):
        with patch.object(worker.config, 'require_config'), \
             patch.object(worker.config, 'WORKER_TASK_ID', ''), \
             patch.object(worker, 'recover_orphaned_stages', side_effect=[httpx.ConnectError('offline')] * 7 + [KeyboardInterrupt]), \
             patch.object(worker, 'tick') as tick, \
             patch.object(worker.db, 'reset_client'), \
             patch.object(worker.time, 'sleep') as sleep:
            worker.main()
        tick.assert_not_called()
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [2, 4, 8, 16, 30, 30, 30])


if __name__ == '__main__':
    unittest.main()
