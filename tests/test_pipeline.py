import datetime
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "files"))

import dedup  # noqa: E402
import guy_of_day  # noqa: E402


class DedupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.write(b'{"2026-10-18": [{"l": "vnexpress.net/old-story", '
                       b'"k": ["ngan", "hang", "nha", "nuoc", "giam", "lai", "suat"], "t": "x"}]}')
        self.tmp.close()
        self.dd = dedup.Dedup("2026-10-19", history_path=self.tmp.name)

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_same_link_from_history_is_dup(self):
        self.assertTrue(self.dd.is_dup("Tiêu đề khác hẳn", "https://www.vnexpress.net/old-story?utm=x"))

    def test_near_duplicate_title_across_outlets(self):
        self.assertTrue(self.dd.take("Đà Nẵng kết nối với Silicon Valley phát triển công nghệ chiến lược",
                                     "https://a.vn/1"))
        self.assertFalse(self.dd.take("Đà Nẵng kết nối Silicon Valley trong phát triển các ngành công nghệ chiến lược",
                                      "https://b.vn/2"))

    def test_history_title_blocks_rewrite(self):
        self.assertTrue(self.dd.is_dup("Ngân hàng Nhà nước yêu cầu giảm lãi suất", "https://c.vn/3"))

    def test_unrelated_story_passes(self):
        self.assertTrue(self.dd.take("Giá vàng hôm nay tăng mạnh", "https://d.vn/4"))

    def test_rerun_same_day_does_not_block_itself(self):
        self.dd.take("Tin A về thời tiết miền Trung", "https://e.vn/5")
        self.dd.save()
        again = dedup.Dedup("2026-10-19", history_path=self.tmp.name)
        self.assertFalse(again.is_dup("Tin A về thời tiết miền Trung", "https://e.vn/5"))
        nextday = dedup.Dedup("2026-10-20", history_path=self.tmp.name)
        self.assertTrue(nextday.is_dup("Tin A về thời tiết miền Trung", "https://e.vn/5"))

    def test_age_hours(self):
        now = datetime.datetime(2026, 10, 19, 1, 0, tzinfo=datetime.timezone.utc)
        entry = {"published_parsed": time.strptime("2026-10-18 01:00", "%Y-%m-%d %H:%M")}
        self.assertAlmostEqual(dedup.age_hours(entry, now), 24, places=3)
        self.assertIsNone(dedup.age_hours({}, now))
        baomoi = {"pub_dt": datetime.datetime(2026, 10, 19, 7, 0)}  # naive GMT+7
        self.assertAlmostEqual(dedup.age_hours(baomoi, now), 1, places=3)


class RoundRobinTest(unittest.TestCase):
    def test_one_story_per_feed_before_seconds(self):
        import fetch_content as fc
        recent = time.gmtime(time.time() - 3600)

        words = {"a": ["vang", "dau", "gao", "thep", "dien"], "b": ["bao", "lu", "nang", "mua", "gio"],
                 "c": ["phim", "nhac", "show", "concert", "album"]}

        def fake_parse(url, **_):
            n = url[-1]
            return mock.Mock(entries=[{"title": f"{words[n][i]} chuyen muc {n}{n}{n} so{i}",
                                       "link": f"https://x/{n}/{i}", "summary": "",
                                       "published_parsed": recent} for i in range(5)])
        with tempfile.NamedTemporaryFile(suffix=".json") as tmp, \
                mock.patch.object(fc.feedparser, "parse", side_effect=fake_parse):
            dd = dedup.Dedup("2026-10-19", history_path=tmp.name)
            feeds = [(f"https://feed/{c}", f"P{c}") for c in "abc"]
            got = fc._fetch_rss_articles(dd, target=4, feeds=feeds)
        self.assertEqual([g["publisher"] for g in got], ["Pa", "Pb", "Pc", "Pa"])

    def test_stale_entries_dropped(self):
        import fetch_content as fc
        old = time.gmtime(time.time() - 5 * 86400)
        with tempfile.NamedTemporaryFile(suffix=".json") as tmp, \
                mock.patch.object(fc.feedparser, "parse", return_value=mock.Mock(
                    entries=[{"title": "Old news", "link": "https://x/1", "published_parsed": old}])):
            dd = dedup.Dedup("2026-10-19", history_path=tmp.name)
            self.assertEqual(fc._fetch_rss_articles(dd, target=3, feeds=[("u", "P")]), [])


class GuyTest(unittest.TestCase):
    def test_zodiac_and_age(self):
        bd = guy_of_day.parse_birthday("12/09/1994")
        self.assertEqual(guy_of_day.zodiac(bd), "Xử Nữ ♍")
        self.assertEqual(guy_of_day.zodiac(datetime.date(2000, 1, 1)), "Ma Kết ♑")
        self.assertEqual(guy_of_day.zodiac(datetime.date(2000, 12, 25)), "Ma Kết ♑")
        self.assertEqual(guy_of_day.age_on(bd, datetime.date(2026, 10, 19)), 32)
        self.assertEqual(guy_of_day.age_on(bd, datetime.date(2026, 9, 11)), 31)

    def test_birthday_wins_and_rotation_covers_all(self):
        guys = [{"name": f"G{i}", "birthday": f"0{i + 1}/01/1995"} for i in range(5)]
        g, is_bday = guy_of_day.pick(guys, datetime.date(2026, 1, 3))
        self.assertTrue(is_bday)
        self.assertEqual(g["name"], "G2")
        seen = {guy_of_day.pick(guys, datetime.date(2026, 3, 1) + datetime.timedelta(days=d))[0]["name"]
                for d in range(5)}
        self.assertEqual(len(seen), 5)


class HotNewsMatchTest(unittest.TestCase):
    def test_name_match_is_exact(self):
        self.assertTrue(guy_of_day._mentions("Lý Hiện", "Lý Hiện đóng phim mới cùng Châu Đông Vũ"))
        self.assertFalse(guy_of_day._mentions("Lý Hiện", "Thuế củng cố nguồn thu trên nền tảng quản lý hiện đại"))
        self.assertFalse(guy_of_day._mentions("Jin", "Jinny ra mắt MV"))


class HealthGateTest(unittest.TestCase):
    def test_empty_ai_sections_block(self):
        import ai_news_bot as bot
        data = {"articles": [{"ai_summary": True}] * 8, "danang_articles": [1],
                "guy": {"name": "X", "image_url": "assets/missing.jpg"},
                "llm_stats": {"disabled": {"gemini": "403"}}}
        problems, blocking = bot.health_check(data)
        self.assertTrue(any("Empty AI sections" in p for p in blocking))
        self.assertTrue(any("image missing" in p for p in blocking))
        self.assertFalse(any(p.startswith("LLM provider") for p in blocking))


if __name__ == "__main__":
    unittest.main()
