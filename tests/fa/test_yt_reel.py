# -*- coding: utf-8 -*-
"""آزمون‌های skills/yt-reel/keyword.py (شکل‌های تایپی کلمه‌ی کامنت).

اجرا از ریشه‌ی مخزن:  python3 -I -m unittest discover -s tests -t .
"""
import importlib.util
import json
import os
import re
import shutil
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
        # the keyword is shown the way the user typed it; the lowercase form is a variant
        items = kw.generate("Artifact")
        v = [x for x, _s, _w in items]
        self.assertEqual(v[0], "Artifact")
        self.assertEqual(items[0][2], ["orig"])
        self.assertIn(("artifact", ["latin_case"]), [(x, w) for x, _s, w in items])
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

    def test_common_word_warning(self):
        for word in ("شروع", "سلام", "مرسی", "عالی", "آره", "اره", "لینک", "ممنون", "خوب", "هوش",
                     "Start", "link", "YES", "«سلام»"):
            self.assertTrue(kw.common_words(word), word)
        for word in ("آرتیفکت", "دهه ۶۰", "هوش مصنوعی", "شروع ریلز", "artifact"):
            self.assertEqual(kw.common_words(word), [], word)
        self.assertEqual(kw.common_words("آرتیفکت", ["link"]), ["link"])  # --also is checked too
        r = run("شروع")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("هشدار", r.stdout)
        self.assertIn("دوتکه", r.stdout)
        r = run("start", "--regex")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(len(r.stdout.strip().splitlines()), 1)  # stdout stays one regex
        self.assertIn("رایج", r.stderr)
        d = json.loads(run("مرسی", "--json").stdout)
        self.assertEqual(d["common_word"], ["مرسی"])
        self.assertIn("نامعمول", d["warning"])
        d = json.loads(run("آرتیفکت", "--json").stdout)
        self.assertEqual(d["common_word"], [])
        self.assertIsNone(d["warning"])
        self.assertNotIn("هشدار", run("آرتیفکت").stdout)
        with open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8") as fh:
            self.assertIn("کلمه‌ی خیلی رایج", fh.read())

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


def rx_for(word, exact=False, **k):
    return kw.build_regex(kw.generate(word, **k), exact=exact)


class TestRegexPrecision(unittest.TestCase):
    """A short keyword must not shrink to a consonant skeleton that DMs everyone."""

    def test_short_keywords_do_not_match_common_words(self):
        cases = {
            "سورا": ["سر", "سری جدید", "سوری", "سیر"],
            "آوا": ["او گفت", "ای وای"],
            "پایتون": ["بدن", "بتن"],
            "طلا": ["تل", "تلو"],
        }
        for word, comments in cases.items():
            rx = rx_for(word)
            for c in comments:
                self.assertFalse(kw.matches(rx, c), (word, c))

    def test_real_variants_still_match(self):
        cases = {"سورا": ["سورآ", "سورا لطفا"], "پایتون": ["پایتن", "python"],
                 "طلا": ["طلاا"], "آرتیفکت": ["آرتیفکت", "ارتیفکت", "ارتیفکیت", "اردیفکت"]}
        for word, comments in cases.items():
            rx = rx_for(word)
            for c in comments:
                self.assertTrue(kw.matches(rx, c), (word, c))

    def test_every_variant_still_matched(self):
        for word in ("آوا", "پاییز", "آیووی", "سورا", "طلا", "جمینای", "دهه ۶۰", "ChatGPT"):
            items = kw.generate(word)
            for exact in (False, True):
                rx = kw.build_regex(items, exact=exact)
                for v, _s, _w in items:
                    self.assertTrue(re.search(rx, v, re.I), (word, exact, v))

    def test_no_backtracking_blowup(self):
        import time
        for word, comment in (("آوا", "آ" + "ا" * 2200 + "x"), ("پاییز", "پ" + "ی" * 2200 + "x"),
                              ("آیووی", "آ" + "ی" * 2200 + "x"),
                              ("آرتیفکت", "آر" + "ـ" * 2200 + "x")):
            rx = rx_for(word)
            t = time.time()
            kw.matches(rx, comment)
            self.assertLess(time.time() - t, 0.5, word)


class TestRegexSuffixes(unittest.TestCase):
    def test_spoken_suffixes(self):
        cases = {
            "آرتیفکت": ["ارتیفکتو بفرست", "ارتیفکتها", "ارتیفکتای", "آرتیفکتو", "artifacts",
                        "Artifacts!"],
            "پرامپت": ["پرامپتو بفرست", "پرامپتشو", "پرامپتها", "پرامپت‌هارو", "پرامپتمو"],
            "کلاد": ["کلادو", "کلاد" + ZWNJ + "ها"],
        }
        for word, comments in cases.items():
            rx = rx_for(word)
            for c in comments:
                self.assertTrue(kw.matches(rx, c), (word, c))
        self.assertTrue(kw.matches(rx_for("پرامپت", exact=True), "پرامپتو"))

    def test_longer_words_still_rejected(self):
        self.assertFalse(kw.matches(rx_for("کلاد"), "کلادیاتور"))
        self.assertFalse(kw.matches(rx_for("کلاد"), "گلادیاتور"))
        self.assertFalse(kw.matches(rx_for("پرامپت"), "پرامپتیک"))
        self.assertFalse(kw.matches(rx_for("پرامپت"), "پرامپتور"))
        self.assertFalse(kw.matches(rx_for("آرتیفکت"), "آرتیست"))

    def test_ezafe_and_number_words(self):
        rx = rx_for("دهه ۶۰")
        for c in ("دهه‌ی ۶۰", "دهه ی ۶۰", "دههٔ ۶۰", "دهه۶۰", "دهه شصت", "دهه شست"):
            self.assertTrue(kw.matches(rx, c), c)
        self.assertIn("دهه شصت", texts("دهه ۶۰"))
        self.assertEqual(kw._num_words(65), "شصت و پنج")
        self.assertEqual(kw._num_words(120), "صد و بیست")


