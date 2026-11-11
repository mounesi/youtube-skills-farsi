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
        # Shorts and long videos of one channel each get their own median (was: one merged median).
        data = {"_type": "playlist", "channel": "کانال تست", "entries": [
            {"_type": "playlist", "title": "کانال تست - Videos",
             "webpage_url": "https://www.youtube.com/@t/videos", "entries": [
                 {"title": "v%d" % i, "view_count": n} for i, n in enumerate([10000, 12000, 9000, 11000, 30000])]},
            {"_type": "playlist", "title": "کانال تست - Shorts",
             "webpage_url": "https://www.youtube.com/@t/shorts", "entries": [
                 {"title": "s%d" % i, "view_count": n}
                 for i, n in enumerate([500000, 400000, 600000, 450000, 700000, 550000])]}]}
        out = self.run_json(self.write(data), "--min", "0")
        by = {o["title"]: o for o in out["outliers"]}
        self.assertEqual(by["v4"]["median"], 11000)
        self.assertAlmostEqual(by["v4"]["multiple"], 2.73, places=2)
        self.assertEqual((by["v4"]["format"], by["s0"]["format"]), ("video", "short"))
        self.assertEqual(by["s0"]["median"], 525000)
        txt = self.run_swipe(self.write(data), "--min", "2").stdout
        self.assertIn("از ۱ کانال", txt)
        self.assertIn("(ویدیو)", txt)
        # a thin Shorts tab is listed separately, with its format
        data["entries"][1]["entries"] = data["entries"][1]["entries"][:2]
        out = self.run_json(self.write(data))
        self.assertEqual(out["skipped_thin_channels"], [["کانال تست", 2, "short"]])
        self.assertEqual([o["title"] for o in out["outliers"]], ["v4"])

    def test_jsonl_ytdlp_lowercase_j(self):
        lines = [{"channel": "A", "title": "t%d" % i, "view_count": n, "webpage_url": "https://www.youtube.com/watch?v=%d" % i}
                 for i, n in enumerate([1000, 1100, 900, 8000])]
        for name in ("a.jsonl", "a.json"):
            p = self.write("\n".join(json.dumps(l) for l in lines) + "\n", name)
            out = self.run_json(p, "--min", "0")
            self.assertEqual(len(out["outliers"]), 4, name)
            self.assertEqual(out["outliers"][0]["title"], "t3")

    def test_infinite_and_huge_views_are_unknown(self):
        rows = [{"channel": "A", "title": "x%d" % i, "views": 1000} for i in range(4)]
        p = self.write(json.dumps(rows + [{"channel": "A", "title": "inf", "views": 1e309}])
                       .replace("Infinity", "1e309"))
        r = self.run_swipe(p, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["skipped_unknown_views"], 1)
        p = self.write('[{"channel": "A", "title": "big", "views": 1%s}, {"channel": "A", "title": "s", "views": "1%s"}]'
                       % ("0" * 400, "0" * 400))
        r = self.run_swipe(p)
        self.assertNotIn("Traceback", r.stderr)
        swipe = _load(SWIPE, "swipe_fa_inf")
        for bad in (float("inf"), float("-inf"), float("nan"), "1" * 400, 10 ** 400):
            self.assertIsNone(swipe._num(bad), bad)

    def test_zero_median_is_not_a_zero_multiple(self):
        data = [{"channel": "A", "title": "t%d" % i, "views": n} for i, n in enumerate([0, 0, 0, 0, 5000])]
        out = self.run_json(self.write(data), "--min", "0")
        self.assertEqual(out["outliers"], [])
        self.assertEqual(out["skipped_zero_median_channels"], [["A", 5]])
        txt = self.run_swipe(self.write(data)).stdout
        self.assertIn("میانه‌ی بازدیدش صفر است", txt)
        self.assertNotIn("هیچ موردی به این آستانه نرسید", txt)

    def test_instagram_views_and_plays_not_mixed(self):
        # 4 rows with both counts + 1 with plays only: plays is on every row, so the account is
        # measured on plays alone (was: the last reel 3.0x, plays against a views median)
        data = [{"ownerUsername": "p", "caption": "c%d" % i, "videoViewCount": 1000, "videoPlayCount": 3000}
                for i in range(4)] + [{"ownerUsername": "p", "caption": "only plays", "videoPlayCount": 3000}]
        out = self.run_json(self.write(data), "--min", "0")
        self.assertEqual([o["multiple"] for o in out["outliers"]], [1.0] * 5)
        self.assertEqual(out["skipped_other_metric"], [])
        # 4 rows with views only + 1 with plays only: the plays row is left out, never mixed in
        data = [{"ownerUsername": "p", "caption": "c%d" % i, "videoViewCount": 1000} for i in range(4)] + \
               [{"ownerUsername": "p", "caption": "only plays", "videoPlayCount": 3000}]
        out = self.run_json(self.write(data), "--min", "0")
        self.assertEqual([o["multiple"] for o in out["outliers"]], [1.0] * 4)
        self.assertNotIn("only plays", [o["title"] for o in out["outliers"]])
        self.assertEqual(out["skipped_other_metric"][0]["count"], 1)
        txt = self.run_swipe(self.write(data)).stdout
        self.assertIn("برای اکانت p، ۱ ریلز فقط «پلی» داشت نه «بازدید»", txt)

    def test_account_names_are_normalised(self):
        names = ["@ali", "ali ", "@Ali", "@ali ", "ali", "@ali", "@ALI"]
        views = [100, 110, 90, 105, 95, 2000, 100]
        data = [{"account": a, "caption": "c%d" % i, "plays": v} for i, (a, v) in enumerate(zip(names, views))]
        # Arabic ي / ك and a ZWNJ difference are the same Persian name
        fa_names = ["علی", "علي", "@علی", "علی "]
        data += [{"account": a, "caption": "f%d" % i, "plays": v} for i, (a, v) in enumerate(zip(fa_names, [50, 60, 55, 900]))]
        out = self.run_json(self.write(data))
        self.assertEqual(out["skipped_thin_channels"], [])
        self.assertEqual([(o["channel"], o["views"]) for o in out["outliers"]], [("@ali", 2000), ("علی", 900)])

    def test_one_channel_mixed_title_caption_keys_is_one_group(self):
        data = [{"channel": "X", "title": "t%d" % i, "views": 1000} for i in range(4)] + \
               [{"channel": "X", "caption": "big", "views": 5000}]
        out = self.run_json(self.write(data))
        self.assertEqual(out["skipped_thin_channels"], [])
        self.assertEqual([(o["title"], o["platform"]) for o in out["outliers"]], [("big", "youtube")])
        # a YouTube URL on some rows decides the platform for the whole channel
        data[0]["url"] = "https://www.youtube.com/watch?v=1"
        data[4] = {"account": "X", "caption": "big", "views": 5000}
        out = self.run_json(self.write(data))
        self.assertEqual([(o["title"], o["platform"]) for o in out["outliers"]], [("big", "youtube")])

    def test_scientific_and_space_grouped_views(self):
        swipe = _load(SWIPE, "swipe_fa_sci")
        self.assertEqual(swipe._num("1.2E+06"), 1200000)
        self.assertEqual(swipe._num("12 400"), 12400)
        self.assertEqual(swipe._num("1 234 567"), 1234567)
        self.assertEqual(swipe._num("۱۲ ۴۰۰"), 12400)
        self.assertIsNone(swipe._num("12 400 views"))
        self.assertIsNone(swipe._num("1.2e6 views"))
        self.assertEqual(swipe._num("۱۲ هزار"), 12000)
        self.assertEqual(swipe._threshold("1e3"), 1000)
        self.assertEqual(swipe._threshold("۲٫۵"), 2.5)
        for bad in ("1e3x", "1 500", "inf", "nan", "-1"):
            with self.assertRaises(Exception, msg=bad):
                swipe._threshold(bad)
        rows = [{"channel": "A", "title": "t%d" % i, "views": v} for i, v in
                enumerate(["1.2E+06", "1.1E+06", "1.3E+06", "1.2E+07"])]
        out = self.run_json(self.write(rows))
        self.assertEqual([(o["views"], o["median"]) for o in out["outliers"]], [(12000000, 1250000)])

    def test_phrase_ignores_zwnj_space_and_no_gap(self):
        swipe = _load(SWIPE, "swipe_fa_zwnj")
        self.assertTrue(swipe.has_phrase("میخوام کلاد یاد بگیرم", "می‌خوام"))
        self.assertTrue(swipe.has_phrase("می‌خوام کلاد", "میخوام"))
        self.assertTrue(swipe.has_phrase("می خوام", "میخوام"))
        self.assertTrue(swipe.has_phrase("میخوام کلاد", "می‌خوام کلاد"))
        self.assertFalse(swipe.has_phrase("میخوام", "خوام"))
        self.assertFalse(swipe.has_phrase("میخوامش", "میخوام"))

    def test_unreadable_and_too_deep_files_are_clean_errors(self):
        deep = self.write("[" * 100000 + "]" * 100000, "deep.json")
        r = self.run_swipe(deep)
        self.assertEqual(r.returncode, 2)
        self.assertIn("خوانده نشد", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root can read a chmod 000 file")
        p = self.write("[]", "noperm.json")
        os.chmod(p, 0)
        self.addCleanup(os.chmod, p, 0o600)
        r = self.run_swipe(p)
        self.assertEqual(r.returncode, 2)
        self.assertIn("خوانده نشد", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def _channel(self, name, views):
        return {"_type": "playlist", "channel": name,
                "entries": [{"title": "%s %d" % (name, i), "view_count": v} for i, v in enumerate(views)]}

    def test_one_file_per_channel(self):
        a = self.write(self._channel("کانال الف", [1000, 1000, 1000, 9000]), "a.json")
        b = self.write(self._channel("کانال ب", [50, 50, 50, 400]), "b.json")
        out = self.run_json(a, b, "--min", "2")
        self.assertEqual(sorted((o["channel"], o["multiple"]) for o in out["outliers"]),
                         [("کانال الف", 9.0), ("کانال ب", 8.0)])

    def test_appended_ytdlp_outputs_in_one_file(self):
        # `yt-dlp -J ... >> all.json` twice: one JSON document per line
        docs = [self._channel("کانال الف", [1000, 1000, 1000, 9000]),
                self._channel("کانال ب", [50, 50, 50, 400])]
        p = self.write(json.dumps(docs[0], ensure_ascii=False) + "\n"
                       + json.dumps(docs[1], ensure_ascii=False) + "\n", "all.json")
        out = self.run_json(p, "--min", "2")
        self.assertEqual({o["channel"] for o in out["outliers"]}, {"کانال الف", "کانال ب"})

    def test_bad_second_file_is_named(self):
        a = self.write(self._channel("کانال الف", [1000, 1000, 1000, 9000]), "a.json")
        bad = self.write("{نه جیسون", "bad.json")
        r = self.run_swipe(a, bad)
        self.assertEqual(r.returncode, 2)
        self.assertIn("bad.json", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        r = self.run_swipe(a, os.path.join(self.tmp.name, "missing.json"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing.json", r.stderr)

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
