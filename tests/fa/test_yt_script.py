"""Tests for skills/yt-script (hookscore.py, runtime.py, hooks.json) in the Persian pack."""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL = os.path.join(ROOT, "skills", "yt-script")
FIX = os.path.join(ROOT, "tests", "fixtures", "yt-script")
HOOKSCORE = os.path.join(SKILL, "hookscore.py")
RUNTIME = os.path.join(SKILL, "runtime.py")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hs = _load(HOOKSCORE, "fa_hookscore")
rt = _load(RUNTIME, "fa_runtime")
fa = hs.fa

STRONG_FA = "تو هر هفته ۳ ساعت روی تایتل یوتیوب هدر میدی و هیچکس بهت نمیگه چرا؟"
WEAK_FA = "سلام دوستان امروز یه ویدیوی فوق‌العاده داریم"


def run(tool, *args):
    return subprocess.run([sys.executable, "-I", tool] + list(args), stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True, encoding="utf-8")


class HooksJsonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(SKILL, "hooks.json"), encoding="utf-8") as fh:
            cls.data = json.load(fh)
        cls.formulas = cls.data["hooks"]

    def test_21_bilingual_formulas(self):
        self.assertEqual(len(self.formulas), 21)
        names = set()
        for f in self.formulas:
            for key in ("id", "name", "name_fa", "shape", "example", "example_en", "fails_when", "match"):
                self.assertTrue(f.get(key), (f.get("id"), key))
            self.assertTrue(fa.is_persian(f["name_fa"]), f["id"])
            self.assertTrue(fa.is_persian(f["example"]), f["id"])
            self.assertTrue(fa.is_persian(f["shape"]) and fa.is_persian(f["fails_when"]), f["id"])
            self.assertFalse(fa.is_persian(f["example_en"]), f["id"])
            for text in (f["name_fa"], f["example"], f["shape"], f["fails_when"]):
                self.assertNotRegex(text, "[يك]", "Arabic letters in %s" % f["id"])
            for p in f["match"]:
                re.compile(p)
            self.assertTrue(any(re.search("[؀-ۿ]", p) for p in f["match"]), "no Persian pattern: " + f["id"])
            names.add(f["name_fa"])
        self.assertEqual(len(names), 21)

    def test_persian_and_english_examples_classify_as_themselves_outright(self):
        for f in self.formulas:
            for key in ("example", "example_en"):
                with self.subTest(formula=f["id"], example=key):
                    own = hs.formula_hits(f, f[key])
                    self.assertGreater(own, 0)
                    for g in self.formulas:
                        if g is not f:
                            self.assertLess(hs.formula_hits(g, f[key]), own, "%s ties or beats it" % g["id"])
                    self.assertEqual(hs.classify(f[key])[0], f["name"])

    def test_classification_ignores_zwnj_and_arabic_letters(self):
        a = "می‌خوام همون پرامپتی رو که این ویدیو رو نوشت، روی صفحه نشونت بدم."
        b = "ميخوام همون پرامپتي رو كه اين ويديو رو نوشت، روي صفحه نشونت بدم."
        self.assertEqual(hs.classify(a), hs.classify(b))
        self.assertEqual(hs.classify(a)[0], "The Reveal")

    def test_persian_digits_and_words_in_patterns(self):
        self.assertEqual(hs.classify("۷ تا ابزاری که هر سازنده‌ی تازه‌کار باید بشناسه")[0], "The List")
        self.assertEqual(hs.classify("هفت تا ابزاری که هر سازنده‌ی تازه‌کار باید بشناسه")[0], "The List")
        self.assertEqual(hs.classify("تا شش دقیقه‌ی دیگه یه اسکریپت داری.")[0], "The Clock")
        self.assertEqual(hs.classify("۴۰٪ بیننده‌ها اینجا می‌رن")[0], "The Statistic")