class TestRawComments(unittest.TestCase):
    """--test must say exactly what the automation will do with the raw comment."""

    def test_invisible_characters_in_the_comment(self):
        rx = rx_for("آرتیفکت")
        for c in ("آرتیـفکت", "آرتی‏فکت", "آرتی‎فکت", "﻿آرتیفکت"):
            self.assertTrue(re.search(rx, c, re.I), repr(c))
        rx = rx_for("پرامپت")
        self.assertTrue(re.search(rx, "پرامپـت", re.I))
        self.assertTrue(re.search(rx, "پِرامپت", re.I))
        self.assertTrue(re.search(rx_for("هوش مصنوعی"), "هوش  مصنوعی", re.I))

    def test_cli_test_equals_printed_pattern(self):
        comments = ["آرتیـفکت", "آرتی‏فکت", "ارتیفکتو بفرست", "مرسی", "آرتیست", "artifact!"]
        args = ["آرتیفکت", "--json"]
        for c in comments:
            args += ["--test", c]
        d = json.loads(run(*args).stdout)
        for t in d["tests"]:
            self.assertEqual(t["match"], re.search(d["regex"], t["comment"], re.I) is not None,
                             t["comment"])

    def test_matches_does_not_normalize(self):
        self.assertFalse(kw.matches("آرتیفکت", "آرتیـفکت"))

    def test_punctuation_only_keyword_refused(self):
        r = run("-")
        self.assertEqual(r.returncode, 2)
        self.assertIn("علامت", r.stderr)


class TestRegexPortable(unittest.TestCase):
    def test_no_w_classes(self):
        for word, exact in (("کلاد", False), ("آرتیفکت", True), ("ChatGPT", False)):
            rx = rx_for(word, exact=exact)
            self.assertNotIn("\\w", rx)
            self.assertNotIn("\\W", rx)

    def test_python_boundaries(self):
        rx = rx_for("کلاد")
        got = [kw.matches(rx, c) for c in ("کلادیاتور", "ماکلادا", "کلاد لطفا", "claude!",
                                            "کلاد،", "کلاد؟")]
        self.assertEqual(got, [False, False, True, True, True, True])

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_same_result_in_javascript(self):
        cases = ["کلادیاتور", "گلادیاتور", "ماکلادا", "کلاد لطفا", "claude!", "کلادو",
                 "کلاد" + ZWNJ + "ها", "مرسی"]
        for exact in (False, True):
            rx = rx_for("کلاد", exact=exact)
            want = [kw.matches(rx, c) for c in cases]
            js = ("const r=JSON.parse(process.argv[1]);const c=JSON.parse(process.argv[2]);"
                  "for(const f of ['i','iu']){const x=new RegExp(r,f);"
                  "console.log(JSON.stringify(c.map(s=>x.test(s))))}")
            out = subprocess.run(["node", "-e", js, json.dumps(rx), json.dumps(cases)],
                                 capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(out.returncode, 0, out.stderr)
            for line in out.stdout.split():
                self.assertEqual(json.loads(line), want, (exact, line))


class TestRanking(unittest.TestCase):
    def test_finglish_initial_vowel(self):
        fin = lambda w: [x for x, _w in kw._finglish(w)]  # noqa: E731
        self.assertIn("iran", fin("ایران"))
        self.assertNotIn("ayran", fin("ایران"))
        self.assertTrue({"open", "opn"} & set(fin("اوپن")))
        self.assertIn("instagram", fin("اینستاگرام"))
        self.assertTrue(all(x.startswith(("ij", "ej", "ey")) for x in fin("ایجنت")))
        self.assertTrue(fin("ایجنت")[0].startswith(("ij", "ej")))
        self.assertTrue(fin("آوا")[0].startswith("av"))

    def test_no_vowelless_skeletons_on_top(self):
        self.assertNotIn("hoshmsnoi", texts("هوش مصنوعی")[:30])
        v = texts("شروع")
        self.assertLess(v.index("shero"), v.index("shro"))

    def test_final_he_before_digits(self):
        fin = kw._finglish("دهه60")
        self.assertIn("dahe60", [x for x, _w in fin])
        self.assertEqual(fin[0][0], "dahe60")

    def test_prompt_common_spellings(self):
        top = texts("پرامپت")[:30]
        self.assertIn("پرومپت", top)
        self.assertIn("promt", top)
        self.assertTrue(kw.matches(rx_for("پرامپت"), "promt"))
        self.assertTrue(kw.matches(rx_for("پرامپت"), "prompts"))

    def test_latin_edits(self):
        self.assertNotIn("khatgpt", texts("ChatGPT"))
        self.assertNotIn("mkp", texts("MCP"))
        ai = texts("AI")
        self.assertNotIn("ae", ai)
        self.assertNotIn("aa", ai)
        self.assertIn("artifakt", texts("artifact"))

    def test_latin_case_label(self):
        items = kw.generate("AI")
        self.assertEqual(items[0][:1] + (items[0][2],), ("AI", ["orig"]))
        self.assertIn(("ai", ["latin_case"]), [(v, w) for v, _s, w in items])
        rx = kw.build_regex(items)
        self.assertEqual(rx.count("ai") + rx.count("AI"), 1)  # flag i covers the other case
        d = json.loads(run("ChatGPT", "--json").stdout)
        self.assertEqual(d["keyword"], "ChatGPT")


if __name__ == "__main__":
    unittest.main()
