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
                          ("7d", "7d"), ("۷ روز", "7d"), ("هفته", "7d"), ("1w", "7d"), ("48h", "2d"),
                          ("2d", "2d"), ("168h", "7d"), ("۲۴ ساعته", "24h"), ("۷ روزه", "7d"), ("36h", "36h"),
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


class TestStrictValues(unittest.TestCase):
    """Fixes from the review: never keep half a number, never store an estimate."""

    def test_watch_time_forms(self):
        for raw in ("1:23", "۱:۲۳", "1m 23s", "۱ دقیقه و ۲۳ ثانیه", "83", "۸۳ ثانیه"):
            self.assertEqual(res.parse_value("avg_watch_s", raw), "83", raw)
        self.assertEqual(res.parse_value("avg_watch_s", "۲ دقیقه"), "120")  # never 2, never 2,000,000
        for raw in ("زیاد", "1:75", "یه کم"):
            with self.assertRaises(res.InputError, msg=raw):
                res.parse_value("avg_watch_s", raw)

    def test_whole_number_or_error(self):
        for raw, want in (("12 400", "12400"), ("۱۲ ۴۰۰", "12400"), ("12 400", "12400"),
                          ("۱۲ هزار و ۴۰۰", "12400"), ("۱ میلیون و ۲۰۰ هزار", "1200000"),
                          ("۱۲ هزار و چهارصد", "12400"), ("۱۵٫۰۰۰", "15"), ("12,400", "12400"),
                          ("1.2K", "1200"), ("۱٫۲ هزار", "1200"), ("4.5M views", "4500000"),
                          ("۱۲ هزار بازدید", "12000")):
            self.assertEqual(res.parse_value("views", raw), want, raw)
        self.assertEqual(res.parse_value("non_follower_pct", "45%"), "45")
        for raw in ("12 40", "1 2 3", "۱ هزار و ۲ میلیون", "1.000", "12 views 400"):
            with self.assertRaises(res.InputError, msg=raw):
                res.parse_value("views", raw)

    def test_estimates_and_ranges_rejected(self):
        for raw in ("حدود ۲۰۰", "بیش از ۱۰ هزار", "220 تا 250", "12K-13K", "~200", "200+",
                    "حدوداً ۲۰۰", "about 200"):
            with self.assertRaises(res.InputError, msg=raw):
                res.parse_value("follows", raw)
        self.assertEqual(res.parse_value("views", "۱/۵ میلیون"), "1500000")  # '/' is a decimal, not a range

    def test_platform_and_format_names(self):
        self.assertEqual(res.parse_value("format", "ویدئو"), "long")
        self.assertEqual(res.parse_value("format", "Reels"), "reel")
        self.assertEqual(res.parse_value("platform", "تیک تاک"), "tiktok")
        self.assertEqual(res.parse_value("platform", "فیس بوک"), "facebook")
        for col, raw in (("platform", "instgram"), ("platform", "YouTube Shorts"), ("format", "Reels video")):
            with self.assertRaises(res.InputError, msg=raw):
                res.parse_value(col, raw)

    def test_ambiguous_share_key(self):
        base = ["video_id=a", "platform=ig", "format=reel", "checked_at=24h"]
        with self.assertRaises(res.InputError):
            res.parse_pairs(base + ["اشتراک=20"])
        self.assertEqual(res.parse_pairs(base + ["اشتراک‌گذاری=20"])["shares"], "20")

    def test_small_rates_keep_their_digits(self):
        self.assertEqual(res.fanum(0.05), "۰٫۰۵")
        self.assertNotEqual(res.fanum(0.05), res.fanum(0.1))
        self.assertEqual(res.fanum(0.004), "۰٫۰۰۴")


