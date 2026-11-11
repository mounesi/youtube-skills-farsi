"""Tests for skills/yt-viral/swipe.py (Persian / Instagram behaviour)."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL = os.path.join(ROOT, "skills", "yt-viral")
SWIPE = os.path.join(SKILL, "swipe.py")
HOOKSCORE = os.path.join(ROOT, "skills", "yt-script", "hookscore.py")
FIX = os.path.join(ROOT, "tests", "fixtures", "yt-viral")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SwipeFaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, data, name="in.json"):
        p = os.path.join(self.tmp.name, name)
        with open(p, "w", encoding="utf-8") as fh:
            if isinstance(data, str):
                fh.write(data)
            else:
                json.dump(data, fh, ensure_ascii=False)
        return p

    def run_swipe(self, *args, script=SWIPE):
        return subprocess.run([sys.executable, "-I", script] + list(args), cwd=self.tmp.name,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

    def run_json(self, *args, script=SWIPE):
        r = self.run_swipe(*(list(args) + ["--json"]), script=script)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    # --- view formats ---------------------------------------------------------------------------
    def test_persian_view_formats(self):
        out = self.run_json(os.path.join(FIX, "youtube_fa.json"), "--min", "2")
        self.assertEqual([o["title"] for o in out["outliers"]], ["چرا ۹۷٪ کانال‌ها قبل از ویدیوی ۳۰ ول می‌کنند؟"])
        o = out["outliers"][0]
        # ۱۲ هزار, ۹۶ هزار, ۱۰٬۵۰۰, 1.1K -> median of 12000, 96000, 10500, 1100 = 11250
        self.assertEqual(o["views"], 96000)
        self.assertEqual(o["median"], 11250)
        self.assertEqual(out["skipped_unknown_views"], 1)
        self.assertEqual(out["skipped_thin_channels"], [["کانال نمونه ب", 3]])

    def test_parse_views_never_guesses(self):
        swipe = _load(SWIPE, "swipe_fa_views")
        self.assertEqual(swipe._num("۱۲ هزار بازدید"), 12000)
        self.assertEqual(swipe._num("1.2K views"), 1200)
        self.assertEqual(swipe._num("۱٫۲ میلیون"), 1200000)
        self.assertEqual(swipe._num(412000), 412000)
        for bad in (None, "", "—", "N/A", True, -5, "1,2,3"):
            self.assertIsNone(swipe._num(bad), bad)

    def test_ytdlp_nested_channel_tabs(self):
        data = {"_type": "playlist", "channel": "کانال تست", "entries": [
            {"_type": "playlist", "title": "Videos", "entries": [
                {"title": "a", "view_count": 1000}, {"title": "b", "view_count": 1000}]},
            {"_type": "playlist", "title": "Shorts", "entries": [
                {"title": "c", "view_count": 1000}, {"title": "d", "view_count": 7000}]}]}
        out = self.run_json(self.write(data))
        self.assertEqual([(o["channel"], o["title"], o["platform"]) for o in out["outliers"]],
                         [("کانال تست", "d", "youtube")])

    # --- Instagram ------------------------------------------------------------------------------
    def test_instagram_reels_list(self):
        out = self.run_json(os.path.join(FIX, "instagram_reels.json"), "--min", "2")
        got = [(o["channel"], o["platform"], o["views"], o["median"]) for o in out["outliers"]]
        self.assertEqual(got, [("@example.page", "instagram", 57000, 4650), ("other.page", "instagram", 8000, 1050)])
        # caption: only the first line is the "title"
        self.assertEqual(out["outliers"][0]["title"], "کامنت کن «آرتیفکت» تا آموزشش رو برات بفرستم")
        self.assertEqual(out["outliers"][1]["url"], "https://www.instagram.com/reel/EXAMPLE/")

    def test_instagram_csv_persian_headers_and_persian_min(self):
        out = self.run_json(os.path.join(FIX, "reels_fa.csv"), "--min", "۳")
        self.assertEqual([(o["channel"], o["views"], o["platform"]) for o in out["outliers"]],
                         [("@csv.page", 6000, "instagram")])

    def test_instagram_needs_four_per_account(self):
        data = [{"account": "@a", "caption": "x", "plays": n} for n in (100, 100, 900)]
        out = self.run_json(self.write(data))
        self.assertEqual(out["outliers"], [])
        self.assertEqual(out["skipped_thin_channels"], [["@a", 3]])
        txt = self.run_swipe(self.write(data)).stdout
        self.assertIn("کمتر از ۴ ریلز داشت", txt)

    def test_same_name_on_two_platforms_is_two_medians(self):
        yt = [{"channel": "DrX", "title": "t%d" % i, "views": 1000} for i in range(4)]
        ig = [{"account": "DrX", "caption": "c%d" % i, "plays": 50000} for i in range(3)] + \
             [{"account": "DrX", "caption": "big", "plays": 200000}]
        out = self.run_json(self.write(yt + ig))
        self.assertEqual([(o["title"], o["platform"]) for o in out["outliers"]], [("big", "instagram")])
        txt = self.run_swipe(self.write(yt + ig)).stdout
        self.assertIn("ویدیو/ریلز", txt)

    # --- Persian report -------------------------------------------------------------------------
    def test_report_is_persian(self):
        r = self.run_swipe(os.path.join(FIX, "youtube_fa.json"), "--min", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("۸ ویدیو از ۲ کانال", r.stdout)
        self.assertIn("۸٫۵۳×", r.stdout)
        self.assertIn("۹۶٬۰۰۰ بازدید", r.stdout)
        self.assertIn("فرمول:", r.stdout)
        self.assertNotIn("ي", r.stdout)
        self.assertNotIn("ك", r.stdout)
        for en in ("outliers", "median", "skipped", "videos across"):
            self.assertNotIn(en, r.stdout)

    def test_bad_json_is_clean_error(self):
        r = self.run_swipe(self.write("{نه جیسون", "bad.json"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("خوانده نشد", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_directory_is_not_a_file(self):
        r = self.run_swipe(self.tmp.name)
        self.assertEqual(r.returncode, 1)
        self.assertIn("پیدا نشد", r.stderr)

    # --- supply check ---------------------------------------------------------------------------
    def test_phrase_supply(self):
        swipe = _load(SWIPE, "swipe_fa_phrase")
        self.assertTrue(swipe.has_phrase("آموزش‌ کلاد کد", "آموزش کلاد"))
        self.assertTrue(swipe.has_phrase("آموزش كلاد", "آموزش کلاد"))  # Arabic ک
        self.assertFalse(swipe.has_phrase("کلاد آموزش", "آموزش کلاد"))
        out = self.run_json(os.path.join(FIX, "search_fa.json"), "--phrase", "آموزش کلاد")
        sup = out["supply"]
        self.assertEqual((sup["top"], sup["exact_phrase"], sup["with_subscribers"], sup["views_beat_subscribers"]),
                         (4, 2, 3, 2))
        txt = self.run_swipe(os.path.join(FIX, "search_fa.json"), "--phrase", "آموزش کلاد").stdout
        self.assertIn("عبارت عیناً در عنوان: ۲ از ۴", txt)
        self.assertIn("شکاف", txt)

    # --- formulas: portable, Persian schema -----------------------------------------------------
    def _alone(self, hooks=None):
        d = os.path.join(self.tmp.name, "yt-viral")
        os.mkdir(d)
        for f in ("swipe.py", "_fatext.py"):
            shutil.copy(os.path.join(SKILL, f), d)
        if hooks is not None:
            with open(os.path.join(d, "hooks.json"), "w", encoding="utf-8") as fh:
                json.dump(hooks, fh, ensure_ascii=False)
        return os.path.join(d, "swipe.py")

    def test_folder_alone_uses_bundled_persian_hooks(self):
        hooks = {"hooks": [
            {"name": "The Question", "name_fa": "سؤال", "match": ["^(چرا|چطور)"]},
            {"name": "The List", "name_fa": "فهرست", "match": ["^[۰-۹0-9]+ (تا|ابزار)"]}]}
        script = self._alone(hooks)
        data = [{"channel": "ک", "title": t, "views": n} for t, n in
                (("چرا کسی اینو نمی‌گه؟", 9000), ("۵ ابزار رایگان", 8000), ("یه ویدیو", 1000), ("یکی دیگه", 1000))]
        out = self.run_json(self.write(data), script=script)
        self.assertEqual(out["formulas_file"], "hooks.json")
        self.assertEqual([(o["formula"], o["formula_fa"]) for o in out["outliers"]],
                         [("The Question", "سؤال"), ("The List", "فهرست")])
        self.assertIn("فرمول: سؤال", self.run_swipe(self.write(data), script=script).stdout)

    def test_folder_alone_without_hooks_still_runs(self):
        script = self._alone()
        data = [{"channel": "ک", "title": "t", "views": n} for n in (1, 1, 1, 9)]
        r = self.run_swipe(self.write(data), script=script)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("hooks.json", r.stdout)
        self.assertEqual(self.run_json(self.write(data), script=script)["outliers"][0]["formula"], "Unclassified")

    def test_bundled_hooks_match_yt_script(self):
        a, b = os.path.join(SKILL, "hooks.json"), os.path.join(ROOT, "skills", "yt-script", "hooks.json")
        if not (os.path.exists(a) and os.path.exists(b)):
            self.skipTest("one of the hooks.json files is missing")
        with open(a, "rb") as fa_, open(b, "rb") as fb_:
            self.assertEqual(fa_.read(), fb_.read(),
                             "skills/yt-viral/hooks.json is stale: cp skills/yt-script/hooks.json skills/yt-viral/")

    def test_persian_titles_same_formula_as_hookscore(self):
        swipe = _load(SWIPE, "swipe_fa_tie")
        hook = _load(HOOKSCORE, "hookscore_fa_tie")
        for t in ("چرا ۹۷٪ کانال‌ها قبل از ویدیوی ۳۰ ول می‌کنند؟", "۵ ابزار هوش مصنوعی که وقتت رو نجات می‌ده",
                  "اشتباهی که همه توی تامبنیل می‌کنن", "ChatGPT یا Gemini؟", "قبل و بعد"):
            # hooks.json "match_on": patterns run on the folded text. Feeding hookscore the folded
            # form keeps this test valid whether or not hookscore.py folds internally (fold is idempotent).
            self.assertEqual(swipe.classify(t), hook.classify(swipe.match_text(t))[0], t)
        self.assertEqual(swipe.match_text("۹۷٪ کانال‌ها"), "97% کانالها")


if __name__ == "__main__":
    unittest.main()
