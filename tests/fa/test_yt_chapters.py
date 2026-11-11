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
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Traceback", r.stderr)


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