class TestLogRobust(Base):
    def add(self, *pairs, extra=()):
        return run("--log", self.csv, "--add", *pairs, *extra)

    def test_unquoted_spaced_views(self):
        code, out, err = self.add("video_id=a", "platform=ig", "format=reel", "checked_at=24h",
                                  "views=12", "400")
        self.assertEqual(code, 0, err)
        self.assertEqual(read_rows(self.csv)[0]["views"], "12400")

    def test_file_without_final_newline(self):
        self.assertEqual(self.add("video_id=r1", "platform=ig", "format=reel", "checked_at=24h", "views=100",
                                  extra=("--today", "2000-01-01"))[0], 0)
        with io.open(self.csv, "rb") as f:
            data = f.read().rstrip(b"\r\n")
        with io.open(self.csv, "wb") as f:
            f.write(data)
        self.assertEqual(self.add("video_id=r2", "platform=ig", "format=reel", "checked_at=24h", "views=500")[0], 0)
        header, rows = res.read_log(self.csv)
        self.assertEqual([r["video_id"] for r in rows], ["r1", "r2"])
        self.assertEqual(rows[0]["logged_on"], "2000-01-01")

    def test_bad_files_are_clean_errors(self):
        good = "video_id,platform,format,checked_at,views\n"
        cases = {
            "cp1252": (good + "a,instagram,reel,24h,10\n").encode("utf-8") + "caf\xe9\n".encode("cp1252"),
            "utf16": (good + "a,instagram,reel,24h,10\n").encode("utf-16"),
            "nul": (good + "a,instagram,reel,24h,1\x000\n").encode("utf-8"),
            "huge": (good + "a,instagram,reel,24h,\"" + "x" * 140000 + "\"\n").encode("utf-8"),
        }
        for name, data in cases.items():
            with io.open(self.csv, "wb") as f:
                f.write(data)
            code, out, err = run("--log", self.csv, "--report")
            self.assertEqual(code, 2, (name, err))
            self.assertIn("خطا:", err, name)
            self.assertNotIn("Traceback", err, name)

    def test_video_id_digits_fold(self):
        base = ["platform=ig", "format=reel"]
        self.assertEqual(self.add("video_id=ریلز-۰۷", *base, "checked_at=24h", "views=1000",
                                  "tested=هوک سؤالی")[0], 0)
        code, out, err = self.add("video_id=ریلز-07", *base, "checked_at=24h", "views=2000")
        self.assertEqual(code, 2)
        self.assertIn("--replace", err)
        self.assertEqual(self.add("video_id=ریلز-07", *base, "checked_at=7d", "views=3000")[0], 0)
        code, out, err = run("--log", self.csv, "--report", "--json", "--video", "ریلز-07", "--checked", "7d")
        self.assertEqual(code, 0, err)
        a = json.loads(out)
        self.assertEqual(a["row"]["tested"], "هوک سؤالی")
        self.assertAlmostEqual(a["growth_7d_vs_24h"], 3.0)

    def test_hand_edited_rows_group(self):
        with io.open(self.csv, "w", encoding="utf-8-sig", newline="") as f:
            f.write("video_id,platform,format,checked_at,views,follows\n"
                    "v1,instagram,reel,24h,1000,10\nv2,instagram,reel,24h,1000,10\n"
                    "v3,instagram,reel,24h,1000,10\nv4,Instagram,Reels,24 h,1000,30\n")
        code, out, err = run("--log", self.csv, "--report", "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["baseline_n"], 3)


class TestReportEdges(Base):
    def write(self, lines):
        with io.open(self.csv, "w", encoding="utf-8-sig", newline="") as f:
            f.write("video_id,platform,format,checked_at,tested,views,shares,follows\n" + "\n".join(lines) + "\n")

    def test_zero_median_is_high(self):
        self.write(["a,instagram,reel,24h,,1000,0,", "b,instagram,reel,24h,,1000,0,",
                    "c,instagram,reel,24h,,1000,0,", "d,instagram,reel,24h,,1000,50,"])
        code, out, err = run("--log", self.csv, "--report", "--json")
        a = json.loads(out)
        sh = [m for m in a["metrics"] if m["metric"] == "shares_1k"][0]
        self.assertEqual(sh["verdict"], "high")
        code, out, err = run("--log", self.csv, "--report")
        self.assertEqual(code, 0, err)
        self.assertNotIn("هیچ نرخی", out)
        self.assertIn("میانه‌ی قبلی صفر بود", out)

    def test_confirmation_is_symmetric(self):
        self.write(["a,instagram,reel,24h,,10000,,100", "b,instagram,reel,24h,,10000,,100",
                    "c,instagram,reel,24h,,10000,,100", "d,instagram,reel,24h,X,10000,,146",
                    "e,instagram,reel,24h,X,10000,,200"])
        for vid, other in (("d", "e"), ("e", "d")):
            code, out, err = run("--log", self.csv, "--report", "--json", "--video", vid)
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(out)["confirm"]["follows_1k"], [other], vid)

    def test_small_rates_differ_in_report(self):
        with io.open(self.csv, "w", encoding="utf-8-sig", newline="") as f:
            f.write("video_id,platform,format,checked_at,views,follows\n"
                    "a,youtube,long,24h,40000,2\nb,youtube,long,24h,40000,2\n"
                    "c,youtube,long,24h,40000,2\nd,youtube,long,24h,40000,4\n")
        code, out, err = run("--log", self.csv, "--report")
        self.assertEqual(code, 0, err)
        self.assertIn("فالو در هر ۱۰۰۰ بازدید: ۰٫۱۰ · میانه ۰٫۰۵ · ۲٫۰×", out)


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
