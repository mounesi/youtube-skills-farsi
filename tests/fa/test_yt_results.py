# -*- coding: utf-8 -*-
"""آزمون‌های skills/yt-results/results.py با داده‌ی کاملاً ساختگی (هیچ آمار واقعی‌ای اینجا نیست).

اجرا از ریشه‌ی مخزن:  python3 -I -m unittest discover -s tests -t .
"""
import csv
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL = os.path.join(ROOT, "skills", "yt-results")
TOOL = os.path.join(SKILL, "results.py")
FIX = os.path.join(ROOT, "tests", "fixtures", "yt-results", "synthetic_results.csv")


def _load():
    sys.path.insert(0, SKILL)
    try:
        spec = importlib.util.spec_from_file_location("yt_results_under_test", TOOL)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(SKILL)


res = _load()


def run(*args, tool=TOOL):
    p = subprocess.run([sys.executable, "-I", tool] + list(args), stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, universal_newlines=True, encoding="utf-8")
    return p.returncode, p.stdout, p.stderr


def read_rows(path):
    with io.open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.csv = os.path.join(self.tmp, "results.csv")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fixture_copy(self):
        shutil.copy(FIX, self.csv)
        return self.csv


class TestValues(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(res.parse_value("views", "۱۲٫۴ هزار"), "12400")
        self.assertEqual(res.parse_value("views", "12.4K"), "12400")
        self.assertEqual(res.parse_value("views", "۱۲٬۴۰۰"), "12400")
        self.assertEqual(res.parse_value("views", "۱/۵ میلیون"), "1500000")
        self.assertEqual(res.parse_value("views", "سیصد هزار"), "300000")
        self.assertEqual(res.parse_value("non_follower_pct", "۸۷٪"), "87")
        self.assertEqual(res.parse_value("avg_watch_s", "۷٫۵"), "7.5")
        self.assertEqual(res.parse_value("likes", ""), "")

    def test_bad_numbers_rejected(self):
        for col, v in (("views", "زیاد"), ("likes", "12.5"), ("non_follower_pct", "120"),
                       ("follows", "−۳"), ("views", "نمی‌دونم")):
            with self.assertRaises(res.InputError, msg=v):
                res.parse_value(col, v)

    def test_checked_at(self):
        for raw, want in (("24h", "24h"), ("۲۴ ساعت", "24h"), ("1d", "24h"), ("روز", "24h"),
                          ("7d", "7d"), ("۷ روز", "7d"), ("هفته", "7d"), ("1w", "7d"), ("48h", "48h"),
                          ("24", "24h"), ("7", "7d")):
            self.assertEqual(res.norm_checked(raw), want, raw)
        with self.assertRaises(res.InputError):
            res.norm_checked("دیروز")

    def test_aliases(self):
        row = res.parse_pairs(["ویدیو=a1", "پلتفرم=اینستا", "فرمت=ریلز", "زمان=۲۴ ساعت",
                               "بازدید=۱۰ هزار", "سیو=۲۰۰", "سابسکرایب=۱۲"])
        self.assertEqual(row["video_id"], "a1")
        self.assertEqual(row["platform"], "instagram")
        self.assertEqual(row["format"], "reel")
        self.assertEqual(row["checked_at"], "24h")
        self.assertEqual(row["views"], "10000")
        self.assertEqual(row["saves"], "200")
        self.assertEqual(row["follows"], "12")
        yt = res.parse_pairs(["video_id=b", "platform=یوتیوب", "format=شورت", "checked_at=7d"])
        self.assertEqual((yt["platform"], yt["format"]), ("youtube", "short"))

    def test_unknown_or_duplicate_key(self):
        with self.assertRaises(res.InputError):
            res.parse_pairs(["video_id=a", "platform=ig", "format=reel", "checked_at=24h", "foo=1"])
        with self.assertRaises(res.InputError):
            res.parse_pairs(["video_id=a", "platform=ig", "format=reel", "checked_at=24h",
                             "views=1", "بازدید=2"])
        with self.assertRaises(res.InputError):
            res.parse_pairs(["video_id=a", "platform=ig", "format=reel"])  # no checked_at


class TestLog(Base):
    def test_creates_header_and_appends(self):
        code, out, err = run("--log", self.csv, "--add", "video_id=t-1", "platform=اینستاگرام",
                             "format=ریلز", "checked_at=24h", "views=۸٫۲", "هزار", "follows=۴۰",
                             "--today", "2000-01-01")
        self.assertEqual(code, 0, err)
        self.assertIn("فایل ساخته شد", out)
        with io.open(self.csv, "rb") as f:
            self.assertTrue(f.read().startswith(b"\xef\xbb\xbf"))  # BOM for Excel
        rows = read_rows(self.csv)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["views"], "8200")   # 'views=۸٫۲' + 'هزار' glued back together
        self.assertEqual(rows[0]["follows"], "40")
        self.assertEqual(rows[0]["saves"], "")       # never invented
        self.assertEqual(rows[0]["logged_on"], "2000-01-01")
        self.assertEqual(list(rows[0].keys()), res.COLUMNS)
        code, out, err = run("--log", self.csv, "--add", "video_id=t-2", "platform=ig", "format=reel",
                             "checked_at=24h", "views=1.2K")
        self.assertEqual(code, 0, err)
        self.assertEqual([r["video_id"] for r in read_rows(self.csv)], ["t-1", "t-2"])

    def test_bad_value_writes_nothing(self):
        code, out, err = run("--log", self.csv, "--add", "video_id=t", "platform=ig", "format=reel",
                             "checked_at=24h", "views=زیاد")
        self.assertEqual(code, 2)
        self.assertIn("حدس نمی‌زنیم", err)
        self.assertFalse(os.path.exists(self.csv))

    def test_duplicate_and_replace(self):
        base = ["--log", self.csv, "--add", "video_id=t", "platform=ig", "format=reel", "checked_at=24h"]
        self.assertEqual(run(*(base + ["views=100"]))[0], 0)
        code, out, err = run(*(base + ["views=200"]))
        self.assertEqual(code, 2)
        self.assertIn("--replace", err)
        self.assertEqual(run(*(base + ["views=300", "--replace"]))[0], 0)
        rows = read_rows(self.csv)
        self.assertEqual([r["views"] for r in rows], ["300"])
        # 7d of the same video is a different row
        self.assertEqual(run("--log", self.csv, "--add", "video_id=t", "platform=ig", "format=reel",
                             "checked_at=7d", "views=900")[0], 0)
        self.assertEqual(len(read_rows(self.csv)), 2)

    def test_keeps_extra_user_columns(self):
        with io.open(self.csv, "w", encoding="utf-8", newline="") as f:
            f.write("video_id,platform,format,checked_at,views,my_col\nold,instagram,reel,24h,10,x\n")
        self.assertEqual(run("--log", self.csv, "--add", "video_id=n", "platform=ig", "format=reel",
                             "checked_at=24h", "views=20")[0], 0)
        rows = read_rows(self.csv)
        self.assertEqual(rows[0]["my_col"], "x")
        self.assertEqual(rows[1]["views"], "20")
        self.assertIn("follows", rows[1])

    def test_usage_errors(self):
        self.assertEqual(run("--log")[0], 2)
        self.assertEqual(run("--report")[0], 2)  # no --log
        code, out, err = run("--log", os.path.join(self.tmp, "nope.csv"), "--report")
        self.assertEqual(code, 2)
        self.assertIn("ردیفی نیست", err)
        self.assertEqual(run("--log", self.tmp, "--report")[0], 2)  # a directory
        self.assertEqual(run("--bogus")[0], 2)
        self.assertEqual(run("--help")[0], 0)
        code, out, _ = run("--fields")
        self.assertEqual(code, 0)
        self.assertIn("non_follower_pct", out)


