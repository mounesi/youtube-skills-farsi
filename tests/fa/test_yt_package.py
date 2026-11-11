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
        # over 40 characters: a mobile preview note, not a scored issue (60-70 is the target)
        r = self.t.check(base)
        self.assertNotIn("mobile", kinds(r))
        self.assertTrue(any("فید موبایل" in n for n in r["notes"]))
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


class ReviewFixTests(unittest.TestCase):
    """Regressions from the review of title.py (scoring, matching, markers, input)."""

    @classmethod
    def setUpClass(cls):
        cls.t = load()

    def test_issue_never_ties_with_clean_title(self):
        kw = dict(keyword="کلاد کد")
        clean = self.t.check("کلاد کد ابزار جدید ۱۴۰۵ در فروردین", "رایگان شد", **kw)
        vague = self.t.check("کلاد کد بهترین ابزار ۱۴۰۵ در فروردین", "رایگان شد", **kw)
        dup = self.t.check("کلاد کد ابزار رایگان ۱۴۰۵ در فروردین", "رایگان شد", **kw)
        self.assertEqual(clean["issues"], [])
        self.assertIn("vague", kinds(vague))
        self.assertIn("duplicate", kinds(dup))
        for r in (vague, dup):
            self.assertLess(r["score"], 100)
            self.assertGreater(clean["score"], r["score"])
        r = self.t.check("دکتر رضایی: آینده هوش مصنوعی در ۱۴۰۵", guest="دکتر رضایی")
        self.assertLessEqual(r["score"], 100 - 14 + 3)

    def test_file_ranking_puts_clean_title_first(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "t.txt")
            with open(f, "w", encoding="utf-8") as fh:
                fh.write("کلاد کد بهترین ابزار ۱۴۰۵ در فروردین\nکلاد کد ابزار رایگان ۱۴۰۵ در فروردین\n"
                         "کلاد کد ابزار جدید ۱۴۰۵ در فروردین\n")
            p = run(f, "--keyword", "کلاد کد", "--thumb", "رایگان شد", "--json")
            self.assertEqual(p.returncode, 0, p.stderr)
            rows = json.loads(p.stdout)
            self.assertEqual(rows[0]["title"], "کلاد کد ابزار جدید ۱۴۰۵ در فروردین")
            self.assertTrue(all(r["score"] < 100 for r in rows[1:]))

    def test_mobile_issue_only_when_keyword_is_cut(self):
        t = "آموزش ساخت ریلز با هوش مصنوعی برای همه کلاد کد"
        self.assertIn("mobile", kinds(self.t.check(t, keyword="کلاد کد")))
        t = "ساخت اپ با کلاد کد روی گوشی بدون برنامه‌نویسی در ۳۰ دقیقه"
        self.assertNotIn("mobile", kinds(self.t.check(t, keyword="ساخت اپ")))

    def test_back_translation_whole_tokens(self):
        r = self.t.check("آموزش AI در ۱۰ دقیقه برای مبتدی‌ها", en="A training on maintenance in 100 minutes")
        self.assertIn("AI", r["back_translation"]["missing"])
        self.assertIn("۱۰", r["back_translation"]["missing"])
        r = self.t.check("ساخت اپ با GPT در ۳۰ دقیقه", en="Build an app with ChatGPT in 30 minutes")
        self.assertIn("GPT", r["back_translation"]["missing"])
        r = self.t.check("آموزش Claude در ۳۰ دقیقه", en="Claude's tutorial in 30 minutes")
        self.assertEqual(r["back_translation"]["missing"], [])

    def test_latin_brand_runs_keep_title_persian(self):
        for title in ("Claude Code در برابر Cursor", "مقایسه Claude Code و Cursor AI", "آموزش Claude Code"):
            r = self.t.check(title)
            self.assertTrue(r["persian"], title)
            self.assertNotIn("no-number", kinds(r), title)
            self.assertTrue(any("Claude Code" in g for g in r["good"]), title)
        self.assertFalse(self.t.check("Claude Code vs Cursor in 2026").get("persian"))

    def test_yek_as_article_is_not_a_number(self):
        self.assertIn("no-number", kinds(self.t.check("یک ترفند ساده برای نوشتن ایمیل")))
        self.assertIn("no-number", kinds(self.t.check("بدون یک خط کد ساخت اپ آموزشی")))
        for title in ("یک روز با ChatGPT", "بیست و یک ابزار برای کار", "یک میلیون بازدید در ماه",
                      "۱ میلیون بازدید در ماه"):
            self.assertNotIn("no-number", kinds(self.t.check(title)), title)

    def test_persian_letter_brand_is_a_name(self):
        r = self.t.check("ساخت اپ با کلاد بدون برنامه‌نویسی، روی گوشی خودت")
        self.assertNotIn("no-number", kinds(r))

    def test_brand_tail_markers(self):
        for title in ("ساختن اپ با هوش مصنوعی | قسمت ۳ | DrMounesi",
                      "ساخت اپ در ۵ دقیقه | AI with AL | DrMounesi",
                      "۵ کار ضروری برای فصل امتحانات | DrMounesi",
                      "The hardest part of learning AI | DrMounesi"):
            r = self.t.check(title)
            self.assertNotIn("brand-last", kinds(r), title)
            self.assertNotIn("episode-first", kinds(r), title)
        r = self.t.check("قسمت ۳: ساختن اپ با هوش مصنوعی | DrMounesi")
        self.assertEqual([k for k in kinds(r) if k in ("brand-last", "episode-first")], ["episode-first"])
        self.assertIn("برند/شماره‌ی قسمت آخر عنوان است", r["good"])
        for title in ("قسمت ۳: موضوع هوش مصنوعی", "قسمت ۳: هوش مصنوعی شغلت رو می‌گیره؟",
                      "قسمت ۳ - هوش مصنوعی شغلت رو می‌گیره؟"):
            r = self.t.check(title)
            self.assertIn("episode-first", kinds(r), title)
            self.assertNotIn("برند/شماره‌ی قسمت آخر عنوان است", r["good"], title)
        self.assertIn("episode-first", kinds(self.t.check("قسمت ۵: کلاد کد")))
        self.assertNotIn("episode-first", kinds(self.t.check("فصل امتحانات با هوش مصنوعی در ۱۰ روز")))
        _, markers = self.t.brand_markers("کلاد کد | قسمت ۵ | DrMounesi", self.t.DEFAULT_BRANDS)
        self.assertIn((1, "قسمت"), markers)

    def test_guest_opener_with_guest_flag(self):
        r = self.t.check("گفتگو با دکتر رضایی درباره آینده هوش مصنوعی", guest="رضایی")
        self.assertIn("guest-first", kinds(r))
        self.assertEqual(kinds(r).count("guest-first"), 1)

    def test_whole_word_prefix_match(self):
        self.assertEqual(self.t.find_seq(self.t.toks("Airbnb hacks"), self.t.toks("AI")), -1)
        r = self.t.check("علیرضا رفیعی از آینده هوش مصنوعی می‌گوید", guest="علی")
        self.assertNotIn("guest-first", kinds(r))
        self.assertEqual(self.t.find_seq(self.t.toks("آموزش کلاد کدهای"), self.t.toks("کلاد کد")), 1)
        self.assertEqual(self.t.find_seq(self.t.toks("Claude's tips"), self.t.toks("Claude")), 0)

    def test_inflected_vague_words(self):
        for title in ("یک ترفند فوق‌العاده‌ای برای ساخت اپ", "این ابزار هوش مصنوعی خیلی خفنه",
                      "عالیه! ساخت اپ با هوش مصنوعی", "بهترین‌ها: ابزارهای هوش مصنوعی سال"):
            self.assertIn("vague", kinds(self.t.check(title)), title)
        for title in ("آموزش کامل پایتون در ۱۰ روز", "نهایی‌سازی پروژه با پایتون در ۱۰ روز",
                      "جادوی پایتون در ۵ دقیقه"):
            self.assertNotIn("vague", kinds(self.t.check(title)), title)

    def test_emoji_clusters(self):
        base = "ساخت اپ با Claude در ۱۰ دقیقه "
        self.assertNotIn("spam", kinds(self.t.check(base + "❤️❤️")))
        self.assertNotIn("spam", kinds(self.t.check(base + "🇮🇷🔥")))
        self.assertIn("۳ شکلک", dict(self.t.check(base + "❤️❤️❤️")["issues"])["spam"])

    def test_latin_thumb_on_persian_title(self):
        r = self.t.check("ساخت اپ با هوش مصنوعی در ۳۰ دقیقه", thumb="NO CODE")
        self.assertTrue(any("لاتین روی تامبنیل" in n for n in r["notes"]))
        r = self.t.check("ساخت اپ با هوش مصنوعی در ۳۰ دقیقه", thumb="DrMounesi")
        self.assertFalse(any("لاتین روی تامبنیل" in n for n in r["notes"]))

    def test_invisible_or_punctuation_only_title_rejected(self):
        for t in ("\u200f\u200e", "\u200c\u200c", "\ufeff", "!!!؟؟"):
            p = run("--title", t)
            self.assertEqual(p.returncode, 1, repr(t))
            self.assertIn("خالی", p.stderr)

    def test_invisible_lines_and_rlm_comment_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "t.txt")
            with open(f, "w", encoding="utf-8") as fh:
                fh.write("\u200c\n\u200f# یادداشت من\nکلاد کد در ۱۰ دقیقه\n")
            p = run(f, "--json")
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual([r["title"] for r in json.loads(p.stdout)], ["کلاد کد در ۱۰ دقیقه"])

    def test_file_and_title_together_is_an_error(self):
        p = run(os.path.join(FIX, "titles_fa.txt"), "--title", "عنوان دیگر ۵")
        self.assertEqual(p.returncode, 2)
        self.assertIn("نه هر دو", p.stderr)

    def test_directory_gives_clear_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = run(d)
            self.assertEqual(p.returncode, 1)
            self.assertIn("فایل معمولی نیست", p.stderr)

    def test_non_utf8_locale_no_traceback(self):
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
        for loc in ("C", "en_US.ISO8859-1"):
            env.update(LC_ALL=loc, LANG=loc)
            p = subprocess.run([sys.executable, "-I", TOOL, "--title", "abc 5"], capture_output=True,
                               timeout=30, env=env)
            self.assertEqual(p.returncode, 0, (loc, p.stderr))
            self.assertNotIn(b"Traceback", p.stderr, loc)
            self.assertIn("۵".encode("utf-8"), p.stdout, loc)


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
