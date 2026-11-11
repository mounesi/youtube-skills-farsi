"""Tests for skills/yt-chapters/chapters.py (Farsi pack).

Run from the repo root:  python3 -I -m unittest discover -s tests -t .
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL = os.path.join(ROOT, "skills", "yt-chapters")
TOOL = os.path.join(SKILL, "chapters.py")
FIX = os.path.join(ROOT, "tests", "fixtures", "yt-chapters")


def fx(name):
    return os.path.join(FIX, name)


def fmt(t):
    ms = int(round(t * 1000))
    return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def load_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("yt_chapters_under_test", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(*args, stdin=None, tool=TOOL):
    return subprocess.run([sys.executable, "-I", tool] + list(args), input=stdin,
                          capture_output=True, text=True, timeout=60)


class DraftTest(unittest.TestCase):
    def test_persian_transcript_finds_the_four_sections(self):
        r = run(fx("talk_fa.srt"), "--target", "4", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        self.assertTrue(d["valid"])
        self.assertEqual([c["label"] for c in d["chapters"]], ["0:00", "0:40", "1:20", "2:00"])
        titles = [c["draft_title"] for c in d["chapters"]]
        self.assertIn("تامبنیل", titles[0])
        self.assertIn("عنوان", titles[1])
        self.assertIn("انتشار", titles[3])
        # stopwords, fillers and verbs never become title words
        joined = " ".join(titles)
        for w in ("می‌خوام", "خب", "حالا", "بگم", "توی", "اینکه"):
            self.assertNotIn(w, joined)
        self.assertAlmostEqual(sum(c["seconds"] for c in d["chapters"]), d["duration"], places=2)

    def test_text_output_is_farsi_with_ascii_timestamps(self):
        r = run(fx("talk_fa.srt"), "--target", "4")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("پیش‌نویس فصل‌ها", r.stdout)
        self.assertIn("۴ فصل", r.stdout)
        self.assertIn("\n0:00 ", r.stdout)
        self.assertNotIn("نامعتبر", r.stdout)
        self.assertNotIn("‎", r.stdout)

    def test_duration_pushes_last_chapter_to_video_end(self):
        d = json.loads(run(fx("talk_fa.srt"), "--target", "4", "--duration", "۳:۰۰", "--json").stdout)
        self.assertEqual(d["duration"], 180.0)
        self.assertAlmostEqual(d["chapters"][-1]["start"] + d["chapters"][-1]["seconds"], 180.0, places=2)

    def test_bad_duration_and_target_are_farsi_usage_errors(self):
        r = run(fx("talk_fa.srt"), "--duration", "سه دقیقه")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--duration", r.stderr)
        self.assertIn("خطا در ورودی", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        r = run(fx("talk_fa.srt"), "--target", "2")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--target", r.stderr)

    def test_help_is_farsi(self):
        r = run("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("فصل‌بندی", r.stdout)

    def test_directory_as_input_does_not_crash(self):
        r = run(FIX)
        self.assertEqual(r.returncode, 2)          # bad input, as SKILL.md defines exit 2
        self.assertNotIn("Traceback", r.stderr)

    def test_broken_or_short_transcript_is_bad_input_with_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = os.path.join(tmp, "bad.json")
            with open(broken, "w", encoding="utf-8") as f:
                f.write('{"segments": [')
            r = run(broken, "--json")
            self.assertEqual(r.returncode, 2)
            self.assertIn("خراب", r.stderr)
            self.assertFalse(json.loads(r.stdout)["valid"])
            short = os.path.join(tmp, "short.srt")
            with open(short, "w", encoding="utf-8") as f:
                f.write("1\n00:00:00,000 --> 00:00:02,000\nسلام\n")
            r = run(short, "--json")
            self.assertEqual(r.returncode, 2)
            self.assertIn("کوتاه", json.loads(r.stdout)["error"])
            r = run(os.path.join(tmp, "nope.srt"), "--json")
            self.assertEqual(r.returncode, 2)
            self.assertIn("error", json.loads(r.stdout))

    def test_spacing_grows_with_length_so_each_topic_gets_a_chapter(self):
        # 7 topics of 3 minutes; topic changes are a 1.5 s pause plus new words; topic 4 is a screen
        # demo with 2.5 s pauses between every line (the old 10 s spacing put two chapters at its edges).
        import random
        rnd = random.Random(7)
        vocab = ["تامبنیل صورت درشت رنگ متن کلیک", "عنوان گوگل کلیدی جستجو واژه سرچ",
                 "توضیحات لینک پلی‌لیست هشتگ خلاصه منبع", "تنظیمات دکمه برنامه صفحه منو پنجره",
                 "بیننده ساعت ایران انتشار روز هفته", "نمودار ریتنشن آمار افت درصد دقیقه",
                 "کامنت سابسکرایب پاسخ دعوت پرسش جامعه"]
        cues, t, n, topic_starts = [], 0.0, 1, []
        for k, words in enumerate(vocab):
            topic_starts.append(t)
            pool, gap, topic_end = words.split(), (2.5 if k == 3 else 0.3), t + 180
            while t + 3 <= topic_end:
                text = " ".join(rnd.choice(pool) for _ in range(6))
                cues.append("%d\n%s --> %s\n%s\n" % (n, fmt(t), fmt(t + 3), text))
                t += 3 + gap
                n += 1
            t += 1.5
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "demo.srt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(cues))
            d = json.loads(run(path, "--json").stdout)
        starts = [c["start"] for c in d["chapters"]]
        gap_min = d["duration"] / (2 * 7)
        self.assertEqual(len(starts), 7)
        for a, b in zip(starts, starts[1:]):
            self.assertGreaterEqual(b - a, gap_min, starts)
        # one chapter on each topic change
        for want, got in zip(topic_starts, starts):
            self.assertLess(abs(want - got), 5, (topic_starts, starts))

    def test_spoken_function_words_and_zwnj_less_verbs_are_not_title_words(self):
        mod = load_module()
        self.assertEqual(mod.keywords("اگه سوالی درباره‌ی انتشار داری"), {"سوالی", "انتشار"})
        kept = mod.keywords("میوه بزرگ برنامه میلیون")
        self.assertEqual(kept, {"میوه", "بزرگ", "برنامه", "میلیون"})
        self.assertEqual(mod.keywords("میکنیم میگیره بگیرید کردیم براتون واسه سلام"), set())


class CheckTest(unittest.TestCase):
    def test_persian_digit_list_is_valid_and_comes_back_ascii(self):
        r = run("--check", fx("chapters_ok_fa.txt"), fx("talk_fa.srt"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("جور است", r.stdout)
        self.assertIn("0:00 تامبنیلی که کلیک می‌گیره", r.stdout)
        self.assertIn("2:00 بهترین ساعت انتشار ویدیو", r.stdout)
        block = r.stdout.split("(رقم انگلیسی):")[1]
        self.assertNotRegex(block, "[۰-۹]{1,2}:[۰-۹]{2}")
        # the description's other lines are not chapters
        self.assertNotIn("t.me", block)

    def test_json_check_fields(self):
        r = run("--check", fx("chapters_ok_fa.txt"), "--duration", "2:38", "--json")
        self.assertEqual(r.returncode, 0, r.stdout)
        d = json.loads(r.stdout)
        self.assertTrue(d["valid"])
        self.assertTrue(d["last_checked"])
        self.assertEqual([c["start"] for c in d["chapters"]], [0, 40, 80, 120])
        self.assertEqual(d["chapters"][-1]["seconds"], 38)
        self.assertEqual(d["errors"], [])

    def test_bad_list_reports_every_youtube_rule(self):
        r = run("--check", fx("chapters_bad_fa.txt"), "--duration", "2:45", "--json")
        self.assertEqual(r.returncode, 1)
        d = json.loads(r.stdout)
        self.assertFalse(d["valid"])
        errs = "\n".join(d["errors"])
        self.assertIn("0:00", errs)          # first is not 0:00
        self.assertIn("صعودی", errs)          # 0:10 then 0:08
        self.assertIn("۱۰ ثانیه", errs)       # 0:05 -> 0:10 is 5 s
        self.assertIn("فصل آخر", errs)        # 2:38 -> 2:45 is 7 s
        warns = "\n".join(d["warnings"])
        self.assertIn("«مقدمه»", warns)
        self.assertIn("«جمع‌بندی»", warns)

    def test_last_chapter_unchecked_without_duration(self):
        r = run("--check", fx("chapters_trailing_fa.txt"), "--json")
        d = json.loads(r.stdout)
        self.assertTrue(d["valid"])
        self.assertFalse(d["last_checked"])
        self.assertIn("طول ویدیو را نداده‌ای", "\n".join(d["warnings"]))

    def test_trailing_timestamps_bullets_and_brackets(self):
        d = json.loads(run("--check", fx("chapters_trailing_fa.txt"), "--json").stdout)
        self.assertEqual([c["label"] for c in d["chapters"]], ["0:00", "0:40", "1:20"])
        self.assertEqual(d["chapters"][1]["title"], "عنوانی که توی جست‌وجو پیدا میشه")

    def test_stdin_arabic_letters_and_too_few(self):
        raw = "00:00 معرفي ابزار\n0:30 كار با Claude\n"
        r = run("--check", "-", "--duration", "60", "--json", stdin=raw)
        self.assertEqual(r.returncode, 1)
        d = json.loads(r.stdout)
        self.assertIn("۳ فصل", "\n".join(d["errors"]))
        self.assertEqual(d["chapters"][1]["title"], "کار با Claude")   # Arabic ك -> Persian ک

    def test_long_title_and_bad_timestamp(self):
        long_title = "این عنوان فصل عمداً خیلی بلند نوشته شده تا از پنجاه نویسه بیشتر شود"
        raw = "0:00 %s\n0:75 خراب\n1:00 سوم\n2:00 چهارم\n" % long_title
        d = json.loads(run("--check", "-", "--json", stdin=raw).stdout)
        self.assertIn("زیر ۵۰", "\n".join(d["warnings"]))
        self.assertIn("خوانا نیست", "\n".join(d["errors"]))

    def test_hours_format(self):
        raw = "0:00 الف\n59:50 ب\n1:00:05 پ\n"
        d = json.loads(run("--check", "-", "--duration", "1:10:00", "--json", stdin=raw).stdout)
        self.assertTrue(d["valid"], d["errors"])
        self.assertEqual(d["chapters"][2]["start"], 3605)

    def test_last_chapter_after_subtitles_end_is_a_warning_not_an_error(self):
        raw = "0:00 تامبنیلی که کلیک می‌گیره\n0:40 عنوان\n2:00 بهترین ساعت انتشار\n2:40 پشت صحنه و موسیقی پایانی\n"
        r = run("--check", "-", fx("talk_fa.srt"), "--json", stdin=raw)
        self.assertEqual(r.returncode, 0, r.stdout)
        d = json.loads(r.stdout)
        self.assertEqual(d["duration_source"], "transcript")
        self.assertFalse(d["last_checked"])
        self.assertIn("--duration", "\n".join(d["warnings"]))
        r = run("--check", "-", "--duration", "2:38", "--json", stdin=raw)
        self.assertEqual(r.returncode, 1)
        d = json.loads(r.stdout)
        self.assertEqual(d["duration_source"], "flag")
        self.assertIn("فصل آخر", "\n".join(d["errors"]))

    def test_trailing_clock_time_in_description_is_not_a_chapter(self):
        raw = ("0:00 تامبنیلی که کلیک می‌گیره\n0:40 عنوانی که پیدا میشه\n1:20 توضیحات درست\n\n"
               "پخش زنده هر جمعه ساعت ۲۱:۰۰\nRecorded at 10:30\n")
        r = run("--check", "-", "--duration", "3:00", "--json", stdin=raw)
        self.assertEqual(r.returncode, 0, r.stdout)
        d = json.loads(r.stdout)
        self.assertEqual([c["label"] for c in d["chapters"]], ["0:00", "0:40", "1:20"])
        warns = "\n".join(d["warnings"])
        self.assertIn("خط ۵ زمان دارد ولی فصل حساب نشد", warns)
        self.assertNotIn("رقم فارسی", warns)
        # a list written only with trailing times still works
        mod = load_module()
        self.assertEqual([i["start"] for i in mod.parse_list("مقدمه (۰۰:۰۰)\nدوم - 0:40\nسوم | 1:20\n")],
                         [0, 40, 80])
        self.assertEqual(mod.parse_list("Recorded at 10:30"), [])

    def test_emoji_and_list_number_prefixes(self):
        mod = load_module()
        for line in ("⏱ 0:00 intro", "🎬 0:00 intro", "▶️ 0:00 intro", "1️⃣ 0:00 intro", "1. 0:00 intro",
                     "۱. ۰:۰۰ intro", "1) 0:00 intro", "#1 0:00 intro", "* 0:00 intro"):
            items = mod.parse_list(line)
            self.assertEqual([(i["start"], i["title"]) for i in items], [(0.0, "intro")], line)
        self.assertEqual([(i["start"], i["title"]) for i in mod.parse_list("1:00 x")], [(60.0, "x")])
        skipped = []
        mod.parse_list("0:00 a\nنکته‌ای که 1:00 وسطش آمده\n", skipped)
        self.assertEqual(skipped, [2])

    def test_ranges_and_decimal_seconds(self):
        mod = load_module()
        items = mod.parse_list("00:00 - 10:00 range")
        self.assertEqual((items[0]["start"], items[0]["title"]), (0.0, "range"))
        for line in ("0:10.5 title", "01:05:5 x"):
            items = mod.parse_list(line)
            self.assertEqual(len(items), 1, line)
            self.assertIsNone(items[0]["start"], line)
        raw = "0:00 الف\n0:10.5 ب\n1:00 پ\n2:00 ت\n"
        d = json.loads(run("--check", "-", "--duration", "3:00", "--json", stdin=raw).stdout)
        self.assertFalse(d["valid"])
        self.assertIn("0:10.5", "\n".join(d["errors"]))

    def test_broken_or_unreadable_transcript_in_check_is_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = os.path.join(tmp, "bad.json")
            with open(broken, "w", encoding="utf-8") as f:
                f.write('{"segments": [')
            r = run("--check", fx("chapters_ok_fa.txt"), broken, "--json")
            self.assertEqual(r.returncode, 2)
            self.assertIn("خراب", r.stderr)
            self.assertFalse(json.loads(r.stdout)["valid"])
            noperm = os.path.join(tmp, "noperm.srt")
            shutil.copy(fx("talk_fa.srt"), noperm)
            os.chmod(noperm, 0)
            try:
                if not os.access(noperm, os.R_OK):          # root can still read it
                    r = run("--check", fx("chapters_ok_fa.txt"), noperm, "--json")
                    self.assertEqual(r.returncode, 2)
                    json.loads(r.stdout)
            finally:
                os.chmod(noperm, 0o600)

    def test_missing_list_file_is_exit_2(self):
        r = run("--check", fx("nope.txt"))
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)


class PortableTest(unittest.TestCase):
    def test_skill_folder_works_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst = os.path.join(tmp, "yt-chapters")
            shutil.copytree(SKILL, dst)
            r = run(fx("talk_fa.srt"), "--target", "4", "--json", tool=os.path.join(dst, "chapters.py"))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(json.loads(r.stdout)["valid"])

    def test_no_cross_skill_import(self):
        with open(TOOL, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("yt-edit", src)
        self.assertNotIn("deadair", src.replace("deadair.py", ""))


if __name__ == "__main__":
    unittest.main()