class TestReport(Base):
    def analyse_json(self, *extra):
        code, out, err = run("--log", self.fixture_copy(), "--report", "--json", *extra)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def metric(self, a, name):
        return [m for m in a["metrics"] if m["metric"] == name][0]

    def test_rates_and_multiples(self):
        a = self.analyse_json("--video", "s-05", "--checked", "24h")
        self.assertEqual(a["baseline_n"], 3)  # youtube/long and s-05's own 7d row excluded
        f = self.metric(a, "follows_1k")
        self.assertAlmostEqual(f["value"], 20.0)
        self.assertAlmostEqual(f["median"], 5.0)
        self.assertAlmostEqual(f["multiple"], 4.0)
        self.assertEqual(f["verdict"], "high")
        self.assertAlmostEqual(self.metric(a, "saves_1k")["multiple"], 3.0)
        self.assertEqual(self.metric(a, "comments_1k")["verdict"], "high")   # exactly 1.5x
        self.assertEqual(self.metric(a, "likes_1k")["verdict"], "normal")
        nf = self.metric(a, "non_follower_pct")  # only 2 earlier values -> no median
        self.assertIsNone(nf["median"])
        self.assertIsNone(nf["multiple"])
        self.assertEqual(self.metric(a, "avg_watch_s")["value"], None)
        self.assertEqual(a["confirm"]["follows_1k"], [])  # one video = hypothesis

    def test_text_report_says_hypothesis(self):
        code, out, err = run("--log", self.fixture_copy(), "--report", "--video", "s-05", "--checked", "24h")
        self.assertEqual(code, 0, err)
        self.assertIn("فالو در هر ۱۰۰۰ بازدید: ۲۰ · میانه ۵ · ۴٫۰× ▲ بالاتر از معمول", out)
        self.assertIn("فرضیه: «هوک سؤالی»", out)
        self.assertNotIn("تأییدشده", out)
        self.assertIn("درصد غیرفالوور: ۹۰ · میانه: کمتر از ۳ ردیف قبلی با این عدد", out)
        self.assertNotIn("خالی مانده", out)  # every core field of s-05/24h is filled
        self.assertNotIn("ي", out)
        self.assertNotIn("ك", out)

    def test_second_video_confirms(self):
        self.fixture_copy()
        code, out, err = run("--log", self.csv, "--add", "video_id=s-06", "platform=ig", "format=reel",
                             "checked_at=24h", "views=۱۰ هزار", "follows=۱۸۰", "saves=۲۰", "tested=هوک سؤالی",
                             "--report")
        self.assertEqual(code, 0, err)
        self.assertIn("تأییدشده", out)
        self.assertIn("s-05", out)

    def test_needs_three_earlier_rows(self):
        code, out, err = run("--log", self.fixture_copy(), "--report", "--video", "s-02")
        self.assertEqual(code, 0, err)
        self.assertIn("مقایسه هنوز ممکن نیست", out)
        self.assertIn("فقط ۱ ردیف قبلی", out)
        self.assertNotIn("×", out)
        code, out, err = run("--log", self.csv, "--report", "--video", "s-04")
        self.assertIn("هیچ ردیف قبلی", out)

    def test_7d_growth_and_inherited_tested(self):
        a = self.analyse_json("--video", "s-05", "--checked", "7d")
        self.assertAlmostEqual(a["growth_7d_vs_24h"], 3.0)
        self.assertEqual(a["row"]["tested"], "هوک سؤالی")
        self.assertEqual(a["baseline_n"], 0)
        self.assertIn("saves", a["missing"])

    def test_default_is_last_row_and_table(self):
        a = self.analyse_json()
        self.assertEqual((a["row"]["video_id"], a["row"]["checked_at"]), ("s-05", "7d"))
        code, out, err = run("--log", self.csv, "--report", "--all")
        self.assertEqual(code, 0, err)
        self.assertIn("۲۰٬۰۰۰", out)
        self.assertIn("یوتیوب", out)

    def test_zero_views_no_division(self):
        run("--log", self.csv, "--add", "video_id=z", "platform=ig", "format=reel", "checked_at=24h",
            "views=0", "follows=0")
        code, out, err = run("--log", self.csv, "--report")
        self.assertEqual(code, 0, err)
        self.assertIn("بازدید صفر است", out)


class TestPortable(unittest.TestCase):
    def test_runs_from_a_lone_copy(self):
        tmp = tempfile.mkdtemp()
        try:
            dst = os.path.join(tmp, "yt-results")
            shutil.copytree(SKILL, dst, ignore=shutil.ignore_patterns("__pycache__"))
            data = os.path.join(tmp, "r.csv")
            code, out, err = run("--log", data, "--add", "video_id=p", "platform=ig", "format=reel",
                                 "checked_at=24h", "views=1K", "--report", tool=os.path.join(dst, "results.py"))
            self.assertEqual(code, 0, err)
            self.assertIn("مقایسه هنوز ممکن نیست", out)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_no_cross_skill_imports(self):
        with io.open(TOOL, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("..", src.split("import _fatext")[0].split("sys.path.insert")[-1])
        self.assertNotIn("/Users/", src)


if __name__ == "__main__":
    unittest.main()
