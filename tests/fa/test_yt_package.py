"""Tests for skills/yt-package/title.py (Persian behaviour)."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL = os.path.join(ROOT, "skills", "yt-package")
TOOL = os.path.join(SKILL, "title.py")
FIX = os.path.join(ROOT, "tests", "fixtures", "yt-package")


def load():
    spec = importlib.util.spec_from_file_location("yt_package_title_fa", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(*args, tool=TOOL):
    return subprocess.run([sys.executable, "-I", tool, *args], capture_output=True, text=True, timeout=30)


def kinds(r):
    return [k for k, _ in r["issues"]]


class PersianTitleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = load()

    def test_good_persian_title(self):
        r = self.t.check("تغییرات الگوریتم یوتیوب در فروردین ۱۴۰۵")
        self.assertTrue(r["persian"])
        self.assertEqual(r["words"], 6)
        self.assertEqual(r["issues"], [])
        self.assertTrue(any("۶ تا ۷" in g for g in r["good"]))

    def test_word_count_bounds(self):
        self.assertIn("word-count", kinds(self.t.check("کلاد کد ۲۰۲۶")))
        long = "یک دو سه چهار پنج شش هفت هشت ده یازده دوازده"
        self.assertIn("word-count", kinds(self.t.check(long)))
        r = self.t.check("ساختن اپ با کلاد کد در ۳۰ دقیقه بدون کدنویسی")
        self.assertNotIn("word-count", kinds(r))

    def test_length_thresholds(self):
        base = "آموزش ساخت ریلز با هوش مصنوعی در ۱۰ دقیقه"
        self.assertNotIn("length", kinds(self.t.check(base)))
        self.assertIn("mobile", kinds(self.t.check(base)))
        r = self.t.check(base + " برای کسانی که تازه شروع کرده‌اند")
        self.assertIn("length", kinds(r))
        r = self.t.check("ا" * 101)
        self.assertIn("۱۰۰", dict(r["issues"])["length"])

    def test_persian_digits_spelled_numbers_months_and_names(self):
        for title in ("کلاد کد در ۱۰ دقیقه", "کلاد کد در ٣٠ دقیقه", "سه روش ساختن ریلز با هوش مصنوعی",
                      "تغییرات یوتیوب در اسفند", "تغییرات یوتیوب در دسامبر", "آموزش Claude برای تازه‌کارها"):
            self.assertNotIn("no-number", kinds(self.t.check(title)), title)
        # «نه» (no) is not a number; «دی» alone is not a month
        self.assertIn("no-number", kinds(self.t.check("نه، این ابزار برای همه نیست")))
        self.assertIn("no-number", kinds(self.t.check("دی جی شدن با هوش مصنوعی")))
        self.assertNotIn("no-number", kinds(self.t.check("هوش مصنوعی در ۱۰ دی")))

    def test_brand_is_not_a_name(self):
        r = self.t.check("ساختن اپ بدون کدنویسی | DrMounesi")
        self.assertIn("no-number", kinds(r))

    def test_vague_persian_words_with_and_without_zwnj(self):
        r = self.t.check("بهترین و فوق العاده ترین ترفندهای یوتیوب")
        msg = dict(r["issues"])["vague"]
        self.assertIn("بهترین", msg)
        self.assertIn("فوق‌العاده", msg)
        self.assertIn("vague", kinds(self.t.check("یک ترفند خفن برای ۱۰ برابر بازدید")))

    def test_spam_instead_of_caps_for_persian(self):
        r = self.t.check("هوش مصنوعی شغلت را می‌گیره!!! 🔥🔥🔥")
        self.assertEqual(kinds(r).count("spam"), 2)
        r = self.t.check("آموزش GPT و AI و API در ۵ دقیقه")
        self.assertNotIn("shouting", kinds(r))
        self.assertIn("shouting", kinds(self.t.check("THIS AI TOOL WILL END YOUR JOB 5")))

    def test_episode_first_and_brand_last(self):
        r = self.t.check("قسمت ۱۲: آینده‌ی شغل‌ها با هوش مصنوعی")
        self.assertIn("episode-first", kinds(r))
        self.assertNotIn("brand-last", kinds(r))  # same problem, reported once
        r = self.t.check("آینده‌ی شغل‌ها | قسمت ۱۲ | هوش مصنوعی و ۴۰ درصد کارها")
        self.assertIn("brand-last", kinds(r))
        r = self.t.check("آینده‌ی شغل‌ها با هوش مصنوعی | قسمت ۱۲")
        self.assertNotIn("episode-first", kinds(r))
        self.assertNotIn("brand-last", kinds(r))
        r = self.t.check("DrMounesi | آینده‌ی شغل‌ها با هوش مصنوعی در ۱۴۰۵")
        self.assertIn("brand-last", kinds(r))

    def test_guest_first(self):
        r = self.t.check("دکتر جواد: هوش مصنوعی ۴۰ درصد شغل‌ها را می‌گیرد")
        self.assertIn("guest-first", kinds(r))
        r = self.t.check("سارا احمدی: هوش مصنوعی و ۴۰ درصد شغل‌ها", guest="سارا احمدی")
        self.assertIn("guest-first", kinds(r))
        r = self.t.check("هوش مصنوعی و ۴۰ درصد شغل‌ها با سارا احمدی", guest="سارا احمدی")
        self.assertNotIn("guest-first", kinds(r))

    def test_keyword_first(self):
        r = self.t.check("کلاد کد چیه؟ ساختن اپ در ۳۰ دقیقه", keyword="کلاد کد")
        self.assertNotIn("keyword-first", kinds(r))
        self.assertNotIn("keyword", kinds(r))
        r = self.t.check("ساختن اپ در ۳۰ دقیقه با کلاد کد", keyword="کلاد کد")
        self.assertIn("keyword-first", kinds(r))
        r = self.t.check("ساختن اپ در ۳۰ دقیقه", keyword="کلاد کد")
        self.assertIn("keyword", kinds(r))
        # suffix on the last keyword word still matches (ویدیو → ویدیوها)
        r = self.t.check("ساخت ویدیوها با هوش مصنوعی در ۵ دقیقه", keyword="ساخت ویدیو")
        self.assertNotIn("keyword", kinds(r))

    def test_thumbnail_overlap_on_normalized_tokens(self):
        # Arabic ي, plural suffix and ZWNJ differences must not hide the repeat
        r = self.t.check("ترفندهای یوتیوب برای ۱۰ برابر بازدید", thumb="ترفند يوتيوب")
        msg = dict(r["issues"])["duplicate"]
        self.assertIn("یوتیوب", msg)
        self.assertIn("ترفند", msg)
        r = self.t.check("ترفندهای یوتیوب برای ۱۰ برابر بازدید", thumb="بازدیدم ده برابر شد")
        self.assertIn("duplicate", kinds(r))
        r = self.t.check("ترفندهای یوتیوب برای ۱۰ برابر بازدید", thumb="فقط یک تغییر")
        self.assertNotIn("duplicate", kinds(r))

    def test_thumbnail_three_words_max(self):
        self.assertNotIn("thumb-length", kinds(self.t.check("کلاد کد در ۱۰ دقیقه", thumb="شغلت در خطره")))
        self.assertIn("thumb-length", kinds(self.t.check("کلاد کد در ۱۰ دقیقه", thumb="بدون یک خط کد")))
        # ZWNJ keeps «نمی‌دونستی» one word
        self.assertNotIn("thumb-length", kinds(self.t.check("کلاد کد در ۱۰ دقیقه", thumb="اینو نمی‌دونستی")))

    def test_arabic_letters_fixed_and_flagged(self):
        r = self.t.check("آموزش يوتيوب در ۱۰ دقيقه")
        self.assertIn("letters", kinds(r))
        self.assertEqual(r["title"], "آموزش یوتیوب در ۱۰ دقیقه")

    def test_back_translation_reminder_and_check(self):
        r = self.t.check("کلاد کد چیه؟ ساختن اپ در ۳۰ دقیقه")
        self.assertTrue(any("ترجمه‌ی برگشتی" in n for n in r["notes"]))
        r = self.t.check("کلاد کد چیه؟ ساختن اپ در ۳۰ دقیقه", keyword="کلاد کد", keyword_en="Claude Code",
                         en="What is Claude Code? Build an app in 30 minutes")
        self.assertNotIn("back-translation", kinds(r))
        self.assertEqual(r["back_translation"]["missing"], [])
        r = self.t.check("کلاد کد چیه؟ ساختن اپ در ۳۰ دقیقه", keyword="کلاد کد", keyword_en="Claude Code",
                         en="What is the cloud code? Build an app in half an hour")
        self.assertIn("back-translation", kinds(r))
        self.assertIn("Claude Code", r["back_translation"]["missing"])
        self.assertIn("۳۰", r["back_translation"]["missing"])
        # Latin names inside the Persian title must survive too
        r = self.t.check("آموزش Claude برای تازه‌کارها", en="Cloud tutorial for beginners")
        self.assertIn("Claude", r["back_translation"]["missing"])

    def test_english_title_has_no_persian_reminder(self):
        r = self.t.check("I tried Claude for 30 days")
        self.assertFalse(r["persian"])
        self.assertIsNone(r["back_translation"])
        self.assertNotIn("no-number", kinds(self.t.check("I tried Claude for a week")))


class CliTests(unittest.TestCase):
    def test_file_mode_with_bom_crlf_comments_and_arabic_letters(self):
        p = run(os.path.join(FIX, "titles_fa.txt"), "--json", "--keyword", "کلاد کد")
        self.assertEqual(p.returncode, 0, p.stderr)
        rows = json.loads(p.stdout)
        self.assertEqual(len(rows), 5)
        titles = [r["title"] for r in rows]
        self.assertFalse(any(t.startswith("#") or "﻿" in t or "\r" in t for t in titles))
        self.assertIn("بهترین و فوق‌العاده‌ترین ابزار برنامه‌نویسی", titles)
        self.assertEqual([r["score"] for r in rows], sorted((r["score"] for r in rows), reverse=True))

    def test_text_report_is_persian(self):
        p = run("--title", "قسمت ۴: همه‌چیز درباره‌ی کلاد کد", "--thumb", "کلاد کد")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("امتیاز", p.stdout)
        self.assertIn("ترجمه‌ی برگشتی", p.stdout)
        self.assertIn("تکرار", p.stdout)

    def test_en_flag(self):
        p = run("--title", "کلاد کد در ۱۰ دقیقه", "--keyword-en", "Claude Code", "--en",
                "Claude Code in 10 minutes", "--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)[0]["back_translation"]["missing"], [])

    def test_en_needs_single_title(self):
        p = run(os.path.join(FIX, "titles_fa.txt"), "--en", "x")
        self.assertEqual(p.returncode, 1)
        self.assertIn("--title", p.stderr)

    def test_bad_args_persian_error_no_traceback(self):
        for args in (["--title"], ["--en"], ["--title", ""]):
            p = run(*args)
            self.assertNotEqual(p.returncode, 0, args)
            self.assertNotIn("Traceback", p.stderr, args)

    def test_empty_file(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "empty.txt")
            with open(f, "w", encoding="utf-8") as fh:
                fh.write("# فقط یادداشت\n\n")
            p = run(f)
            self.assertEqual(p.returncode, 1)
            self.assertIn("عنوانی ندارد", p.stderr)

    def test_skill_folder_works_alone(self):
        with tempfile.TemporaryDirectory() as d:
            dst = os.path.join(d, "yt-package")
            shutil.copytree(SKILL, dst)
            p = run("--title", "کلاد کد در ۱۰ دقیقه", "--json", tool=os.path.join(dst, "title.py"))
            self.assertEqual(p.returncode, 0, p.stderr)


class SkillDocTests(unittest.TestCase):
    def test_skill_md(self):
        with open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8") as f:
            s = f.read()
        self.assertTrue(s.startswith("---\nname: yt-package\n"))
        self.assertIn("دروازه", s)
        self.assertIn("منتشرش کنیم یا تغییرش بدیم؟", s)
        self.assertIn("voice.md", s)
        self.assertIn("python3 -I title.py", s)  # the brief says every tool runs with python3 -I
        self.assertNotIn("/Users/", s)
        self.assertNotRegex(s, "[يك]")


if __name__ == "__main__":
    unittest.main()
