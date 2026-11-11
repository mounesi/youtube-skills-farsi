# -*- coding: utf-8 -*-
"""آزمون‌های skills/yt-reel/keyword.py (شکل‌های تایپی کلمه‌ی کامنت).

اجرا از ریشه‌ی مخزن:  python3 -I -m unittest discover -s tests -t .
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL = os.path.join(ROOT, "skills", "yt-reel")
TOOL = os.path.join(SKILL, "keyword.py")
FIX = os.path.join(ROOT, "tests", "fixtures", "yt-reel")
ZWNJ = "‌"


def _load():
    # a unique module name: the file is called keyword.py, like the stdlib module
    spec = importlib.util.spec_from_file_location("yt_reel_keyword_under_test", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


kw = _load()


def run(*args):
    return subprocess.run([sys.executable, "-I", TOOL] + list(args), capture_output=True,
                          text=True, encoding="utf-8")


def texts(word, **k):
    return [v for v, _s, _w in kw.generate(word, **k)]


class TestArtifactCase(unittest.TestCase):
    """The real case from DrMounesi's Artifacts reel: commenters typed these three."""

    def setUp(self):
        self.items = kw.generate("آرتیفکت")
        self.variants = [v for v, _s, _w in self.items]

    def test_three_real_misspellings(self):
        for v in ("ارتیفکت", "ارتیفکیت", "اردیفکت"):
            self.assertIn(v, self.variants)

    def test_real_misspellings_in_default_list(self):
        top = self.variants[:30]
        for v in ("ارتیفکت", "ارتیفکیت", "اردیفکت"):
            self.assertIn(v, top)

    def test_original_first_then_madda_drop(self):
        self.assertEqual(self.variants[0], "آرتیفکت")
        self.assertEqual(self.variants[1], "ارتیفکت")

    def test_one_regex_matches_all(self):
        rx = kw.build_regex(self.items)
        for v in ("آرتیفکت", "ارتیفکت", "ارتیفکیت", "اردیفکت"):
            self.assertTrue(re.search(rx, v, re.I), v)
        for v in self.variants:
            self.assertTrue(re.search(rx, v, re.I), v)

    def test_exact_regex_matches_all(self):
        rx = kw.build_regex(self.items, exact=True)
        for v in self.variants:
            self.assertTrue(re.search(rx, v, re.I), v)
        self.assertIsNone(re.search(rx, "ارتیفکت لطفا", re.I))

    def test_latin_forms(self):
        self.assertIn("artifact", self.variants)  # known loanword
        self.assertTrue(any(v in self.variants for v in ("artifakt", "artifkt")))

    def test_arabic_keyboard(self):
        self.assertIn("آرتيفکت", self.variants)
        self.assertIn("آرتیفكت", self.variants)

    def test_fixture_comments(self):
        rx = kw.build_regex(self.items)
        with open(os.path.join(FIX, "comments_artifact_fa.txt"), encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line or line.startswith("#"):
                    continue
                want, comment = line[0] == "+", line[2:]
                self.assertEqual(kw.matches(rx, comment), want, comment)


class TestRules(unittest.TestCase):
    def test_no_duplicates(self):
        for w in ("آرتیفکت", "پرامپت‌نویسی", "دهه ۶۰", "artifact"):
            v = texts(w)
            self.assertEqual(len(v), len(set(v)), w)

    def test_sorted_by_score(self):
        scores = [s for _v, s, _w in kw.generate("پرامپت‌نویسی")]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_zwnj_space_none(self):
        v = texts("پرامپت‌نویسی")
        self.assertIn("پرامپت نویسی", v)
        self.assertIn("پرامپتنویسی", v)

    def test_space_to_zwnj_and_joined(self):
        v = texts("هوش مصنوعی")
        self.assertIn("هوش" + ZWNJ + "مصنوعی", v)
        self.assertIn("هوشمصنوعی", v)

    def test_digits(self):
        v = texts("دهه ۶۰")
        self.assertIn("دهه 60", v)
        self.assertIn("دهه ٦٠", v)
        self.assertIn("دهه۶۰", v)
        self.assertIn("دهه ۶۰", texts("دهه 60"))

    def test_homophones(self):
        v = texts("صدا")
        self.assertIn("سدا", v)
        self.assertIn("ثدا", v)
        self.assertIn("غیمت", texts("قیمت"))
        self.assertIn("حزینه", texts("هزینه"))
        self.assertIn("ظرف", texts("ذرف"))

    def test_silent_final_he_not_swapped(self):
        self.assertNotIn("خانح", texts("خانه"))

    def test_quotes(self):
        v = texts("جمینای")
        self.assertIn("«جمینای»", v)
        self.assertEqual(texts("«جمینای»")[0], "جمینای")

    def test_arabic_input_normalized(self):
        self.assertEqual(texts("آرتيفكت")[0], "آرتیفکت")

    def test_finglish(self):
        v = texts("قالب")
        self.assertIn("ghalb", v)
        self.assertIn("template", v)
        self.assertIn("dahe 60", texts("دهه ۶۰"))
        self.assertTrue(any(x in texts("کلاد") for x in ("claude", "kelad")))

    def test_english_keyword(self):
        v = texts("Artifact")
        self.assertEqual(v[0], "artifact")
        self.assertIn("artifakt", v)

    def test_also(self):
        v = texts("artifact", also=["آرتیفکت"])
        self.assertIn("ارتیفکت", v)
        rx = kw.build_regex(kw.generate("artifact", also=["آرتیفکت"]))
        self.assertTrue(re.search(rx, "اردیفکت", re.I))

    def test_regex_word_boundary(self):
        rx = kw.build_regex(kw.generate("کلاد"))
        self.assertTrue(kw.matches(rx, "کلاد لطفا"))
        self.assertFalse(kw.matches(rx, "کلادیاتور"))

    def test_empty(self):
        self.assertEqual(kw.generate("  "), [])
        self.assertEqual(kw.build_regex([]), "")


class TestCLI(unittest.TestCase):
    def test_text_output(self):
        r = run("آرتیفکت")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("کلمه‌ی کامنت: «آرتیفکت»", r.stdout)
        self.assertIn("اردیفکت", r.stdout)
        self.assertIn("```", r.stdout)
        self.assertIn("تخمینی", r.stdout)

    def test_max(self):
        d = json.loads(run("آرتیفکت", "--json", "--max", "5").stdout)
        self.assertEqual(len(d["variants"]), 5)
        self.assertGreater(d["total"], 5)

    def test_json_and_test(self):
        r = run("آرتیفکت", "--json", "--test", "ارتیفکیت لطفا", "--test", "مرسی")
        d = json.loads(r.stdout)
        self.assertEqual(d["keyword"], "آرتیفکت")
        self.assertEqual(d["regex_flags"], "i")
        self.assertEqual([t["match"] for t in d["tests"]], [True, False])
        self.assertTrue(re.search(d["regex"], "اردیفکت", re.I))

    def test_regex_only(self):
        r = run("آرتیفکت", "--regex")
        self.assertEqual(r.returncode, 0)
        lines = r.stdout.strip().splitlines()
        self.assertEqual(len(lines), 1)
        for v in ("آرتیفکت", "ارتیفکت", "ارتیفکیت", "اردیفکت"):
            self.assertTrue(re.search(lines[0], v, re.I), v)

    def test_bad_input(self):
        self.assertEqual(run("").returncode, 2)
        self.assertEqual(run("x", "--max", "0").returncode, 2)
        self.assertEqual(run().returncode, 2)

    def test_does_not_shadow_stdlib_keyword(self):
        # the tool appends (not prepends) its folder to sys.path, so the stdlib wins
        import keyword as std
        self.assertTrue(hasattr(std, "iskeyword"))
        self.assertIn(SKILL, sys.path)
        self.assertNotEqual(sys.path[0], SKILL)

    def test_skill_folder_alone(self):
        self.assertTrue(os.path.isfile(os.path.join(SKILL, "_fatext.py")))
        with open(TOOL, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("../", src)
        self.assertNotIn("yt-script", src)
        self.assertNotIn("/Users/", src)

if __name__ == "__main__":
    unittest.main()
