import datetime
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "files"))

from handsome_guys import GUYS  # noqa: E402

REQUIRED = ("name", "origin", "job", "birthday", "summary", "wiki_url",
            "wikidata", "image_url", "image_credit", "tags")
ALLOWED = set(REQUIRED) | {"height"}
FORBIDDEN = {"weight", "blood_type", "zodiac", "fav_color", "fav_number", "status",
             "hobbies", "awards", "top_works", "intro"}


class GuysDatasetTest(unittest.TestCase):
    def test_not_empty(self):
        self.assertGreaterEqual(len(GUYS), 60)

    def test_required_fields_non_empty(self):
        for g in GUYS:
            for k in REQUIRED:
                with self.subTest(name=g.get("name"), field=k):
                    self.assertTrue(g.get(k), f"{g.get('name')}: empty {k}")
            self.assertIsInstance(g.get("height", ""), str)

    def test_no_legacy_or_unknown_fields(self):
        for g in GUYS:
            with self.subTest(name=g["name"]):
                self.assertFalse(FORBIDDEN & set(g), f"legacy fields {FORBIDDEN & set(g)}")
                self.assertFalse(set(g) - ALLOWED, f"unknown fields {set(g) - ALLOWED}")

    def test_birthday_parses(self):
        for g in GUYS:
            with self.subTest(name=g["name"]):
                bd = datetime.datetime.strptime(g["birthday"], "%d/%m/%Y").date()
                self.assertGreaterEqual(bd.year, 1985)
                self.assertLess(bd, datetime.date.today())

    def test_height_format(self):
        for g in GUYS:
            if g["height"]:
                with self.subTest(name=g["name"]):
                    self.assertRegex(g["height"], r"^1m\d{2}$")

    def test_image_exists_and_is_image(self):
        for g in GUYS:
            with self.subTest(name=g["name"]):
                self.assertTrue(g["image_url"].startswith("assets/guys/v2/"))
                path = os.path.join(ROOT, "docs", g["image_url"])
                self.assertTrue(os.path.isfile(path), path)
                with open(path, "rb") as f:
                    head = f.read(12)
                self.assertTrue(head[:3] == b"\xff\xd8\xff" or head[:8] == b"\x89PNG\r\n\x1a\n"
                                or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"), path)
                self.assertLess(os.path.getsize(path), 1_500_000, path)

    def test_no_duplicates(self):
        for key in ("name", "wikidata", "image_url"):
            vals = [g[key] for g in GUYS]
            with self.subTest(key=key):
                self.assertEqual(len(vals), len(set(vals)),
                                 [v for v in set(vals) if vals.count(v) > 1])

    def test_urls(self):
        for g in GUYS:
            with self.subTest(name=g["name"]):
                self.assertRegex(g["wiki_url"], r"^https://(vi|en)\.wikipedia\.org/wiki/")
                self.assertRegex(g["wikidata"], r"^https://www\.wikidata\.org/wiki/Q\d+$")


if __name__ == "__main__":
    unittest.main()
