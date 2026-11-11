"""Regression tests for skills/yt-viral/swipe.py (upstream English behaviour)."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SWIPE = os.path.join(ROOT, "skills", "yt-viral", "swipe.py")
HOOKSCORE = os.path.join(ROOT, "skills", "yt-script", "hookscore.py")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def v(title, views, channel="C"):
    return {"channel": channel, "title": title, "views": views}


class SwipeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, data, name="in.json"):
        p = os.path.join(self.tmp.name, name)
        with open(p, "w") as fh:
            json.dump(data, fh)
        return p

    def run_swipe(self, *args):
        return subprocess.run([sys.executable, "-I", SWIPE] + list(args), cwd=self.tmp.name,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

    def run_json(self, *args):
        r = self.run_swipe(*args, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    # bug 1: yt-dlp -J output
    def test_ytdlp_playlist_entries(self):
        data = {"_type": "playlist", "channel": "Chan A", "entries": [
            {"title": "t1", "view_count": 10000},
            {"title": "t2", "view_count": 12000},
            {"title": "t3", "view_count": 11000},
            {"title": "t4", "view_count": 90000, "webpage_url": "https://y/t4"}]}
        out = self.run_json(self.write(data))
        self.assertEqual(len(out["outliers"]), 1)
        o = out["outliers"][0]
        self.assertEqual(o["title"], "t4")
        self.assertEqual(o["channel"], "Chan A")
        self.assertAlmostEqual(o["multiple"], 90000 / 11500, places=2)
        self.assertEqual(o["url"], "https://y/t4")
        txt = self.run_swipe(self.write(data)).stdout
        # Report is now Persian (Farsi pack, intentional): "4 videos across 1 channels" -> «۴ ویدیو از ۱ کانال».
        self.assertIn("۴ ویدیو از ۱ کانال", txt)

    def test_no_view_counts_is_an_error(self):
        r = self.run_swipe(self.write({"entries": [{"title": "x"}, {"title": "y"}]}))
        self.assertEqual(r.returncode, 2)
        # Message is now Persian (intentional): "no videos with a view count".
        self.assertIn("هیچ ویدیو یا ریلزی با عدد بازدید پیدا نشد", r.stderr)

    def test_videos_key_still_works(self):
        data = {"videos": [v("a", 1000), v("b", 1000), v("c", 1000), v("d", 5000)]}
        out = self.run_json(self.write(data))
        self.assertEqual([o["title"] for o in out["outliers"]], ["d"])

    # bug 2: null views are not zeros
    def test_null_views_excluded_from_median(self):
        data = [v("a", 5000), v("b", None), v("c", None), v("d", 1000), v("e", None)]
        out = self.run_json(self.write(data))
        self.assertEqual(out["outliers"], [])
        self.assertEqual(out["skipped_thin_channels"], [["C", 2]])
        self.assertEqual(out["skipped_unknown_views"], 3)

    def test_null_views_do_not_hide_outlier(self):
        data = [v("a", 1000), v("b", 1000), v("c", 1000), v("d", 9000), v("e", None), v("f", None),
                v("g", None), v("h", None), v("i", None)]
        out = self.run_json(self.write(data))
        self.assertEqual([o["title"] for o in out["outliers"]], ["d"])
        self.assertEqual(out["outliers"][0]["median"], 1000)

    def test_string_views_with_commas(self):
        data = [v("a", "1,000"), v("b", "1,000"), v("c", "1,000"), v("d", "9,000")]
        out = self.run_json(self.write(data))
        self.assertEqual(out["outliers"][0]["views"], 9000)

    # bug 3: null title
    def test_null_title(self):
        data = [v(None, 5000), v("b", 1000), v("c", 1000), v("d", 1000)]
        r = self.run_swipe(self.write(data))
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.run_json(self.write(data))
        self.assertEqual(out["outliers"][0]["title"], "")
        self.assertEqual(out["outliers"][0]["formula"], "Unclassified")
        self.assertEqual(out["outliers"][0]["url"], "")

    # bug 4: null channel
    def test_null_channel(self):
        data = [{"channel": None, "title": "x", "views": 5000}] + [{"channel": None, "title": "y", "views": 1000}] * 3
        r = self.run_swipe(self.write(data))
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.run_json(self.write(data))
        self.assertEqual(out["outliers"][0]["channel"], "?")

    # bug 5: argument handling
    def _base(self):
        return self.write([v("a", 1000), v("b", 1000), v("c", 1000), v("d", 2000)], "ok.json")

    def test_min_equals_form(self):
        p = self._base()
        r = self.run_swipe(p, "--min=3")
        self.assertEqual(r.returncode, 0, r.stderr)
        # Persian report (intentional): "outliers at 3.0x or better" / "nothing cleared".
        self.assertIn("از ۳٫۰ برابرِ میانه به بالا", r.stdout)
        self.assertIn("هیچ موردی به این آستانه نرسید", r.stdout)

    def test_min_space_form_still_works(self):
        r = self.run_swipe(self._base(), "--min", "2.0")
        # Persian report with Persian digits (intentional): "outliers at 2.0x", "2.00x".
        self.assertIn("از ۲٫۰ برابرِ میانه به بالا", r.stdout)
        self.assertIn("۲٫۰۰×", r.stdout)

    def test_min_without_value_is_usage_error(self):
        r = self.run_swipe(self._base(), "--min")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("IndexError", r.stderr)

    def test_numeric_file_name(self):
        self.write([v("a", 1000), v("b", 1000), v("c", 1000), v("d", 2000)], "2024")
        r = self.run_swipe("2024")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("۴ ویدیو از ۱ کانال", r.stdout)  # Persian report (intentional)

    def test_missing_file_prints_usage(self):
        r = self.run_swipe("nope.json")
        self.assertEqual(r.returncode, 1)
        self.assertIn("swipe.py", r.stdout)

    # bug 6: tie-break matches hookscore
    def test_tie_break_matches_hookscore(self):
        swipe = _load(SWIPE, "swipe_under_test")
        hook = _load(HOOKSCORE, "hookscore_under_test")
        self.assertEqual(swipe.classify("Why I tried it"), "I Tried It")
        self.assertEqual(hook.classify("Why I tried it")[0], "I Tried It")
        for f in swipe.FORMULAS:
            for t in (f["name"], "Why I tried it", "How I made $1,000 in 7 days", "nothing here"):
                self.assertEqual(swipe.classify(t), hook.classify(t)[0], t)


if __name__ == "__main__":
    unittest.main()