class HookscoreTest(unittest.TestCase):
    def test_strong_persian_hook_scores_far_above_upstream(self):
        # the English-only upstream tool gave this hook 10/100 (WEAK)
        parts, verdict, name, hits = hs.score(STRONG_FA)
        self.assertGreaterEqual(verdict, 70, parts)
        self.assertEqual(hs.band(verdict), "STRONG")
        self.assertGreaterEqual(parts["ADDRESS"], 80)
        self.assertGreaterEqual(parts["BREVITY"], 100)
        self.assertGreater(hits, 0)

    def test_greeting_hook_is_weak(self):
        parts, verdict, name, hits = hs.score(WEAK_FA)
        self.assertEqual(hs.band(verdict), "WEAK")
        self.assertLess(verdict, 40)
        self.assertEqual(parts["SPECIFICITY"], 0)
        self.assertEqual(name, "Unclassified")

    def test_zwnj_and_arabic_letters_do_not_change_scores(self):
        a = "تو هر هفته ۳ ساعت روی تایتل یوتیوب هدر می‌دی و هیچ‌کس بهت نمی‌گه چرا؟"
        b = "تو هر هفته 3 ساعت روي تايتل يوتيوب هدر میدی و هيچكس بهت نميگه چرا؟"
        self.assertEqual(hs.score(a)[:2], hs.score(STRONG_FA)[:2])
        self.assertEqual(hs.score(b)[:2], hs.score(STRONG_FA)[:2])

    def test_address_suffixes_and_verbs(self):
        base = hs.address("این روش کانال رو بزرگ می‌کنه")
        for t in ("این روش کانالت رو بزرگ می‌کنه", "این روش کانالتون رو بزرگ می‌کنه",
                  "این روش ویدیوهات رو بزرگ می‌کنه", "این روش رو بهت می‌گم", "این روش رو می‌دونی",
                  "ببین این روش چی کار می‌کنه"):
            self.assertGreater(hs.address(t), base, t)
        self.assertEqual(hs.address_fa("بدون ادیتور"), 0)
        # colloquial «تو» = "in" is not the viewer
        self.assertEqual(hs.address_fa("تو این ویدیو درباره‌ی هوش مصنوعی حرف می‌زنیم"), 0)
        self.assertEqual(hs.address_fa("تو هر هفته وقت می‌ذاری"), 2)  # «بدون» = without, not «بدون!» (know)

    def test_specificity_numbers_units_brands(self):
        vague = hs.specificity("چند ساعت روی تایتل وقت می‌ذاری")
        self.assertGreater(hs.specificity("۳ ساعت روی تایتل وقت می‌ذاری"), vague)
        self.assertGreater(hs.specificity("سه ساعت روی تایتل وقت می‌ذاری"), vague)
        self.assertEqual(hs.specificity("۱۲٬۴۰۰ بازدید گرفت"), hs.specificity("12,400 بازدید گرفت"))
        self.assertGreater(hs.specificity("با Claude تایتل بنویس"), hs.specificity("با هوش تایتل بنویس"))
        self.assertGreater(hs.specificity("با کلاد تایتل بنویس"), hs.specificity("با هوش تایتل بنویس"))
        self.assertLess(hs.specificity("یه ابزار خفن و فوق‌العاده"), hs.specificity("یه ابزار"))
        # «نه» = no and «یه» = a are not numbers
        self.assertEqual(hs.numbers_fa("نه، یه ابزار دیگه")[0], 0)

    def test_stakes_and_curiosity_lexicon(self):
        self.assertGreater(hs.stakes("داری پول و وقتت رو هدر می‌دی"), hs.stakes("داری کار می‌کنی"))
        self.assertGreater(hs.stakes("قبل از اینکه آپلود کنی"), hs.stakes("وقتی آپلود کردی"))
        self.assertGreater(hs.curiosity("چرا هیچ‌کس اینو نمی‌دونه؟"), hs.curiosity("این رو همه می‌دونن."))
        self.assertLess(hs.curiosity("ویدیوت دیده نمی‌شه چون تایتلش بده"),
                        hs.curiosity("ویدیوت دیده نمی‌شه و تایتلش بده"))

    def test_curiosity_advice_matches_the_problem(self):
        self.assertIn("چون", hs.advice("CURIOSITY", "ویدیوت دیده نمی‌شه چون تایتلش بده"))
        self.assertNotIn("چون", hs.advice("CURIOSITY", "این ۳ تا اشتباه رو داری می‌کنی"))

    def test_brevity_band_in_persian_words(self):
        self.assertEqual(hs.band_words("یه متن فارسی"), (8, 22))
        self.assertEqual(hs.brevity(" ".join(["کلمه"] * 8)), 100)
        self.assertEqual(hs.brevity(" ".join(["کلمه"] * 22)), 100)
        self.assertLess(hs.brevity(" ".join(["کلمه"] * 30)), 100)
        self.assertLess(hs.brevity("کلمه کلمه"), 100)
        self.assertAlmostEqual(hs.seconds(" ".join(["کلمه"] * 12)), 5.0)

    def test_english_scoring_unchanged(self):
        self.assertEqual(hs.specificity("This is amazing."), 18)
        self.assertEqual(hs.specificity("He moved to Tokyo. Then Apple called."), 46)
        self.assertEqual(hs.band_words("Why do channels die?"), (9, 24))


