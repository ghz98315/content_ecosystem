import unittest
from unittest.mock import patch
import worker_guardian as guard

class GuardianTests(unittest.TestCase):
 def run_case(self,alive,locked,last=0,now=100):
  state={}
  with patch.object(guard,'inspect_worker',return_value=alive),patch.object(guard,'service_locked',return_value=locked),patch.object(guard,'start_service') as start:
   result=guard.guard_once(state,last,now)
  return state,result,start.call_count
 def test_healthy_worker_not_restarted(self):
  state,_,calls=self.run_case(True,True);self.assertEqual('online',state['status']);self.assertEqual(0,calls)
 def test_dead_worker_launched(self):
  state,last,calls=self.run_case(False,False);self.assertEqual('recovering',state['status']);self.assertEqual(100,last);self.assertEqual(1,calls)
 def test_supervisor_lock_prevents_duplicate(self):
  self.assertEqual(0,self.run_case(False,True)[2])
 def test_restart_backoff(self):
  self.assertEqual(0,self.run_case(False,False,last=95)[2])

if __name__=='__main__':unittest.main()
