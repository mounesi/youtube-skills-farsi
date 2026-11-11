# -*- coding: utf-8 -*-
"""آزمون‌های skills/yt-subtitle/fasubs.py (بازبینی زیرنویس فارسی).

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
SKILL = os.path.join(ROOT, "skills", "yt-subtitle")
TOOL = os.path.join(SKILL, "fasubs.py")
FIX = os.path.join(ROOT, "tests", "fixtures", "yt-subtitle")
ZWNJ = "‌"


def _load():
    spec = importlib.util.spec_from_file_location("yt_subtitle_fasubs", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fs = _load()


def run(*args, tool=TOOL):
    return subprocess.run([sys.executable, "-I", tool] + list(args), capture_output=True, text=True,
                          timeout=60)


def fx(name):
    return os.path.join(FIX, name)


def codes(result):
    return [i["code"] for i in result["issues"]]


def lint_text(raw, **opts):
    return fs.lint(fs.parse_blocks(raw), opts)


def srt(*cues):
    """cues: (start, end, text) -> SRT text."""
    out = []
    for n, (a, b, t) in enumerate(cues, 1):
        out.append("%d\n%s --> %s\n%s\n" % (n, a, b, t))
    return "\n".join(out)


class TestFixLine(unittest.TestCase):
    def fix(self, line, **kw):
        return fs.fix_line(line, **kw)[0]

    def test_arabic_letters(self):
        self.assertEqual(self.fix("كتاب يك"), "کتاب یک")
        self.assertEqual(self.fix("مصطفى"), "مصطفی")
        self.assertEqual(self.fix("٤٥٦ تا"), "۴۵۶ تا")

    def test_presentation_forms(self):
        # «ﻻ» و «ﻳ» (متن کپی‌شده از PDF) درست دیده می‌شوند ولی در جست‌وجو حرف دیگری‌اند
        out, found = fs.fix_line("ﻻزم نيست، ﻳک بار")
        self.assertEqual(out, "لازم نیست، یک بار")
        self.assertIn(("arabic-letter", "ﻻزم", "لازم"), found)
        self.assertFalse(any(f[0] == "fix-unsafe" for f in found))

    def test_mi_nemi(self):
        self.assertEqual(self.fix("این می شود"), "این می" + ZWNJ + "شود")
        self.assertEqual(self.fix("نمی دونم"), "نمی" + ZWNJ + "دونم")
        self.assertEqual(self.fix("مي خوام"), "می" + ZWNJ + "خوام")
        # «همی» / «کمی» are not the prefix
        self.assertEqual(self.fix("کمی صبر کن"), "کمی صبر کن")

    def test_plural(self):
        self.assertEqual(self.fix("کتاب ها رو"), "کتاب" + ZWNJ + "ها رو")
        self.assertEqual(self.fix("ویدیو های جدید"), "ویدیوهای جدید")  # «و» does not join
        self.assertEqual(self.fix("عکس هایش"), "عکس" + ZWNJ + "هایش")

    def test_plural_interjection_not_fixed(self):
        self.assertEqual(self.fix("مواظب باش ها!"), "مواظب باش ها!")
        _, found = fs.fix_line("مواظب باش ها!")
        self.assertIn("zwnj-maybe", [f[0] for f in found])
        self.assertEqual(self.fix("ها ها ها خندیدم"), "ها ها ها خندیدم")
        self.assertEqual(self.fix("آ ها فهمیدم"), "آ ها فهمیدم")

    def test_tar_tarin(self):
        self.assertEqual(self.fix("مهم ترین نکته"), "مهم" + ZWNJ + "ترین نکته")
        self.assertEqual(self.fix("سریع تر از قبل"), "سریع" + ZWNJ + "تر از قبل")
        self.assertEqual(self.fix("خیلی بزرگ تر شد"), "خیلی بزرگ" + ZWNJ + "تر شد")
        self.assertEqual(self.fix("خیلی دور تر"), "خیلی دورتر")
        # «تر» = wet: only a warning
        self.assertEqual(self.fix("دستم تر شد"), "دستم تر شد")

    def test_am_ay_after_silent_he(self):
        self.assertEqual(self.fix("من خسته ام"), "من خسته" + ZWNJ + "ام")
        self.assertEqual(self.fix("یه نکته ای"), "یه نکته" + ZWNJ + "ای")
        self.assertEqual(self.fix("رفته اند"), "رفته" + ZWNJ + "اند")
        # short function words: «که ام» is not «که‌ام»
        self.assertEqual(self.fix("گفتم که ام"), "گفتم که ام")
        # not after other letters
        self.assertEqual(self.fix("کتاب ای"), "کتاب ای")

    def test_double_zwnj_and_rlm_in_word(self):
        self.assertEqual(self.fix("می" + ZWNJ * 2 + "کنه"), "می" + ZWNJ + "کنه")
        self.assertEqual(self.fix("چی‏کار"), "چی" + ZWNJ + "کار")

    def test_punctuation(self):
        self.assertEqual(self.fix("سلام, دوستان"), "سلام، دوستان")
        self.assertEqual(self.fix("چی شد?"), "چی شد؟")
        self.assertEqual(self.fix("اول این; بعد اون"), "اول این؛ بعد اون")
        self.assertEqual(self.fix("از ChatGPT استفاده کردی یا Claude?"), "از ChatGPT استفاده کردی یا Claude؟")
        self.assertEqual(self.fix("Claude, یه ابزار"), "Claude، یه ابزار")

    def test_punctuation_left_alone(self):
        self.assertEqual(self.fix("12,400 بازدید"), "12,400 بازدید")
        self.assertEqual(self.fix("۱۲,۴۰۰ بازدید"), "۱۲,۴۰۰ بازدید")
        self.assertEqual(self.fix("Hello, how are you?"), "Hello, how are you?")
        self.assertEqual(self.fix("https://youtu.be/x?t=1 رو ببین"), "https://youtu.be/x?t=1 رو ببین")

    def test_tags_kept(self):
        self.assertEqual(self.fix("<i>چطوری مي شه?</i>"), "<i>چطوری می" + ZWNJ + "شه؟</i>")

    def test_digits_option(self):
        self.assertEqual(self.fix("قیمت 20 دلار با GPT-5", digits="fa"), "قیمت ۲۰ دلار با GPT-5")
        self.assertEqual(self.fix("سال ۲۰۲۶", digits="ascii"), "سال 2026")

    def test_rlm_option(self):
        self.assertEqual(self.fix("Claude الان جواب می‌ده", rlm=True), "‏Claude الان جواب می‌ده")
        self.assertEqual(self.fix("سلام Claude", rlm=True), "سلام Claude")

    def test_correct_text_untouched(self):
        for line in ("می‌خوام یه چیز جالب نشونت بدم", "ویدیوها و کتاب‌ها", "بزرگ‌ترین اشتباه",
                     "خسته‌ام ولی این نکته‌ای که گفتم مهمه", "سلام! چطوری؟", "میز و میوه و میلیون",
                     "این ویدیو ۱۲٬۴۰۰ بار دیده شد؛ نه بیشتر", "هم ما هم شما"):
            self.assertEqual(self.fix(line), line, line)

    def test_never_changes_words(self):
        """هر چه --fix می‌کند، حرف‌ها و ترتیبشان همان می‌ماند (جز فاصله، نیم‌فاصله و نشانه‌ی همتا)."""
        with open(fx("messy_fa.srt"), encoding="utf-8") as fh:
            raw = fh.read()
        new, _ = fs.apply_fixes(raw, fs.parse_blocks(raw))
        self.assertEqual(fs.skeleton(raw), fs.skeleton(new))
        self.assertEqual(len(raw.splitlines()), len(new.splitlines()))


class TestLint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        blocks, _, _ = fs.load_blocks(fx("messy_fa.srt"))
        cls.messy = fs.lint(blocks)

    def at(self, code):
        return sorted(i["cue"] for i in self.messy["issues"] if i["code"] == code and i["cue"])

    def test_messy_fixture(self):
        r = self.messy
        self.assertEqual(r["cues"], 14)
        self.assertEqual(self.at("overlap"), [6])
        self.assertEqual(self.at("empty"), [7])
        self.assertEqual(self.at("gap"), [3])
        self.assertEqual(self.at("short"), [4])
        self.assertEqual(self.at("long"), [5])
        self.assertEqual(self.at("lines"), [5])
        self.assertIn(6, self.at("cps"))
        self.assertIn(6, self.at("line-long"))
        self.assertEqual(sorted(set(self.at("arabic-letter"))), [1])
        self.assertEqual(sorted(set(self.at("zwnj"))), [1, 2, 3, 5, 8])
        self.assertEqual(sorted(set(self.at("zwnj-maybe"))), [9, 10])
        self.assertEqual(sorted(set(self.at("punct"))), [1, 3, 9])
        self.assertEqual(self.at("rtl-start"), [3])
        self.assertIn(5, self.at("digit-mix"))
        self.assertIn(12, self.at("digit-mix"))

    def test_levels(self):
        lv = {i["code"]: i["level"] for i in self.messy["issues"]}
        self.assertEqual(lv["overlap"], "error")
        self.assertEqual(lv["arabic-letter"], "error")
        self.assertEqual(lv["empty"], "error")
        self.assertEqual(lv["cps"], "warn")

    def test_clean_fixture_has_no_issues(self):
        blocks, _, _ = fs.load_blocks(fx("clean_fa.srt"))
        self.assertEqual(fs.lint(blocks)["issues"], [])

    def test_thresholds(self):
        raw = srt(("00:00:00,000", "00:00:02,000", "سلام"),
                  ("00:00:02,060", "00:00:04,000", "دوباره سلام"))
        self.assertIn("gap", codes(lint_text(raw)))            # 60 ms < 2 frames at 25 fps
        self.assertNotIn("gap", codes(lint_text(raw, fps=60)))  # 60 ms > 2 frames at 60 fps
        chained = srt(("00:00:00,000", "00:00:02,000", "سلام"), ("00:00:02,000", "00:00:04,000", "سلام"))
        self.assertNotIn("gap", codes(lint_text(chained)))
        long_line = srt(("00:00:00,000", "00:00:06,000", "ا" * 43))
        self.assertIn("line-long", codes(lint_text(long_line)))
        self.assertNotIn("line-long", codes(lint_text(long_line, max_chars=50)))

    def test_zwnj_and_marks_not_counted_in_length(self):
        line = ("می" + ZWNJ + "شه ") * 8 + "خب"  # 8 x 5 + 2 = 42 visible characters, 8 ZWNJ
        self.assertEqual(fs.visible_len(line.strip()), 42)
        raw = srt(("00:00:00,000", "00:00:05,000", line))
        self.assertNotIn("line-long", codes(lint_text(raw)))

    def test_bad_time_and_order(self):
        raw = srt(("00:00:05,000", "00:00:04,000", "برعکس"),
                  ("00:00:10,000", "00:00:11,000", "یک"),
                  ("00:00:08,000", "00:00:09,000", "دو"))
        c = codes(lint_text(raw))
        self.assertIn("bad-time", c)
        self.assertIn("order", c)

    def test_persian_digit_timing_and_bom(self):
        blocks, _, _ = fs.load_blocks(os.path.join(ROOT, "tests", "fixtures", "fatext", "bom_fa.srt"))
        self.assertEqual(len(blocks), 4)
        self.assertEqual(blocks[2]["start"], 4.0)
        r = fs.lint(blocks)
        self.assertIn("arabic-letter", codes(r))
        self.assertIn("short", codes(r))

    def test_vtt(self):
        blocks, _, kind = fs.load_blocks(fx("messy_fa.vtt"))
        self.assertEqual(kind, "vtt")
        self.assertEqual(len(blocks), 2)
        self.assertNotIn("NOTE", " ".join(blocks[0]["lines"]))
        self.assertNotIn("intro", " ".join(blocks[0]["lines"]))
        c = codes(fs.lint(blocks))
        self.assertIn("punct", c)
        self.assertIn("zwnj", c)

    def test_whisper_json(self):
        blocks, _, kind = fs.load_blocks(fx("whisper_fa.json"))
        self.assertEqual(kind, "json")
        self.assertEqual(len(blocks), 2)
        c = codes(fs.lint(blocks))
        self.assertIn("arabic-letter", c)
        self.assertIn("cps", c)

    def test_srt_without_blank_lines(self):
        raw = "1\n00:00:00,000 --> 00:00:02,000\nسلام\n2\n00:00:02,000 --> 00:00:04,000\nخداحافظ\n"
        blocks = fs.parse_blocks(raw)
        self.assertEqual([b["lines"] for b in blocks], [["سلام"], ["خداحافظ"]])


class TestUnsure(unittest.TestCase):
    def test_items(self):
        blocks, _, _ = fs.load_blocks(fx("messy_fa.srt"))
        items = fs.unsure_items(blocks)
        written = [i["written"] for i in items]
        for w in ("Claude", "YouTube Studio", "ChatGPT", "۲۰۲۶", "20", "12,400", "۱۲٬۵۰۰", "سیصد هزار"):
            self.assertIn(w, written)
        gpt = [i for i in items if i["written"] == "ChatGPT"][0]
        self.assertEqual(gpt["forms"], ["ChatGPT", "Chatgpt"])
        self.assertEqual(gpt["count"], 2)

    def test_numbers_inside_names_are_not_numbers(self):
        blocks = fs.parse_blocks(srt(("00:00:00,000", "00:00:03,000", "با GPT-5 و مدل 4o کار کردم، 12K بازدید")))
        items = fs.unsure_items(blocks)
        nums = [i["written"] for i in items if i["kind"] == "number"]
        self.assertEqual(nums, ["12K"])
        self.assertIn("GPT-5", [i["written"] for i in items if i["kind"] == "latin"])

    def test_spelling_choices(self):
        blocks, _, _ = fs.load_blocks(fx("messy_fa.srt"))
        choices = fs.spelling_choices(blocks)
        self.assertIn(["میخوام", "می" + ZWNJ + "خوام"], choices)

    def test_render_has_table(self):
        blocks, _, _ = fs.load_blocks(fx("messy_fa.srt"))
        out = fs.render_unsure("messy_fa.srt", blocks)
        self.assertIn("| # | زمان | شنیده | نوشته |", out)
        self.assertIn("YouTube Studio", out)
        self.assertIn("انتخاب املا", out)


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_report_and_exit_codes(self):
        p = run(fx("messy_fa.srt"))
        self.assertEqual(p.returncode, 1, p.stderr)  # errors present
        self.assertIn("بازبینی زیرنویس: messy_fa.srt", p.stdout)
        self.assertIn("خطاها:", p.stdout)
        self.assertNotIn("Traceback", p.stderr)
        self.assertNotIn(ROOT, p.stdout)  # only the file name, never the full path
        p = run(fx("clean_fa.srt"))
        self.assertEqual(p.returncode, 0)
        self.assertIn("ایرادی پیدا نشد", p.stdout)

    def test_json(self):
        p = run(fx("messy_fa.srt"), "--json")
        d = json.loads(p.stdout)
        self.assertEqual(d["cues"], 14)
        self.assertTrue(any(i["code"] == "overlap" for i in d["issues"]))

    def test_fix_writes_new_file_only(self):
        src = os.path.join(self.tmp, "subs.srt")
        shutil.copy(fx("messy_fa.srt"), src)
        with open(src, "rb") as fh:
            before = fh.read()
        p = run(src, "--fix")
        # the overlap and empty cue in messy_fa.srt are errors --fix cannot fix: still exit 1
        self.assertEqual(p.returncode, 1, p.stderr)
        out = os.path.join(self.tmp, "subs.fixed.srt")
        self.assertTrue(os.path.exists(out))
        with open(src, "rb") as fh:
            self.assertEqual(fh.read(), before)  # original untouched
        with open(out, encoding="utf-8") as fh:
            fixed = fh.read()
        self.assertIn("سلام دوستان، امروز می" + ZWNJ + "خوام یه چیز جالب", fixed)
        self.assertIn("کتاب" + ZWNJ + "ها و ویدیوهای آموزشی", fixed)
        self.assertIn("مهم" + ZWNJ + "ترین", fixed)
        self.assertIn("مواظب باش ها؛", fixed)
        self.assertIn("دستم تر شد", fixed)
        self.assertNotIn("ي", fixed)
        self.assertIn("00:00:16,000 --> 00:00:18,000", fixed)  # timing untouched
        self.assertIn("اصلاح بی‌خطر", p.stdout)
        # after the fix, no fixable issue is left
        blocks, _, _ = fs.load_blocks(out)
        self.assertFalse([i for i in fs.lint(blocks)["issues"] if i["fixable"]])

    def test_fix_keeps_bom_and_crlf(self):
        out = os.path.join(self.tmp, "c.srt")
        p = run(fx("crlf_bom_fa.srt"), "--fix", "--out", out)
        self.assertEqual(p.returncode, 0, p.stderr)
        with open(out, "rb") as fh:
            data = fh.read()
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        text = data.decode("utf-8-sig")
        self.assertEqual(text.count("\r\n"), 7)
        self.assertIn("کتاب" + ZWNJ + "ها رو ببین\r\n", text)
        self.assertIn("نمی" + ZWNJ + "دونم چرا؟", text)

    def test_fix_vtt_keeps_header(self):
        out = os.path.join(self.tmp, "v.vtt")
        run(fx("messy_fa.vtt"), "--fix", "--out", out)
        with open(out, encoding="utf-8") as fh:
            text = fh.read()
        self.assertTrue(text.startswith("WEBVTT\nKind: captions\nLanguage: fa\n"))
        self.assertIn("NOTE این یک یادداشت است", text)
        self.assertIn("align:start position:0%", text)
        self.assertIn("<i>چطوری می" + ZWNJ + "شه زیرنویس ساخت؟</i>", text)

    def test_fix_refuses_to_overwrite_input(self):
        src = os.path.join(self.tmp, "subs.srt")
        shutil.copy(fx("messy_fa.srt"), src)
        p = run(src, "--fix", "--out", src)
        self.assertEqual(p.returncode, 2)
        self.assertIn("بازنویسی نمی‌شود", p.stderr)

    def test_fix_json_refused(self):
        p = run(fx("whisper_fa.json"), "--fix", "--out", os.path.join(self.tmp, "x.srt"))
        self.assertEqual(p.returncode, 2)
        self.assertNotIn("Traceback", p.stderr)

    def test_unsure_cli(self):
        p = run(fx("messy_fa.srt"), "--unsure")
        self.assertEqual(p.returncode, 0)
        self.assertIn("شنیده ← نوشته", p.stdout)
        self.assertNotIn("شنیده → نوشته", p.stdout)
        d = json.loads(run(fx("messy_fa.srt"), "--unsure", "--json").stdout)
        self.assertTrue(d["items"])

    def test_bad_input(self):
        for args in ([], ["nope.srt"], [self.tmp], [fx("clean_fa.srt"), "--fps"],
                     [fx("clean_fa.srt"), "--fps", "abc"], [fx("clean_fa.srt"), "--bogus"],
                     [fx("clean_fa.srt"), "--digits", "fa"], [fx("clean_fa.srt"), "--fix", "--digits", "xx"]):
            p = run(*args)
            self.assertEqual(p.returncode, 2, args)
            self.assertNotIn("Traceback", p.stderr, args)

    def test_empty_file(self):
        f = os.path.join(self.tmp, "empty.srt")
        open(f, "w").close()
        p = run(f)
        self.assertEqual(p.returncode, 2)
        self.assertIn("هیچ زیرنویسی", p.stderr)

    def test_options_accept_persian_digits(self):
        p = run(fx("clean_fa.srt"), "--max-chars", "۳۰", "--json")
        d = json.loads(p.stdout)
        self.assertTrue(any(i["code"] == "line-long" for i in d["issues"]))

    def test_help(self):
        p = run("--help")
        self.assertEqual(p.returncode, 0)
        self.assertIn("بازبینی زیرنویس فارسی", p.stdout)

    def test_folder_works_alone(self):
        """کپی پوشه‌ی مهارت به تنهایی (مثل ~/.claude/skills/yt-subtitle) کار می‌کند."""
        dst = os.path.join(self.tmp, "yt-subtitle")
        shutil.copytree(SKILL, dst)
        p = run(fx("clean_fa.srt"), tool=os.path.join(dst, "fasubs.py"))
        self.assertEqual(p.returncode, 0, p.stderr)


class TestReviewFixes(unittest.TestCase):
    """رگرسیون ایرادهای بازبینی (نوامبر ۲۰۲۶)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def fix(self, line, **kw):
        return fs.fix_line(line, **kw)[0]

    def found(self, line, **kw):
        return fs.fix_line(line, **kw)[1]

    def write(self, name, data):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as fh:
            fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))
        return path

    # ---- encodings
    def test_cp1256_file(self):
        raw = "1\r\n00:00:01,000 --> 00:00:03,000\r\nسلام دوستان كتاب ها رو ببين\r\n"
        src = self.write("cp.srt", raw.encode("cp1256"))
        p = run(src, "--json")
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertIn("cp1256", p.stderr)
        self.assertIn("arabic-letter", [i["code"] for i in json.loads(p.stdout)["issues"]])
        p = run(src, "--fix")
        self.assertIn("UTF-8", p.stderr)
        with open(os.path.join(self.tmp, "cp.fixed.srt"), "rb") as fh:
            text = fh.read().decode("utf-8")  # strict: the output is UTF-8
        self.assertNotIn("�", text)
        self.assertIn("کتاب" + ZWNJ + "ها", text)
        self.assertNotIn("ك", text)
        self.assertIn("\r\n", text)

    def test_utf16_file(self):
        raw = "1\n00:00:01,000 --> 00:00:03,000\nسلام دوستان\n"
        p = run(self.write("u16.srt", raw.encode("utf-16")), "--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["cues"], 1)

    def test_undecodable_file(self):
        # Latin-1 «café»: not UTF-8, and as cp1256 it has no Persian letters
        p = run(self.write("bad.srt", b"1\n00:00:01,000 --> 00:00:03,000\ncaf\xe9\n"))
        self.assertEqual(p.returncode, 2)
        self.assertIn("UTF-8", p.stderr)
        self.assertNotIn("Traceback", p.stderr)

    # ---- unsafe lines keep their findings; LRM inside a word
    def test_lrm_inside_word(self):
        line = "چی‎کار مي کني"
        self.assertEqual(self.fix(line), "چی" + ZWNJ + "کار می" + ZWNJ + "کنی")
        r = lint_text(srt(("00:00:01,000", "00:00:03,000", line)))
        self.assertIn("arabic-letter", codes(r))

    def test_unsafe_line_still_reported(self):
        orig = fs.skeleton
        try:
            fs.skeleton = lambda t: t  # every change now looks unsafe
            new, found = fs.fix_line("كتاب ها")
            self.assertEqual(new, "كتاب ها")
            c = [f[0] for f in found]
            self.assertIn("arabic-letter", c)
            self.assertIn("fix-unsafe", c)
            r = lint_text(srt(("00:00:01,000", "00:00:03,000", "كتاب ها")))
            self.assertIn("arabic-letter", codes(r))
            self.assertIn("fix-unsafe", codes(r))
            raw = srt(("00:00:01,000", "00:00:03,000", "كتاب ها"))
            out, changes = fs.apply_fixes(raw, fs.parse_blocks(raw))
            self.assertEqual(out, raw)
            self.assertEqual([c[1] for c in changes], ["skipped"])
        finally:
            fs.skeleton = orig

    # ---- «ترین» = train
    def test_train_loanword(self):
        for line in ("مدل رو ترین کردیم", "باید مدل ترین بشه", "دیتا رو ترین کن"):
            self.assertEqual(self.fix(line), line, line)
        self.assertEqual(self.fix("بزرگ ترین مدل"), "بزرگ" + ZWNJ + "ترین مدل")
        self.assertEqual(self.fix("بزرگ ترین شهر"), "بزرگ" + ZWNJ + "ترین شهر")
        self.assertEqual(self.fix("مدل ترین"), "مدل ترین")
        self.assertEqual([f[0] for f in self.found("مدل ترین")], ["zwnj-maybe"])

    # ---- month «می»
    def test_month_may(self):
        self.assertEqual(self.fix("در ماه می سال گذشته"), "در ماه می سال گذشته")
        self.assertEqual(self.fix("۱۵ می امسال"), "۱۵ می امسال")
        self.assertIn("zwnj-maybe", [f[0] for f in self.found("در ماه می سال گذشته")])
        self.assertEqual(self.fix("ماه نمی شود"), "ماه نمی" + ZWNJ + "شود")
        self.assertEqual(self.fix("من می روم"), "من می" + ZWNJ + "روم")

    # ---- «ها» forms that are words
    def test_ha_ambiguous(self):
        for line in ("قدرت هاش ریت", "یه هات داگ", "دریاچه هامون خشک شد"):
            self.assertEqual(self.fix(line), line, line)
            self.assertEqual([f[0] for f in self.found(line)], ["zwnj-maybe"], line)
        self.assertEqual(self.fix("کتاب هایش"), "کتاب" + ZWNJ + "هایش")
        self.assertEqual(self.fix("کتاب هاشون"), "کتاب" + ZWNJ + "هاشون")

    # ---- emphasis «ها» after a verb
    def test_ha_after_imperative(self):
        for line in ("مواظب باش ها اینجا", "بیا ها اینجا"):
            self.assertEqual(self.fix(line), line, line)
            self.assertIn("zwnj-maybe", [f[0] for f in self.found(line)])
        self.assertEqual(self.fix("کتاب ها اینجا"), "کتاب" + ZWNJ + "ها اینجا")
        self.assertEqual(self.fix("قلم ها رو"), "قلم" + ZWNJ + "ها رو")

    # ---- vocative «ای» and spoken «ه»
    def test_vocative_and_pronounced_he(self):
        self.assertEqual(self.fix("خلاصه ای کاش زودتر"), "خلاصه ای کاش زودتر")
        self.assertEqual(self.fix("گروه ای از ما"), "گروه ای از ما")
        f = self.found("گروه ای از ما")
        self.assertEqual(f, [("zwnj-maybe", "گروه ای", "گروهی")])
        self.assertEqual(self.fix("یه نکته ای"), "یه نکته" + ZWNJ + "ای")

    # ---- bare ezafe «ی»
    def test_ezafe_ye(self):
        self.assertEqual(self.fix("درباره ی این"), "درباره" + ZWNJ + "ی این")
        self.assertEqual(self.fix("خونه ی قشنگ"), "خونه" + ZWNJ + "ی قشنگ")
        for line in ("خونه یه", "خونه یک", "به ی"):
            self.assertEqual(self.fix(line), line, line)
        self.assertIn("zwnj", codes(lint_text(srt(("00:00:01,000", "00:00:03,000", "درباره ی این خونه ی قشنگ")))))

    # ---- markup and entities
    def test_entities_kept(self):
        self.assertEqual(self.fix("&rlm;سلام دنیا"), "&rlm;سلام دنیا")
        self.assertEqual(self.fix("سلام&nbsp;دنیا"), "سلام&nbsp;دنیا")
        self.assertEqual(self.fix("&#8207;سلام دنیا"), "&#8207;سلام دنیا")
        self.assertEqual(self.fix("&rlm;سلام, دنیا"), "&rlm;سلام، دنیا")

    def test_digits_not_in_markup(self):
        self.assertEqual(self.fix("<00:00:01.500><c>سلام 12</c>", digits="fa"), "<00:00:01.500><c>سلام ۱۲</c>")
        self.assertEqual(self.fix('<font color="#00FF00">سلام 5</font>', digits="fa"),
                         '<font color="#00FF00">سلام ۵</font>')
        self.assertEqual(self.fix("{\\pos(100,200)}سلام 3", digits="fa"), "{\\pos(100,200)}سلام ۳")
        self.assertEqual(self.fix('<font face="كوفي">كتاب</font>'), '<font face="كوفي">کتاب</font>')

    # ---- broken timing lines
    def test_broken_timing_not_dropped(self):
        for bad in ("00:00:03,500 -> 00:00:05,000", "00:00:03,500 -->"):
            raw = ("1\n00:00:01,000 --> 00:00:03,000\nیک\n\n2\n%s\nدو\n\n"
                   "3\n00:00:05,000 --> 00:00:07,000\nسه\n" % bad)
            blocks = fs.parse_blocks(raw)
            self.assertEqual(len(blocks), 3, bad)
            self.assertEqual(blocks[1]["lines"], ["دو"])
            p = run(self.write("arrow.srt", raw), "--json")
            self.assertEqual(p.returncode, 1, bad)
            self.assertIn("bad-time", [i["code"] for i in json.loads(p.stdout)["issues"]])

    def test_vtt_header_not_a_cue(self):
        raw = "WEBVTT\n\nNOTE hi\n\n00:00:01.000 --> 00:00:02.000\nسلام\n"
        self.assertEqual(len(fs.parse_blocks(raw)), 1)

    # ---- Persian digits in timing
    def test_timing_digits(self):
        raw = "1\r\n۰۰:۰۰:۰۱,۰۰۰ --> ۰۰:۰۰:۰۳٫۰۰۰\r\nسلام دوستان\r\n"
        self.assertIn("timing-digits", codes(lint_text(raw)))
        out = os.path.join(self.tmp, "t.fixed.srt")
        p = run(self.write("t.srt", raw), "--fix", "--out", out)
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        with open(out, "rb") as fh:
            text = fh.read().decode("utf-8")
        tline = text.split("\r\n")[1]
        self.assertEqual(tline, "00:00:01,000 --> 00:00:03,000")
        self.assertEqual(text.count("\r\n"), 3)
        vtt = "WEBVTT\n\n۰۰:۰۰:۰۱٫۰۰۰ --> ۰۰:۰۰:۰۳٫۰۰۰ align:start\nسلام\n"
        new, _ = fs.apply_fixes(vtt, fs.parse_blocks(vtt), kind="vtt")
        self.assertIn("00:00:01.000 --> 00:00:03.000 align:start\n", new)

    # ---- RLM already there
    def test_rlm_not_flagged_twice(self):
        src = self.write("r.srt", srt(("00:00:01,000", "00:00:03,000", "AI الان همه جا هست")))
        out = os.path.join(self.tmp, "r2.srt")
        run(src, "--fix", "--rlm", "--out", out)
        p = run(out, "--json")
        self.assertNotIn("rtl-start", [i["code"] for i in json.loads(p.stdout)["issues"]])
        for line in ("<i>‏AI الان</i>", "&rlm;AI الان"):
            self.assertEqual(self.fix(line, rlm=True), line)
            self.assertNotIn("rtl-start", codes(lint_text(srt(("00:00:01,000", "00:00:03,000", line)))))

    # ---- --fix exit code and overwrite guard
    def test_fix_exit_code_and_overwrite(self):
        raw = srt(("00:00:01,000", "00:00:04,000", "مي خوام"), ("00:00:03,000", "00:00:05,000", "دو"))
        src = self.write("ov.srt", raw)
        out = os.path.join(self.tmp, "ov.fixed.srt")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write("دستی اصلاح شده")
        p = run(src, "--fix")
        self.assertEqual(p.returncode, 2)
        self.assertIn("--force", p.stderr)
        with open(out, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "دستی اصلاح شده")
        p = run(src, "--fix", "--force", "--json")
        self.assertEqual(p.returncode, 1, p.stderr)  # the overlap is still an error
        d = json.loads(p.stdout)
        self.assertEqual(d["errors"], 1)
        p = run(src, "--fix")  # identical output: fine without --force
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertIn("خطا و", p.stdout)
        self.assertEqual(run(src, "--force").returncode, 2)  # --force only with --fix

    def test_fix_header_names_output(self):
        src = self.write("m.srt", srt(("00:00:01,000", "00:00:03,000", "مي خوام")))
        p = run(src, "--fix")
        self.assertEqual(p.returncode, 0, p.stderr)
        first = p.stdout.splitlines()[0]
        self.assertIn("اصلاح‌شده: m.fixed.srt", first)
        self.assertNotIn("←", first)

    # ---- Whisper JSON: no per-line length
    def test_json_capacity(self):
        seg74 = "این یک جمله‌ی معمولی است که ویسپر در یک تکه برگردانده و طولش زیاد است"
        seg100 = seg74 + " و این هم بقیه‌ی همان جمله که دیگر جا نمی‌شود"
        self.assertGreater(fs.visible_len(seg74), 42)
        self.assertGreater(fs.visible_len(seg100), 84)
        d = {"segments": [{"start": 0, "end": 6, "text": seg74}, {"start": 7, "end": 14, "text": seg100}]}
        p = run(self.write("w.json", json.dumps(d, ensure_ascii=False)), "--json")
        issues = json.loads(p.stdout)["issues"]
        self.assertNotIn("line-long", [i["code"] for i in issues])
        self.assertEqual([i["cue"] for i in issues if i["code"] == "capacity"], [2])


class TestSkillDoc(unittest.TestCase):
    def test_skill_md(self):
        with open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8") as fh:
            doc = fh.read()
        self.assertTrue(doc.startswith("---\nname: yt-subtitle\n"))
        self.assertIn("شنیده → نوشته", doc)
        self.assertIn("## دروازه", doc)
        self.assertTrue(doc.rstrip().endswith("**منتشرش کنیم یا تغییرش بدیم؟**"))
        self.assertIn("description: >-", doc)
        self.assertNotIn("/Users/", doc)


if __name__ == "__main__":
    unittest.main()