class HookscoreCliTest(unittest.TestCase):
    def test_json_has_farsi_fields(self):
        r = run(HOOKSCORE, "--json", os.path.join(FIX, "hooks_fa.txt"))
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(len(out), 5)
        self.assertEqual(out[0]["hook"], STRONG_FA)  # ranked first
        self.assertEqual(out[0]["band_fa"], "قوی")
        weak = [x for x in out if x["hook"] == WEAK_FA][0]
        self.assertEqual(weak["band_fa"], "ضعیف")
        self.assertEqual(weak["formula_fa"], "بی‌فرمول")
        self.assertEqual(set(out[0]["properties_fa"]), {"دقت", "خطاب", "ریسک", "کنجکاوی", "کوتاهی"})
        self.assertTrue(fa.is_persian(out[0]["advice"]))
        en = [x for x in out if x["lang"] == "en"][0]
        self.assertEqual(en["formula"], "The Question")

    def test_text_report_is_farsi(self):
        r = run(HOOKSCORE, os.path.join(FIX, "hooks_fa.txt"))
        self.assertEqual(r.returncode, 0, r.stderr)
        for label in ("دقت", "خطاب", "ریسک", "کنجکاوی", "کوتاهی", "حکم", "قوی", "ضعیف", "فرمول",
                      "ضعیف‌ترین", "برنده:", "کلمه در ثانیه"):
            self.assertIn(label, r.stdout)
        self.assertIn("۷۴", r.stdout)  # Persian digits in the report
        self.assertNotIn("VERDICT", r.stdout)

    def test_bom_crlf_and_indent(self):
        r = run(HOOKSCORE, "--json", os.path.join(FIX, "hooks_bom_crlf.txt"))
        self.assertEqual(r.returncode, 0, r.stderr)
        hooks = [x["hook"] for x in json.loads(r.stdout)]
        self.assertIn("چرا ویدیوهات تو ثانیه‌ی سی می‌میرن؟", hooks)
        self.assertEqual(len(hooks), 2)
        self.assertFalse(any("﻿" in h for h in hooks))

    def test_errors(self):
        self.assertEqual(run(HOOKSCORE, "--hook").returncode, 2)
        r = run(HOOKSCORE, "/nonexistent/hooks.txt")
        self.assertEqual(r.returncode, 2)
        self.assertIn("پیدا نشد", r.stderr)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "empty.txt")
            open(p, "w").close()
            self.assertEqual(run(HOOKSCORE, p).returncode, 2)
            self.assertEqual(run(HOOKSCORE, d).returncode, 2)


