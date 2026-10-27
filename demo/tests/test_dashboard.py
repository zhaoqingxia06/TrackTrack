import unittest
from datetime import datetime
from analytics import summarize_dashboard, ZONE

class DashboardTest(unittest.TestCase):
    def test_distinct_period_and_first_observed_across_all_history(self):
        def event(day, user, kind="click"):
            return {"timestamp":f"2026-10-{day}T10:00:00+08:00", "device_id":user, "user":user, "type":kind}
        events=[event("24","a"),event("25","a"),event("25","b"),event("25","b"),event("26","a"),event("26","c","session_active")]
        d=summarize_dashboard(events,datetime(2026,10,27,12,tzinfo=ZONE),"2026-10-25","2026-10-27")["dashboard"]
        self.assertEqual(d["period_active"],2)
        self.assertEqual(d["first_observed"],1)
        self.assertEqual([x["active"] for x in d["daily"]],[2,1,None])
        self.assertTrue(d["coverage_start"].startswith("2026-10-24"))
    def test_empty_coverage_is_unknown(self):
        d=summarize_dashboard([],datetime(2026,10,27,12,tzinfo=ZONE))["dashboard"]
        self.assertIsNone(d["period_active"])
        self.assertIsNone(d["first_observed"])
        self.assertIsNone(d["daily"][0]["active"])

    def test_fixed_today_week_and_year_ignore_filter(self):
        def event(stamp, identity):
            return {"timestamp":stamp+"T10:00:00+08:00", "device_id":identity, "type":"page_view"}
        events=[event("2025-12-31","old"),event("2026-01-01","old"),event("2026-10-22","a"),event("2026-10-28","a"),event("2026-10-28","b"),event("2026-10-28","b")]
        d=summarize_dashboard(events,datetime(2026,10,28,12,tzinfo=ZONE),"2026-10-22","2026-10-22")["dashboard"]
        self.assertEqual(d["today_active"],2)
        self.assertEqual(d["today_first_observed"],1)
        self.assertEqual(d["year_active"],3)
        self.assertEqual([x["date"] for x in d["recent_daily"]],[f"2026-10-{n}" for n in range(22,29)])
        self.assertEqual([x["active"] for x in d["recent_daily"]],[1,None,None,None,None,None,2])

    def test_visits_count_unique_entry_and_keep_unconfirmed(self):
        def entry(stamp, identity, trajectory=None):
            return {"timestamp":stamp+"T10:00:00+08:00", "device_id":identity, "type":"page_view", "trajectory_id":trajectory}
        events=[entry("2026-10-22","a","one"),entry("2026-10-28","a","two"),entry("2026-10-28","a","two"),entry("2026-10-28","a","three"),entry("2026-10-28","b","four"),entry("2026-10-28","b")]
        d=summarize_dashboard(events,datetime(2026,10,28,12,tzinfo=ZONE))["dashboard"]
        self.assertEqual(d["today_visits"],3)
        self.assertEqual(d["today_visits_per_user"],1.5)
        self.assertEqual(d["year_visits"],4)
        self.assertTrue(d["year_visits_partial"])
        self.assertTrue(d["recent_daily"][-1]["visits_partial"])
        self.assertEqual(d["recent_daily"][0]["visits"],1)
        self.assertIsNone(d["recent_daily"][1]["visits"])
