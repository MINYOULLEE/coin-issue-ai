import unittest
import verify_learned_targets_stage29 as r

class MinuteTargetTests(unittest.TestCase):
    def setUp(self):
        self.p=dict(symbol='ICP',entry_ts=0,exit_bar=0,side=1)
        self.rows={i*r.M:dict(o=100.,h=100.5,l=99.5,c=100.) for i in range(60)}
        self.rows[2*r.M]=dict(o=100.,h=102.,l=99.5,c=101.)
    def test_first_touch_and_arming(self):
        self.assertEqual(r.execution(self.rows,self.p,101.5,'minute_touch'),(2*r.M,101.5))
        self.assertIsNone(r.execution(self.rows,self.p,101.5,'arm_5m'))
    def test_delayed_exit_uses_later_open(self):
        self.rows[7*r.M]['o']=98.
        self.assertEqual(r.execution(self.rows,self.p,101.5,'delay_5m'),(7*r.M,98.))
    def test_deadline_priority(self):
        self.rows[2*r.M]['h']=100.5;self.rows[59*r.M]['h']=102.
        self.assertIsNone(r.execution(self.rows,self.p,101.5,'delay_1m'))
    def test_short_direction_and_adverse_haircut(self):
        p={**self.p,'side':-1};self.rows[2*r.M]['l']=98.
        self.assertEqual(r.execution(self.rows,p,98.5,'minute_touch'),(2*r.M,98.5))
        self.assertAlmostEqual(r.execution(self.rows,p,98.5,'haircut_10bp')[1],98.5985)
    def test_overshoot_requires_more_than_touch(self):
        self.rows[2*r.M]['h']=101.5
        self.assertIsNone(r.execution(self.rows,self.p,101.5,'overshoot_5bp'))
    def test_hour_aggregation_and_mismatch(self):
        hour=dict(o=100.,h=102.,l=99.5,c=100.)
        self.assertTrue(r.validate_hour(self.rows,0,hour))
        self.assertFalse(r.validate_hour(self.rows,0,{**hour,'h':103.}))

if __name__=='__main__':unittest.main()