class RuntimeTest(unittest.TestCase):
    def test_numbers_to_words(self):
        self.assertEqual(rt.int_to_words_fa(1403), "هزار و چهارصد و سه")
        self.assertEqual(rt.int_to_words_fa(200000), "دویست هزار")
        self.assertEqual(rt.int_to_words_fa(15), "پانزده")
        self.assertEqual(rt.int_to_words_fa(1000000), "یک میلیون")
        self.assertEqual(rt.int_to_words_fa(0), "صفر")
        self.assertEqual(rt.number_to_words_fa("۱۲٬۴۰۰"), "دوازده هزار و چهارصد")
        self.assertEqual(rt.number_to_words_fa("12,400"), "دوازده هزار و چهارصد")
        self.assertEqual(rt.number_to_words_fa("۱٫۵"), "یک و نیم")
        self.assertEqual(rt.number_to_words_fa("2.25"), "دو ممیز بیست و پنج")
        self.assertEqual(rt.number_to_words_fa("۳٫۰۵"), "سه ممیز صفر پنج")
        self.assertIsNone(rt.number_to_words_fa("۱۴۰۳/۰۸/۲۰"))
        self.assertIsNone(rt.number_to_words_fa("12:30"))

    def test_brackets_are_not_spoken_and_numbers_count_as_words(self):
        r = rt.analyse("## هوک\nسلام [روی صفحه: یه جمله‌ی خیلی خیلی طولانی که خونده نمی‌شه] دنیا")
        self.assertEqual(r["words"], 2)
        self.assertEqual(rt.spoken_words("۲۰۰ هزار بازدید"), 3)
        self.assertEqual(rt.spoken_words("۱۲٬۴۰۰ بازدید"), 5)

    def test_fixture_script(self):
        with open(os.path.join(FIX, "script_fa.md"), encoding="utf-8") as fh:
            r = rt.analyse(fh.read())
        self.assertEqual(r["lang"], "fa")
        self.assertEqual([b["title"] for b in r["beats"]][:2], ["هوک", "چرخش"])
        self.assertEqual(len(r["beats"]), 6)
        self.assertAlmostEqual(r["seconds"], r["words"] / 2.4, places=0)
        lo, hi = r["seconds_range"]
        self.assertLess(lo, r["seconds"])
        self.assertGreater(hi, r["seconds"])
        self.assertEqual(r["missing_on_screen"], [4])  # «بیت ۲» has no [روی صفحه: ...]
        self.assertEqual(r["asks"], ["کامنت"])
        self.assertTrue(r["first_15s"].startswith("تو هر هفته"))
        self.assertLessEqual(rt.spoken_words(r["first_15s"]), 15 * 2.4)
        self.assertEqual(r["beats"][0]["start"], 0.0)
        self.assertGreater(r["beats"][1]["start"], 0)

    def test_speed_up_shortens_runtime(self):
        text = "## الف\n" + " ".join(["کلمه"] * 48)
        self.assertAlmostEqual(rt.analyse(text)["seconds"], 20.0)
        self.assertAlmostEqual(rt.analyse(text, speed=1.2)["seconds"], 16.7)
        self.assertAlmostEqual(rt.analyse(text, rate=2.0)["seconds"], 24.0)
        self.assertNotIn("seconds_range", rt.analyse(text, rate=2.0))

    def test_paragraphs_are_beats_without_headings(self):
        r = rt.analyse("اولین پاراگراف اینجاست.\n\nدومی هم اینجاست. [روی صفحه: نمودار]")
        self.assertEqual(len(r["beats"]), 2)
        self.assertEqual(r["missing_on_screen"], [1])

    def test_more_than_one_ask(self):
        r = rt.analyse("## پایان\nسابسکرایب کن، لایک کن و کامنت کن «هوک».")
        self.assertEqual(set(r["asks"]), {"سابسکرایب", "لایک", "کامنت"})
        # a subscriber count is not an ask
        self.assertEqual(rt.asks("این کانال ۲۰۰ هزار سابسکرایبر داره"), [])

    def test_tts_lint(self):
        with open(os.path.join(FIX, "tts_fa.md"), encoding="utf-8") as fh:
            issues = rt.analyse(fh.read(), tts=True)["tts"]
        kinds = {}
        for x in issues:
            kinds.setdefault(x["kind"], []).append(x)
        self.assertIn({"kind": "عدد", "found": "۲۰۰", "fix": "دویست"}, issues)
        self.assertIn("درصد", kinds)
        self.assertEqual(kinds["لاتین"][0]["found"], "Claude")
        self.assertIn("کلاد", kinds["لاتین"][0]["fix"])
        self.assertEqual(kinds["ه ساکن"][0]["found"], "کِه")
        self.assertEqual(kinds["اضافه"][0]["found"], "خانهٔ")
        self.assertIn("خانه‌ی", kinds["اضافه"][0]["fix"])
        # clean Persian text has nothing to fix; «که» without a mark is fine
        self.assertEqual(rt.tts_issues("کامنت کن که برات بفرستم، به خانه‌ی اول برگرد."), [])

    def test_cli(self):
        r = run(RUNTIME, os.path.join(FIX, "tts_fa.md"), "--tts", "--speed", "۱٫۲")
        self.assertEqual(r.returncode, 0, r.stderr)
        for label in ("زمان اسکریپت", "بیت‌ها", "۱۵ ثانیه‌ی اول", "صدای کلون", "دویست", "هوش مصنوعی"):
            self.assertIn(label, r.stdout)
        r = run(RUNTIME, "--json", "--text", "یه متن کوتاه برای تست")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["words"], 5)
        self.assertEqual(run(RUNTIME, "--rate").returncode, 2)
        self.assertEqual(run(RUNTIME, "x.md", "--speed", "abc").returncode, 2)
        self.assertEqual(run(RUNTIME, "x.md", "--speed", "0").returncode, 2)
        self.assertEqual(run(RUNTIME, "/nonexistent/s.md").returncode, 2)
        self.assertEqual(run(RUNTIME).returncode, 1)
        self.assertEqual(run(RUNTIME, "--help").returncode, 0)


class PortabilityTest(unittest.TestCase):
    def test_skill_folder_works_alone(self):
        with tempfile.TemporaryDirectory() as d:
            dst = os.path.join(d, "yt-script")
            shutil.copytree(SKILL, dst, ignore=shutil.ignore_patterns("__pycache__"))
            r = run(os.path.join(dst, "hookscore.py"), "--json", "--hook", STRONG_FA)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout)[0]["band"], "STRONG")
            r = run(os.path.join(dst, "runtime.py"), "--text", "یه متن", "--json")
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_skill_md(self):
        with open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8") as fh:
            md = fh.read()
        self.assertTrue(md.startswith("---\nname: yt-script\n"))
        self.assertIn("دروازه", md)
        self.assertIn("منتشرش کنیم یا تغییرش بدیم؟", md)
        self.assertIn("voice.md", md)
        self.assertIn("--tts", md)
        self.assertNotRegex(md, "[يك]")
        self.assertNotIn("/Users/", md)


if __name__ == "__main__":
    unittest.main()
