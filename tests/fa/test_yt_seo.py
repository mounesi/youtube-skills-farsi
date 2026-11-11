# -*- coding: utf-8 -*-
"""آزمون‌های skills/yt-seo/seo.py (بررسی توضیحات و تگ‌های یوتیوب).

اجرا از ریشه‌ی مخزن:  python3 -I -m unittest discover -s tests -t .
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL = os.path.join(ROOT, "skills", "yt-seo")
TOOL = os.path.join(SKILL, "seo.py")
FIX = os.path.join(ROOT, "tests", "fixtures", "yt-seo")


def _load():
    spec = importlib.util.spec_from_file_location("yt_seo_under_test", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


seo = _load()


def read(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def run(*args, stdin=None, cwd=None, tool=TOOL):
    p = subprocess.run([sys.executable, "-I", tool] + list(args), input=stdin,
                       capture_output=True, text=True, encoding="utf-8", cwd=cwd)
    return p.returncode, p.stdout, p.stderr


def levels(res, cid):
    return [r["level"] for r in res if r["id"] == cid]


def worst(res):
    order = {"ok": 0, "info": 1, "warn": 2, "error": 3}
    return max((r["level"] for r in res), key=lambda l: order[l])


GOOD_LINES = [
    "کلاد کد رو از صفر یاد بگیر؛ بدون اینکه یک خط کد بلد باشی.",
    "قسمت قبلی رو ندیدی؟ اینجا ببین: https://www.youtube.com/watch?v=abc&list=PL1",
    "",
    "- نصب کلاد کد روی مک",
    "- اولین پروژه با یک دستور",
    "- فرق کلاد کد با چت",
    "- سه اشتباه رایج اول کار",
    "",
    "0:00 چرا کلاد کد؟",
    "0:45 نصب",
    "3:10 اولین پروژه",
    "",
    "تو با کلاد کد چی می‌سازی؟ تو کامنت بنویس.",
    "",
    "Learn Claude Code from zero in Persian, even if you have never written a line of code.",
    "",
    "#هوش_مصنوعی #کلاد_کد #آموزش",
]


def desc(replace=None, drop=()):
    lines = list(GOOD_LINES)
    for i, v in (replace or {}).items():
        lines[i] = v
    lines = [ln for i, ln in enumerate(lines) if i not in drop]
    return "\n".join(lines) + "\n"


class TestGoodDescription(unittest.TestCase):
    def test_fixture_clean(self):
        res = seo.lint_description(read("good_fa.txt"), keyword="کلاد کد", duration=14 * 60)
        self.assertEqual(worst(res), "ok", [r for r in res if r["level"] != "ok"])

    def test_inline_good(self):
        res = seo.lint_description(desc(), duration=600)
        self.assertEqual(worst(res), "ok", [r for r in res if r["level"] != "ok"])

    def test_english_description(self):
        res = seo.lint_description(read("english.txt"), duration=13 * 60)
        self.assertNotIn("error", [r["level"] for r in res])
        self.assertEqual(levels(res, "english"), ["info"])

    def test_bom_and_crlf(self):
        res = seo.lint_description("﻿" + desc().replace("\n", "\r\n"), duration=600)
        self.assertEqual(worst(res), "ok")


class TestHook(unittest.TestCase):
    def test_lengths(self):
        self.assertEqual(levels(seo.lint_description(desc({0: "ا" * 95})), "hook"), ["ok"])
        self.assertEqual(levels(seo.lint_description(desc({0: "ا" * 120})), "hook"), ["info"])
        self.assertEqual(levels(seo.lint_description(desc({0: "ا" * 151})), "hook"), ["warn"])

    def test_link_in_hook(self):
        res = seo.lint_description(desc({0: "آموزش کلاد کد t.me/DrMounesi"}))
        self.assertEqual(levels(res, "hook_link"), ["error"])

    def test_greeting(self):
        res = seo.lint_description(desc({0: "سلام دوستان، امروز درباره‌ی کلاد حرف می‌زنیم"}))
        self.assertEqual(levels(res, "hook_greeting"), ["warn"])

    def test_title_repeat_and_keyword(self):
        res = seo.lint_description(desc(), title="کلاد کد رو از صفر یاد بگیر؛ بدون اینکه یک خط کد بلد باشی.",
                                   keyword="هوش مصنوعی")
        self.assertEqual(levels(res, "hook_title"), ["warn"])
        self.assertEqual(levels(res, "hook_keyword"), ["warn"])
        # ZWNJ / Arabic-letter differences do not matter for the keyword
        res = seo.lint_description(desc(), keyword="كلاد‌کد")
        self.assertEqual(levels(res, "hook_keyword"), ["ok"])


class TestWatchNext(unittest.TestCase):
    def test_no_link(self):
        res = seo.lint_description(desc({1: "لینک‌ها پایین"}))
        self.assertEqual(levels(res, "watch_next"), ["warn"])

    def test_video_without_playlist(self):
        res = seo.lint_description(desc({1: "قسمت قبلی: https://youtu.be/abc123"}))
        self.assertEqual(levels(res, "watch_next"), ["warn"])
        self.assertIn("&list=", [r for r in res if r["id"] == "watch_next"][0]["message"])

    def test_channel_link(self):
        res = seo.lint_description(desc({1: "کانال من: https://www.youtube.com/@DrMounesi"}))
        msg = [r for r in res if r["id"] == "watch_next"][0]["message"]
        self.assertIn("کانال", msg)

    def test_link_only(self):
        res = seo.lint_description(desc({1: "https://www.youtube.com/watch?v=abc&list=PL1"}))
        self.assertEqual(levels(res, "watch_next"), ["ok"])
        self.assertEqual(levels(res, "watch_next_text"), ["warn"])

    def test_short_link_with_list(self):
        res = seo.lint_description(desc({1: "Watch next: https://youtu.be/abc?list=PL1"}))
        self.assertEqual(levels(res, "watch_next"), ["ok"])
        self.assertEqual(levels(res, "watch_next_text"), [])


class TestBullets(unittest.TestCase):
    def test_none(self):
        self.assertEqual(levels(seo.lint_description(desc(drop=(3, 4, 5, 6))), "bullets"), ["warn"])

    def test_few(self):
        self.assertEqual(levels(seo.lint_description(desc(drop=(4, 5, 6))), "bullets"), ["info"])

    def test_persian_numbered_and_dot(self):
        d = desc({3: "۱. نصب کلاد", 4: "۲) پروژه‌ی اول", 5: "• فرق‌ها با چت", 6: "✅ اشتباه‌های رایج"})
        self.assertEqual(levels(seo.lint_description(d), "bullets"), ["ok"])

    def test_chapter_lines_are_not_bullets(self):
        d = desc({3: "- 0:00 شروع", 4: "- 0:30 نصب", 5: "- 1:00 پروژه", 6: ""})
        self.assertEqual(levels(seo.lint_description(d), "bullets"), ["warn"])


class TestChapters(unittest.TestCase):
    def ch(self, lines, duration=None):
        return seo.validate_chapters([(seo.fa.parse_timestamp(t), ttl) for t, ttl in lines], duration)

    def test_rules(self):
        self.assertEqual(self.ch([("0:00", "a"), ("0:10", "b"), ("0:20", "c")], 30), [])
        msgs = [m for _, m, _ in self.ch([("0:05", "a"), ("0:20", "b"), ("0:40", "c")])]
        self.assertTrue(any("0:00" in m for m in msgs))
        self.assertTrue(self.ch([("0:00", "a"), ("0:20", "b")]))  # fewer than 3
        self.assertTrue(self.ch([("0:00", "a"), ("0:09", "b"), ("0:30", "c")]))  # 9 s
        self.assertTrue(self.ch([("0:00", "a"), ("0:40", "b"), ("0:20", "c")]))  # not ascending
        self.assertTrue(self.ch([("0:00", "a"), ("0:20", "b"), ("0:40", "c")], 45))  # last 5 s
        self.assertTrue(self.ch([("0:00", "a"), ("0:20", "b"), ("0:40", "c")], 30))  # past the end

    def test_long_title(self):
        probs = self.ch([("0:00", "ب" * 51), ("0:20", "b"), ("0:40", "c")])
        self.assertEqual([p[0] for p in probs], ["warn"])

    def test_in_description(self):
        res = seo.lint_description(desc({9: "0:05 نصب"}))
        self.assertIn("error", levels(res, "chapters"))
        res = seo.lint_description(desc(), duration=193)
        self.assertIn("error", levels(res, "chapters"))
        res = seo.lint_description(desc())
        ok = [r for r in res if r["id"] == "chapters"][0]
        self.assertEqual(ok["level"], "ok")
        self.assertIn("--duration", ok["message"])

    def test_persian_digits_and_brackets(self):
        res = seo.lint_description(desc({8: "(۰:۰۰) چرا", 9: "[0:45] نصب", 10: "3:10 - پروژه"}))
        self.assertEqual(levels(res, "chapters"), ["ok"])
        self.assertEqual(levels(res, "chapters_digits"), ["warn"])

    def test_hour_format(self):
        res = seo.lint_description(desc({8: "00:00:00 چرا", 9: "00:10:00 نصب", 10: "1:02:05 پروژه"}))
        self.assertEqual(levels(res, "chapters"), ["ok"])

    def test_none_and_trailing_times(self):
        res = seo.lint_description(desc(drop=(8, 9, 10)))
        self.assertEqual(levels(res, "chapters"), ["info"])
        res = seo.lint_description(desc({8: "مقدمه 0:00", 9: "نصب 0:45", 10: "پروژه 3:10"}))
        self.assertEqual(levels(res, "chapters"), ["warn"])


class TestQuestion(unittest.TestCase):
    def test_none(self):
        self.assertEqual(levels(seo.lint_description(desc({12: "منتظر نظرتون هستم."})), "question"), ["warn"])

    def test_two_in_one_line(self):
        res = seo.lint_description(desc({12: "نظرتون چیه؟ کدوم بهتره؟"}))
        self.assertEqual(levels(res, "question"), ["warn"])

    def test_no_comment_cue(self):
        self.assertEqual(levels(seo.lint_description(desc({12: "کدوم بهتره؟"})), "question"), ["info"])

    def test_hook_and_chapter_questions_ignored(self):
        res = seo.lint_description(desc({0: "چرا کلاد کد این‌قدر سریع شد؟"}))
        self.assertEqual(levels(res, "question"), ["ok"])


class TestEnglishBlock(unittest.TestCase):
    def test_missing(self):
        self.assertEqual(levels(seo.lint_description(desc(drop=(13, 14))), "english"), ["warn"])

    def test_too_long(self):
        long_en = "This is a sentence about Claude. " * 5
        self.assertEqual(levels(seo.lint_description(desc({14: long_en})), "english"), ["info"])

    def test_link_block_is_not_english_block(self):
        res = seo.lint_description(desc({14: "Telegram: https://t.me/DrMounesi YouTube: https://youtube.com/@DrMounesi"}))
        self.assertEqual(levels(res, "english"), ["warn"])


class TestHashtags(unittest.TestCase):
    def tags(self, line, **kw):
        return seo.lint_description(desc({16: line}), **kw)

    def test_counts(self):
        self.assertEqual(levels(self.tags("#الف #ب #ج #د"), "hashtags"), ["warn"])
        self.assertEqual(levels(self.tags(" ".join("#t%d" % i for i in range(16))), "hashtags"), ["warn"])
        self.assertEqual(levels(self.tags(" ".join("#t%d" % i for i in range(61))), "hashtags"), ["error"])
        self.assertEqual(levels(seo.lint_description(desc(drop=(15, 16))), "hashtags"), ["warn"])

    def test_space_zwnj_hyphen(self):
        res = self.tags("#هوش مصنوعی #کلاد")
        self.assertEqual(levels(res, "hashtag_space"), ["warn"])
        self.assertIn("#هوش_مصنوعی", [r for r in res if r["id"] == "hashtag_space"][0]["message"])
        self.assertEqual(levels(self.tags("#هوش‌مصنوعی #کلاد"), "hashtag_zwnj"), ["warn"])
        self.assertEqual(levels(self.tags("#هوش-مصنوعی #کلاد"), "hashtag_break"), ["warn"])

    def test_body_hashtag_and_url_fragment(self):
        res = seo.lint_description(desc({4: "- اولین پروژه #کلاد", 16: "#a #b"}))
        self.assertEqual(levels(res, "hashtags_place"), ["warn"])
        res = seo.lint_description(desc({1: "اینجا ببین: https://www.youtube.com/watch?v=a&list=P#t=30"}))
        self.assertEqual(levels(res, "hashtags"), ["ok"])

    def test_duplicates(self):
        self.assertEqual(levels(self.tags("#کلاد #كلاد"), "hashtag_dup"), ["info"])


class TestLimits(unittest.TestCase):
    def test_length(self):
        res = seo.lint_description(desc() + "ا" * 5000)
        self.assertEqual(levels(res, "length"), ["error"])

    def test_brackets_and_arabic(self):
        res = seo.lint_description(desc({4: "- اولین <پروژه>"}))
        self.assertEqual(levels(res, "brackets"), ["error"])
        res = seo.lint_description(desc({4: "- اولين پروژه با كلاد"}))
        self.assertEqual(levels(res, "arabic_letters"), ["warn"])


class TestTags(unittest.TestCase):
    def test_split(self):
        self.assertEqual(seo.split_tags("کلاد، Claude,  هوش مصنوعی ,\nAI"), ["کلاد", "Claude", "هوش مصنوعی", "AI"])

    def test_studio_length(self):
        self.assertEqual(seo.studio_length(["ab", "c d"]), 2 + 5 + 1)
        self.assertEqual(seo.studio_length([]), 0)

    def test_limit(self):
        tags = ["تگ شماره %d برای آزمون" % i for i in range(30)]
        self.assertEqual(levels(seo.lint_tags(tags), "tags"), ["error"])
        self.assertEqual(levels(seo.lint_tags(["کلاد", "Claude"]), "tags"), ["ok"])

    def test_scripts(self):
        self.assertEqual(levels(seo.lint_tags(["کلاد", "Claude"]), "tags_scripts"), ["ok"])
        self.assertEqual(levels(seo.lint_tags(["کلاد", "هوش مصنوعی"]), "tags_scripts"), ["warn"])
        self.assertEqual(levels(seo.lint_tags(["Claude"]), "tags_scripts"), ["warn"])

    def test_hash_dup_many(self):
        res = seo.lint_tags(["#ai", "AI", "کلاد"] + ["t%d" % i for i in range(14)])
        self.assertEqual(levels(res, "tags_hash"), ["warn"])
        self.assertEqual(levels(res, "tags_many"), ["info"])
        self.assertEqual(levels(seo.lint_tags(["کلاد", "كلاد", "x"]), "tags_dup"), ["info"])


class TestCLI(unittest.TestCase):
    def test_good_exit_0_persian_output(self):
        code, out, err = run(os.path.join(FIX, "good_fa.txt"), "--duration", "۱۴:۲۰",
                             "--tags", "کلاد کد,Claude Code")
        self.assertEqual(code, 0, err)
        self.assertIn("همه‌چیز مرتب است", out)
        self.assertIn("منتشر نمی‌کند", out)

    def test_bad_exit_1(self):
        code, out, _ = run(os.path.join(FIX, "bad_fa.txt"))
        self.assertEqual(code, 1)
        self.assertIn("[خطا]", out)
        self.assertIn("قانون رسمی یوتیوب", out)

    def test_json_and_stdin(self):
        code, out, _ = run("-", "--json", "--tags=کلاد,Claude", stdin=read("good_fa.txt"))
        self.assertEqual(code, 0)
        d = json.loads(out)
        self.assertEqual(d["errors"], 0)
        self.assertEqual(d["tags"], ["کلاد", "Claude"])
        self.assertTrue(all(set(c) == {"id", "level", "title", "message", "source"} for c in d["checks"]))

    def test_tags_only_and_file(self):
        code, out, _ = run("--tags", "کلاد,Claude")
        self.assertEqual(code, 0)
        self.assertIn("تگ", out)
        tmp = tempfile.mkdtemp()
        try:
            p = os.path.join(tmp, "tags.txt")
            with open(p, "w", encoding="utf-8") as f:
                f.write("کلاد\nClaude\n")
            code, out, _ = run("--tags-file", p, "--json")
            self.assertEqual(json.loads(out)["tags"], ["کلاد", "Claude"])
        finally:
            shutil.rmtree(tmp)

    def test_bad_input_exit_2(self):
        self.assertEqual(run("no-such-file.txt")[0], 2)
        self.assertIn("پیدا نشد", run("no-such-file.txt")[2])
        self.assertEqual(run(FIX)[0], 2)  # directory
        self.assertEqual(run(os.path.join(FIX, "good_fa.txt"), "--tags")[0], 2)
        self.assertEqual(run(os.path.join(FIX, "good_fa.txt"), "--duration", "abc")[0], 2)
        self.assertEqual(run(os.path.join(FIX, "good_fa.txt"), "--nope")[0], 2)
        self.assertEqual(run()[0], 2)

    def test_skill_folder_portable(self):
        tmp = tempfile.mkdtemp()
        try:
            dst = os.path.join(tmp, "yt-seo")
            os.mkdir(dst)
            for name in ("seo.py", "_fatext.py", "SKILL.md"):
                shutil.copy(os.path.join(SKILL, name), dst)
            code, out, err = run(os.path.join(FIX, "good_fa.txt"), cwd=tmp,
                                 tool=os.path.join(dst, "seo.py"))
            self.assertEqual(code, 0, err)
        finally:
            shutil.rmtree(tmp)


class TestRegressions(unittest.TestCase):
    """Fixes from the review: invisible lines, lone timestamps, bad times, URL edges, title/keyword, tags."""

    def test_invisible_only_lines_are_blank(self):
        good = read("good_fa.txt")
        res = seo.lint_description("\u200f\n" + good, keyword="کلاد کد", duration=14 * 60)
        self.assertEqual(worst(res), "ok", [r for r in res if r["level"] != "ok"])
        res = seo.lint_description(good.replace("\n\n", "\n\u200c\n"), keyword="کلاد کد", duration=14 * 60)
        self.assertEqual(worst(res), "ok", [r for r in res if r["level"] != "ok"])

    def test_single_timestamp_is_not_a_chapter_list(self):
        res = seo.lint_description(desc({8: "4:12 جایی که خطا رو خودش درست می‌کنه"}, drop=(9, 10)))
        self.assertEqual(levels(res, "chapters"), ["info"])
        self.assertNotIn("error", [r["level"] for r in res])
        res = seo.lint_description(desc({8: "4:12 الف", 9: "6:00 ب"}, drop=(10,)))
        msgs = [r["message"] for r in res if r["id"] == "chapters" and r["level"] == "error"]
        self.assertTrue(any("0:00" in m for m in msgs), msgs)

    def test_impossible_time_is_named(self):
        res = seo.lint_description(desc({10: "3:75 اولین پروژه"}))
        msgs = [r["message"] for r in res if r["id"] == "chapters"]
        self.assertTrue(any("3:75" in m and "۱۱" in m for m in msgs), msgs)
        self.assertEqual(levels(res, "chapters_blocks"), [])

    def test_blank_lines_between_chapters(self):
        d = desc({8: "0:00 چرا", 9: "\n0:45 نصب", 10: "\n3:10 پروژه"})
        res = seo.lint_description(d, duration=600)
        self.assertEqual(levels(res, "chapters"), ["ok"])
        self.assertIn("۳ فصل", [r for r in res if r["id"] == "chapters"][0]["message"])
        self.assertEqual(levels(res, "chapters_gap"), ["warn"])

    def test_blocks_message_names_starts(self):
        res = seo.lint_description(desc({12: "بهترین لحظه:\n4:12 خطا\nتو با کلاد کد چی می‌سازی؟ تو کامنت بنویس."}))
        msg = [r for r in res if r["id"] == "chapters_blocks"][0]["message"]
        self.assertIn("0:00", msg)
        self.assertIn("4:12", msg)

    def test_url_needs_word_end(self):
        self.assertEqual(levels(seo.lint_description(desc({0: "راز موفقیت Mr.Beast در یوتیوب؛"})), "hook_link"), [])
        self.assertEqual(levels(seo.lint_description(desc({0: "آموزش youtu.be/x"})), "hook_link"), ["error"])
        self.assertEqual(levels(seo.lint_description(desc({0: "آموزش bit.ly"})), "hook_link"), ["error"])

    def test_title_repeat_ignores_punctuation_and_prefix(self):
        res = seo.lint_description(desc(), title="کلاد کد رو از صفر یاد بگیر؛ بدون اینکه یک خط کد بلد باشی")
        self.assertEqual(levels(res, "hook_title"), ["warn"])
        res = seo.lint_description(desc(), title="کلاد کد رو از صفر یاد بگیر")
        self.assertEqual(levels(res, "hook_title"), ["warn"])

    def test_keyword_whole_words(self):
        self.assertEqual(levels(seo.lint_description(desc({0: "ساخت ایمیل با Gmail از صفر؛"}), keyword="AI"),
                                "hook_keyword"), ["warn"])
        self.assertEqual(levels(seo.lint_description(desc({0: "ساخت ایمیل‌ها با Gmail از صفر؛"}), keyword="ایمیل"),
                                "hook_keyword"), ["ok"])
        self.assertEqual(levels(seo.lint_description(desc({0: "کلادکد از صفر"}), keyword="کلاد کد"),
                                "hook_keyword"), ["ok"])

    def test_tag_dup_case_only(self):
        msg = [r for r in seo.lint_tags(["Claude", "claude", "کلاد"]) if r["id"] == "tags_dup"][0]["message"]
        self.assertNotIn("نیم‌فاصله", msg)
        msg = [r for r in seo.lint_tags(["کلاد", "كلاد"]) if r["id"] == "tags_dup"][0]["message"]
        self.assertIn("نیم‌فاصله", msg)

    def test_english_warning_wording(self):
        msg = [r for r in seo.lint_description(desc(drop=(13, 14))) if r["id"] == "english"][0]["message"]
        self.assertIn("ترجمه از فارسی", msg)

    def test_help_exit_0_stdout(self):
        code, out, _ = run("--help")
        self.assertEqual(code, 0)
        self.assertIn("seo.py", out)

    def test_latin1_locale_pipe(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("LC_") and k != "LANG"}
        env["LC_ALL"] = "en_US.ISO8859-1"
        p = subprocess.run([sys.executable, "-I", TOOL, os.path.join(FIX, "good_fa.txt")],
                           capture_output=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn(b"Traceback", p.stdout + p.stderr)
        self.assertIn("منتشر نمی‌کند".encode("utf-8"), p.stdout)


class TestSkillDoc(unittest.TestCase):
    def test_skill_md(self):
        with open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("---\nname: yt-seo\n"))
        self.assertIn("منتشرش کنیم یا تغییرش بدیم؟", text)
        self.assertIn("## دروازه", text)
        self.assertIn("voice.md", text)
        self.assertNotRegex(text, "[يك]")
        self.assertNotIn("/Users/", text)

    def test_skeleton_in_skill_md_passes(self):
        with open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8") as f:
            text = f.read()
        start = text.index("```\n", text.index("### نمونه‌ی اسکلت")) + 4
        block = text[start:text.index("```", start)]
        res = seo.lint_description(block)
        self.assertNotIn("error", [r["level"] for r in res])


if __name__ == "__main__":
    unittest.main()
