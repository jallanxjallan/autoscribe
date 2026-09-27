import unittest
from autoscribe.call import build_call_record
class CallTests(unittest.TestCase):
    def test_shape(self):
        sources=[{"identity":"psg.test","path":"Note.md","blob":"b1","directive":None,"content":"Body\n"}]
        call=build_call_record(repo="/home/jeremy/Repos/X",repo_name="X",commit="abc",ref="refs/heads/master",plan={"id":"p1","steps":[]},sources=sources)
        self.assertEqual(call["schema"],"autoscribe.call.v2"); self.assertEqual(call["source"]["commit"],"abc"); self.assertEqual(call["sources"],sources); self.assertIn("created_at",call)
if __name__=="__main__": unittest.main()
