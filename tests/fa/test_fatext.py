# -*- coding: utf-8 -*-
"""آزمون‌های lib/fatext.py (کتابخانه‌ی مشترک متن فارسی) و کپی‌های _fatext.py.

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
LIB = os.path.join(ROOT, "lib", "fatext.py")
FIX = os.path.join(ROOT, "tests", "fixtures", "fatext")
ZWNJ = "‌"


def _load(path, name="fatext_under_test"):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fa = _load(LIB)


class TestNormalize(unittest.TestCase):
    def test_arabic_letters(self):
        self.assertEqual(fa.normalize("كتاب يك"), "کتاب یک")
        self.assertEqual(fa.normalize("مصطفى"), "مصطفی")
        self.assertNotIn("ي", fa.normalize("علي"))

    def test_taa_marbuta_off_by_default(self):
        self.assertEqual(fa.normalize("مدرسة"), "مدرسة")
        self.assertEqual(fa.normalize("مدرسة", taa_marbuta=True), "مدرسه")

    def test_tatweel_and_bidi(self):
        self.assertEqual(fa.normalize("ســـلام"), "سلام")
        self.assertEqual(fa.normalize("﻿‏سلام‎ ‫دنیا‬⁧!⁩"), "سلام دنیا!")

    def test_zwnj_collapse_and_edges(self):
        self.assertEqual(fa.normalize("می" + ZWNJ * 3 + "خوام"), "می" + ZWNJ + "خوام")
        self.assertEqual(fa.normalize("کتاب " + ZWNJ + "ها"), "کتاب ها")
        self.assertEqual(fa.normalize(ZWNJ + "سلام" + ZWNJ), "سلام")

    def test_zwnj_variants(self):
        # zero-width space and soft hyphen used where a ZWNJ was meant
        self.assertEqual(fa.normalize("می​شود"), "می" + ZWNJ + "شود")
        self.assertEqual(fa.normalize("ویدیو­ها"), "ویدیو" + ZWNJ + "ها")
        self.assertEqual(fa.normalize("a​ b"), "a b")

    def test_spaces_and_lines(self):
        self.assertEqual(fa.normalize("سلام    دنیا !  \n  خط دوم  "), "سلام دنیا !\nخط دوم")
        self.assertEqual(fa.normalize("a\r\nb"), "a\nb")

    def test_diacritics_optional(self):
        self.assertEqual(fa.normalize("مُحَمَّد"), "مُحَمَّد")
        self.assertEqual(fa.normalize("مُحَمَّد", diacritics=True), "محمد")
        self.assertEqual(fa.normalize("اِ", diacritics=True), "ا")

    def test_presentation_forms(self):
        self.assertEqual(fa.normalize("ﺳﻼﻡ"), "سلام")

    def test_digits_option(self):
        self.assertEqual(fa.normalize("ويديو ۱۲", digits="ascii"), "ویدیو 12")
        self.assertEqual(fa.normalize("قسمت 3", digits="fa"), "قسمت ۳")

    def test_english_untouched(self):
        self.assertEqual(fa.normalize("Hello, World!"), "Hello, World!")
        self.assertEqual(fa.normalize(""), "")
        self.assertEqual(fa.normalize(None), "")

    def test_fold(self):
        self.assertEqual(fa.fold("می" + ZWNJ + "خوام"), fa.fold("میخوام"))
        self.assertEqual(fa.fold("آرتیفکت"), fa.fold("ارتیفکت"))
        self.assertEqual(fa.fold("Claude ۱۲"), "claude 12")


class TestDigits(unittest.TestCase):
    def test_ascii(self):
        self.assertEqual(fa.to_ascii_digits("۰۱۲۳۴۵۶۷۸۹"), "0123456789")
        self.assertEqual(fa.to_ascii_digits("٠١٢٣٤٥٦٧٨٩"), "0123456789")
        self.assertEqual(fa.to_ascii_digits("قسمت ۱۲"), "قسمت 12")

    def test_fa(self):
        self.assertEqual(fa.to_fa_digits("12:05"), "۱۲:۰۵")
        self.assertEqual(fa.to_fa_digits("٤٥"), "۴۵")
        self.assertEqual(fa.to_fa_digits("1.5 و 12,400", separators=True), "۱٫۵ و ۱۲٬۴۰۰")


class TestParseNumber(unittest.TestCase):
    CASES = [
        ("۱٫۲ هزار", 1200), ("1.2K", 1200), ("1.2k", 1200), ("۳ میلیون", 3e6), ("12,400", 12400),
        ("۱۲٬۴۰۰", 12400), ("4.5M views", 4.5e6), ("۱۲ هزار بازدید", 12000), ("1.2B", 1.2e9),
        ("۱۲،۴۰۰", 12400), ("٤٥", 45), ("1,234,567", 1234567), ("1.234.567", 1234567), ("1,5", 1.5),
        ("1,234.5", 1234.5), ("1.234,5", 1234.5), ("۱/۵ میلیون", 1.5e6), ("45%", 45), ("٪۴۵", 45),
        ("−۳", -3), ("-3", -3), ("۱۲" + ZWNJ + "هزار", 12000), ("2 میلیارد", 2e9), ("10 کا", 10000),
        ("1.5 million", 1.5e6), ("بازدید: ۸۵۰", 850), ("12 هزارتا", 12000), ("۳ میلیونی", 3e6),
        ("یک و نیم میلیون", 1.5e6), ("سیصد هزار بازدید", 3e5), ("هزار", 1000), ("حدود دویست هزار", 2e5),
        ("بیست و پنج", 25), (1200, 1200), (3.5, 3.5),
        # spelled half: «نیم» before a scale is half of it, «… و نیم» after a scale is half of that scale
        ("نیم میلیون", 5e5), ("دو میلیون و نیم", 2.5e6), ("سه هزار و نیم", 3500), ("هزار و نیم", 1500),
        ("دو و نیم", 2.5), ("دو میلیون و سیصد هزار", 2.3e6),
        # leading decimal separator
        (".5k", 500), ("٫۵", 0.5), ("٫۵ میلیون", 5e5), ("-.5", -0.5),
    ]

    def test_forms(self):
        for s, want in self.CASES:
            with self.subTest(s=s):
                self.assertAlmostEqual(fa.parse_number(s), float(want))

    def test_no_number(self):
        for s in ("", None, "abc", "بازدید نداره", "نه", "یه ویدیو", "1,2,3", "۱۴۰۳/۰۸/۲۰", "سلام دنیا"):
            with self.subTest(s=s):
                self.assertIsNone(fa.parse_number(s))

    def test_suffix_must_end(self):
        self.assertEqual(fa.parse_number("5 minutes"), 5.0)
        self.assertEqual(fa.parse_number("۵ کانال"), 5.0)
        self.assertEqual(fa.parse_number("3 books"), 3.0)

    def test_single_letter_suffix_must_touch(self):
        self.assertEqual(fa.parse_number("4.5M"), 4.5e6)
        self.assertEqual(fa.parse_number("1.2B"), 1.2e9)
        self.assertEqual(fa.parse_number("2m"), 2e6)
        self.assertEqual(fa.parse_number("5 m"), 5.0)  # "m" may be minutes or metres
        self.assertEqual(fa.parse_number("5 b"), 5.0)
        self.assertEqual(fa.parse_number("1.5 million"), 1.5e6)
        self.assertEqual(fa.parse_number("a.5"), 5.0)  # a dot glued to a word is not a decimal point

    def test_not_finite(self):
        self.assertIsNone(fa.parse_number(float("inf")))
        self.assertIsNone(fa.parse_number(float("nan")))

    def test_hyphen_inside_text_not_negative(self):
        self.assertEqual(fa.parse_number("1080-1920"), 1080.0)
        self.assertEqual(fa.parse_number("x-3"), 3.0)



class TestParseNumberStrict(unittest.TestCase):
    """strict=True: the whole text must be one number; nothing is dropped silently."""
    OK = [
        ("۱۲ هزار و ۵۰۰ بازدید", 12500), ("۲ میلیون و ۳۰۰ هزار", 2.3e6), ("۱۲٬۴۰۰", 12400),
        ("12.4K", 12400), ("۱/۵ میلیون", 1.5e6), ("سیصد هزار", 3e5), ("۸۷٪", 87), ("٪۴۵", 45),
        ("حدود ۱۲ هزار بازدید", 12000), ("بیش از ۱۰ هزار", 1e4), ("−۳", -3), ("12 هزارتا", 12000),
        ("۳ میلیونی", 3e6), ("10 کا", 1e4), ("1.5 million", 1.5e6), ("۱۲" + ZWNJ + "هزار", 12000),
        ("نیم میلیون", 5e5), ("دو میلیون و نیم", 2.5e6), ("یک و نیم میلیون", 1.5e6),
        ("صد و بیست و پنج", 125), ("هزار", 1000), (".5k", 500), ("٫۵", 0.5), ("4.5M", 4.5e6), (95, 95),
    ]
    BAD = [
        "بین 5 تا 8 هزار", "12K-15K", "زیاد 5", "ساعت 8:30", "8:30", "2026-11-11", "3/4 of viewers",
        "۵ هزار و ۳ میلیون", "5 8", "12 و 5", "هزار و ۲۰۰۰", "و ۵", "۵ و", "دو میلیون سیصد هزار", "5 m",
        "1,2,3", "۱۴۰۳/۰۸/۲۰", "abc", "", None, "نه", "یه", "ده", "نیم", "بازدید",
    ]

    def test_ok(self):
        for s, want in self.OK:
            with self.subTest(s=s):
                self.assertAlmostEqual(fa.parse_number(s, strict=True), float(want))

    def test_rejected(self):
        for s in self.BAD:
            with self.subTest(s=s):
                self.assertIsNone(fa.parse_number(s, strict=True))

    def test_lenient_default_unchanged(self):
        self.assertEqual(fa.parse_number("زیاد 5"), 5.0)
        self.assertEqual(fa.parse_number("بازدید: ۸۵۰"), 850.0)
        self.assertIsNone(fa.parse_number("بازدید: ۸۵۰", strict=True))

class TestTokenize(unittest.TestCase):
    def test_persian_zwnj_kept(self):
        self.assertEqual(fa.tokenize("من می" + ZWNJ + "خوام ویدیو" + ZWNJ + "ها رو ببینم."),
                         ["من", "می" + ZWNJ + "خوام", "ویدیو" + ZWNJ + "ها", "رو", "ببینم"])

    def test_persian_punctuation_stripped(self):
        self.assertEqual(fa.tokenize("سلام، دنیا؛ «چطوری»؟ …خب!"), ["سلام", "دنیا", "چطوری", "خب"])

    def test_numbers_one_token(self):
        self.assertEqual(fa.tokenize("۱٫۵ میلیون و 12,400 و ۱۲٬۴۰۰ و 3.5"),
                         ["۱٫۵", "میلیون", "و", "12,400", "و", "۱۲٬۴۰۰", "و", "3.5"])

    def test_latin(self):
        self.assertEqual(fa.tokenize("Don't stop, it's mind-blowing... OK?"),
                         ["Don't", "stop", "it's", "mind-blowing", "OK"])

    def test_mixed_and_hashtag(self):
        self.assertEqual(fa.tokenize("با Claude کار کن #هوش_مصنوعی"),
                         ["با", "Claude", "کار", "کن", "هوش", "مصنوعی"])

    def test_normalizes_first(self):
        self.assertEqual(fa.tokenize("كتاب ي"), ["کتاب", "ی"])
        self.assertEqual(fa.tokenize("مُحَمَّد"), ["مُحَمَّد"])

    def test_word_count(self):
        self.assertEqual(fa.word_count("خب امروز می" + ZWNJ + "خوایم با Claude یه اپ بسازیم!"), 8)
        self.assertEqual(fa.word_count(""), 0)
        self.assertEqual(fa.word_count("… ، ؟"), 0)

    def test_norm_words(self):
        self.assertEqual(fa.norm_words("تو کلاد بخش"), fa.norm_words("تو  كلاد بخش…"))
        self.assertEqual(fa.norm_words("قسمت ۲"), ["قسمت", "2"])
        self.assertNotEqual(fa.norm_words("قسمت ۲"), fa.norm_words("قسمت ۳"))


class TestScript(unittest.TestCase):
    def test_ratio(self):
        self.assertEqual(fa.script_ratio("سلام"), 1.0)
        self.assertEqual(fa.script_ratio("hello"), 0.0)
        self.assertEqual(fa.script_ratio("۱۲۳ !"), 0.0)
        self.assertAlmostEqual(fa.script_ratio("سلام abcd"), 0.5)

    def test_counts(self):
        self.assertEqual(fa.script_counts("سلام hi Привет"), {"fa": 4, "latin": 2, "other": 6})

    def test_is_persian(self):
        self.assertTrue(fa.is_persian("امروز با Claude یه اپ ساختم"))
        self.assertFalse(fa.is_persian("Today I built an app with Claude"))
        self.assertFalse(fa.is_persian(""))

    def test_latin_tokens(self):
        t = "امروز با Claude و ChatGPT توی YouTube Studio کار کردیم."
        self.assertEqual(fa.latin_tokens(t), ["Claude", "ChatGPT", "YouTube", "Studio"])
        self.assertEqual(fa.latin_tokens(t, phrases=True), ["Claude", "ChatGPT", "YouTube Studio"])
        self.assertEqual(fa.latin_tokens("فقط فارسی ۱۲"), [])
        self.assertEqual(fa.latin_tokens("مدل GPT-5 اومد", phrases=True), ["GPT-5"])


class TestTimestamps(unittest.TestCase):
    CASES = [
        ("1:02:03", 3723), ("02:03", 123), ("00:00:01,000", 1), ("00:00:01.250", 1.25), ("00:01.500", 1.5),
        ("۰۱:۲۳", 83), ("۱:۰۲:۰۳,۵۰۰", 3723.5), ("00:00:01٫500", 1.5), ("75", 75), ("75.5", 75.5),
        ("1h2m3s", 3723), ("2m", 120), ("90s", 90), ("75:10", 4510), (12, 12.0), ("  0:00 ", 0),
    ]

    def test_parse(self):
        for s, want in self.CASES:
            with self.subTest(s=s):
                self.assertAlmostEqual(fa.parse_timestamp(s), float(want))

    def test_parse_bad(self):
        for s in ("", None, "abc", "1:75", "1:60:00", "-1", "1:02:03:04", "1::2", -5):
            with self.subTest(s=s):
                self.assertIsNone(fa.parse_timestamp(s))

    def test_fmt(self):
        self.assertEqual(fa.fmt_timestamp(0), "0:00")
        self.assertEqual(fa.fmt_timestamp(65.9), "1:05")
        self.assertEqual(fa.fmt_timestamp(3725.25), "1:02:05")
        self.assertEqual(fa.fmt_timestamp(65, fa_digits=True), "۱:۰۵")
        self.assertEqual(fa.fmt_timestamp(3725.25, "srt"), "01:02:05,250")
        self.assertEqual(fa.fmt_timestamp(1.9996, "vtt"), "00:00:02.000")
        self.assertEqual(fa.fmt_timestamp(5, "clock"), "00:00:05")
        self.assertEqual(fa.fmt_timestamp(-3), "0:00")
        with self.assertRaises(ValueError):
            fa.fmt_timestamp(1, "nope")

    def test_round_trip(self):
        for t in (0, 1.25, 59.999, 3600, 3723.5):
            with self.subTest(t=t):
                self.assertAlmostEqual(fa.parse_timestamp(fa.fmt_timestamp(t, "srt")), round(t, 3))
                self.assertAlmostEqual(fa.parse_timestamp(fa.fmt_timestamp(t, "vtt", fa_digits=True)), round(t, 3))


class TestCues(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name, data):
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as fh:
            fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))
        return p

    def test_bom_srt_fixture(self):
        cues = fa.load_cues(os.path.join(FIX, "bom_fa.srt"))
        self.assertEqual(len(cues), 4)
        self.assertEqual(cues[0].start, 0.0)
        self.assertEqual(cues[0].text, "سلام دوستان، امروز می" + ZWNJ + "خوام یه چیزی بگم")
        self.assertEqual(cues[2].start, 4.0)  # Persian digits in the timing line
        self.assertEqual(cues[2].text, "کلاد چیکار می" + ZWNJ + "کنه؟")  # Arabic letters, RLM, double ZWNJ fixed
        self.assertEqual(cues[3].text, "۴۲")  # a bare number is speech
        self.assertTrue(fa.is_filler_only(cues[1].text))

    def test_raw_text_option(self):
        cues = fa.load_cues(os.path.join(FIX, "bom_fa.srt"), normalized=False)
        self.assertIn("ك", cues[2].text)

    def test_youtube_auto_vtt_fixture(self):
        cues = fa.load_cues(os.path.join(FIX, "youtube_auto_fa.vtt"))
        self.assertEqual([c.text for c in cues],
                         ["خب امروز می" + ZWNJ + "خوایم با Claude", "یه اپ کوچیک بسازیم", "و منتشرش کنیم"])
        self.assertFalse(any("یادداشت" in c.text or "cue-9" in c.text for c in cues))

    def test_whisper_list_fixture(self):
        cues = fa.load_cues(os.path.join(FIX, "whisper_list_fa.json"))
        self.assertEqual(cues, [fa.Cue(0.0, 2.0, "سلام به همه"), fa.Cue(5.0, 7.5, "۱٫۲ میلیون بازدید")])

    def test_whisper_words_fixture(self):
        p = os.path.join(FIX, "whisper_words_fa.json")
        self.assertEqual([c.text for c in fa.load_cues(p)], ["سلام دوستان", "Claude Code"])
        words = fa.load_cues(p, words=True)
        self.assertEqual([c.text for c in words], ["سلام", "دوستان", "Claude", "Code"])
        self.assertEqual(words[2], fa.Cue(2.0, 2.4, "Claude"))

    def test_bare_word_list_grouped(self):
        raw = json.dumps([{"word": " سلام", "start": 0, "end": 0.4}, {"word": " دوستان.", "start": 0.5, "end": 1},
                          {"word": " امروز", "start": 2, "end": 2.5}, {"word": " بریم", "start": 2.6, "end": 3}])
        self.assertEqual(fa.parse_cues(raw), [fa.Cue(0.0, 1.0, "سلام دوستان."), fa.Cue(2.0, 3.0, "امروز بریم")])
        self.assertEqual(len(fa.parse_cues(raw, words=True)), 4)

    def test_segment_words_without_text(self):
        raw = json.dumps({"segments": [{"start": 0, "end": 2, "words": [
            {"word": "hi", "start": 0, "end": 1}, {"word": "there", "start": 1, "end": 2}]}]})
        self.assertEqual(fa.parse_cues(raw), [fa.Cue(0.0, 2.0, "hi there")])

    def test_other_json_shapes(self):
        cpp = json.dumps({"transcription": [{"offsets": {"from": 0, "to": 1500}, "text": " سلام"},
                                            {"timestamps": {"from": "00:00:02,000", "to": "00:00:03,000"},
                                             "text": " دنیا"}]})
        self.assertEqual(fa.parse_cues(cpp), [fa.Cue(0.0, 1.5, "سلام"), fa.Cue(2.0, 3.0, "دنیا")])
        hf = json.dumps({"text": "a b", "chunks": [{"timestamp": [0, 1.2], "text": "a"},
                                                   {"timestamp": [1.2, None], "text": "b"}]})
        self.assertEqual(fa.parse_cues(hf), [fa.Cue(0.0, 1.2, "a"), fa.Cue(1.2, 1.2, "b")])
        self.assertEqual(fa.parse_cues('{"text": "no timing"}'), [])
        self.assertEqual(fa.parse_cues("[1, 2, null]"), [])

    def test_bom_json_uppercase_ext(self):
        p = self.write("t.JSON", b'\xef\xbb\xbf{"segments":[{"start":0,"end":2,"text":"\xd8\xb3\xd9\x84\xd8\xa7\xd9\x85"}]}')
        self.assertEqual(fa.load_cues(p), [fa.Cue(0.0, 2.0, "سلام")])

    def test_srt_sorted_and_tags(self):
        raw = ("2\n00:00:10,000 --> 00:00:12,000\n<i>دومی</i> {\\an8}&amp; بعد\n\n"
               "1\n00:00:00,000 --> 00:00:02,000\nاولی\nخط دوم\n")
        cues = fa.parse_cues(raw)
        self.assertEqual([c.text for c in cues], ["اولی خط دوم", "دومی & بعد"])
        self.assertEqual(fa.duration(cues), 12.0)

    def test_srt_without_blank_lines(self):
        raw = "1\n00:00:00,000 --> 00:00:01,000\nسلام\n2\n00:00:01,500 --> 00:00:02,000\nدنیا\n"
        self.assertEqual([c.text for c in fa.parse_cues(raw)], ["سلام", "دنیا"])

    def test_crlf_and_vtt_ids(self):
        raw = ("WEBVTT\r\n\r\nc1\r\n00:00.000 --> 00:02.000\r\nخوش اومدین\r\n\r\n"
               "NOTE یادداشت\r\n\r\nc2\r\n00:03.000 --> 00:04.000\r\nبریم\r\n")
        self.assertEqual([c.text for c in fa.parse_cues(raw)], ["خوش اومدین", "بریم"])

    def test_bad_timing_skipped_and_empty_dropped(self):
        raw = ("1\n00:00:00,000 --> 00:00:99,000\nبد\n\n2\n00:00:01,000 --> 00:00:02,000\n\n\n"
               "3\n00:00:03,000 --> 00:00:04,000\nخوب\n")
        self.assertEqual([c.text for c in fa.parse_cues(raw)], ["خوب"])

    def test_duration_max_end(self):
        cues = [fa.Cue(0, 30, "a"), fa.Cue(5, 6, "b")]
        self.assertEqual(fa.duration(cues), 30)
        self.assertEqual(fa.duration([]), 0.0)

    def test_plain_vtt_keeps_repeated_single_lines(self):
        raw = ("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nسلام\n\n00:00:03.100 --> 00:00:05.000\nآره\n\n"
               "00:00:05.100 --> 00:00:07.000\nآره\n\n00:00:07.000 --> 00:00:08.000\n[موسیقی]\n\n"
               "00:00:08.000 --> 00:00:09.000\n[موسیقی]\n")
        p = self.write("rep.vtt", raw)
        self.assertEqual([c.text for c in fa.load_cues(p)], ["سلام", "آره", "آره", "[موسیقی]", "[موسیقی]"])

    def test_youtube_auto_vtt_still_dedupes(self):
        raw = ("WEBVTT\nKind: captions\n\n"
               "00:00:00.000 --> 00:00:02.000\nسلام<00:00:00.500><c> دوستان</c>\n\n"
               "00:00:02.000 --> 00:00:02.010\nسلام دوستان\n\n"
               "00:00:02.010 --> 00:00:04.000\nسلام دوستان\nامروز<00:00:02.500><c> بریم</c>\n\n"
               "00:00:04.000 --> 00:00:06.000\nامروز بریم\n")
        self.assertEqual([c.text for c in fa.parse_cues(raw)], ["سلام دوستان", "امروز بریم"])

    def test_utf16_srt(self):
        raw = "1\n00:00:00,000 --> 00:00:02,000\nسلام دوستان\n\n2\n00:00:03,000 --> 00:00:04,000\nبریم\n"
        for enc in ("utf-16", "utf-16-le", "utf-16-be"):
            with self.subTest(enc=enc):
                p = self.write("u16-%s.srt" % enc, raw.encode(enc))
                self.assertEqual([c.text for c in fa.load_cues(p)], ["سلام دوستان", "بریم"])

    def test_cp1256_srt(self):
        # Persian ی (U+06CC) is not in cp1256; old Windows files carry Arabic ي (U+064A) instead
        raw = "1\n00:00:00,000 --> 00:00:02,000\nسلام دوستان، امروز مي‌خوايم\n"
        p = self.write("old.srt", raw.encode("cp1256"))
        cues = fa.load_cues(p, normalized=False)
        self.assertEqual(cues[0].text, "سلام دوستان، امروز می‌خوایم")
        self.assertNotIn("\ufffd", cues[0].text)

    def test_decode_bytes(self):
        self.assertEqual(fa.decode_bytes("سلام".encode("utf-8")), "سلام")
        self.assertEqual(fa.decode_bytes(b"\xef\xbb\xbf" + "سلام".encode("utf-8")), "سلام")
        self.assertEqual(fa.decode_bytes("a,b\n1,2\n".encode("utf-16")), "a,b\n1,2\n")
        self.assertEqual(fa.decode_bytes("كتاب".encode("cp1256")), "کتاب")
        self.assertEqual(fa.decode_bytes(b""), "")

    def test_tags_keep_real_text(self):
        self.assertEqual(fa.clean_cue_text("اگه x < 10 باشه و y > 3"), "اگه x < 10 باشه و y > 3")
        self.assertEqual(fa.clean_cue_text("از {name} استفاده کن"), "از {name} استفاده کن")
        self.assertEqual(fa.clean_cue_text("List<int>"), "List<int>")
        self.assertEqual(fa.clean_cue_text("اگر a<b و c>d"), "اگر a<b و c>d")
        self.assertEqual(fa.clean_cue_text('<font color="#ffff00">زرد</font> <b>پررنگ</b> {\\an8}بالا'),
                         "زرد پررنگ بالا")
        self.assertEqual(fa.clean_cue_text("<v Al>سلام</v> <c.colorE5E5E5>دنیا</c><00:00:01.000>"), "سلام دنیا")
        self.assertEqual([c.text for c in fa.parse_cues("1\n00:00:00,000 --> 00:00:01,000\nاگر a < b و c > d\n")],
                         ["اگر a < b و c > d"])

    def test_json_text_never_tag_stripped(self):
        raw = json.dumps([{"start": 0, "end": 1, "text": "<i> یعنی x < 10 و {name}"}])
        self.assertEqual(fa.parse_cues(raw)[0].text, "<i> یعنی x < 10 و {name}")
        raw = json.dumps({"words": [{"word": "<b>", "start": 0, "end": 0.5}, {"word": "{x}", "start": 0.5, "end": 1}]})
        self.assertEqual([c.text for c in fa.parse_cues(raw, words=True)], ["<b>", "{x}"])

    def test_json_bad_times_dropped(self):
        raw = ('[{"start": Infinity, "end": 2, "text": "inf"}, {"start": NaN, "end": 3, "text": "nan"},'
               ' {"start": -1, "end": 1, "text": "neg"}, {"start": 1e400, "end": 2, "text": "big"},'
               ' {"start": 5, "end": Infinity, "text": "endinf"}, {"start": 1, "end": 2, "text": "ok"}]')
        self.assertEqual(fa.parse_cues(raw), [fa.Cue(1.0, 2.0, "ok")])
        self.assertIsNone(fa.parse_timestamp(float("inf")))
        self.assertIsNone(fa.parse_timestamp(float("nan")))
        for bad in (float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                fa.fmt_timestamp(bad)

    def test_deep_json_no_crash(self):
        raw = "[" * 5000 + "]" * 5000
        self.assertEqual(fa.parse_cues(raw, kind=None), [])
        self.assertEqual(fa.parse_cues(raw, kind="json"), [])
        p = self.write("deep.json", raw)
        self.assertEqual(fa.load_cues(p), [])

    def test_missing_file_raises(self):
        with self.assertRaises(OSError):
            fa.load_cues(os.path.join(self.tmp, "nope.srt"))


class TestFillers(unittest.TestCase):
    def test_is_filler(self):
        for w in ("اِ", "اه", "ام", "اوم", "اممم", "ااا", "خب", "یعنی", "چیزه", "ببین", "حالا", "مثلاً", "مثلا",
                  "اوکی", "آره", "دیگه", "um", "Uh", "basically", "ummm"):
            with self.subTest(w=w):
                self.assertTrue(fa.is_filler(w))
        for w in ("هم", "سلام", "Claude", "۴۲", "", "کلاد"):
            with self.subTest(w=w):
                self.assertFalse(fa.is_filler(w))

    def test_lexicon_sets(self):
        for w in ("اِ", "اه", "ام", "اوم", "خب", "یعنی", "چیزه", "ببین", "حالا", "مثلاً", "اوکی", "آره", "دیگه",
                  "به هر حال"):
            with self.subTest(w=w):
                self.assertIn(fa.fold(w), {fa.fold(x) for x in fa.FILLERS_FA})
        for w in fa.FILLERS_FA:
            self.assertNotIn("ي", w)
            self.assertNotIn("ك", w)

    def test_is_filler_only(self):
        self.assertTrue(fa.is_filler_only("خب، یعنی…"))
        self.assertTrue(fa.is_filler_only("اِ…"))
        self.assertTrue(fa.is_filler_only("به هر حال!"))
        self.assertTrue(fa.is_filler_only("Um? you know"))
        self.assertTrue(fa.is_filler_only("(uh)"))
        self.assertFalse(fa.is_filler_only("خب امروز می" + ZWNJ + "خوام"))
        self.assertFalse(fa.is_filler_only("۴۲"))
        self.assertFalse(fa.is_filler_only(""))

    def test_strip_cautious(self):
        self.assertEqual(fa.strip_fillers("خب، امروز می" + ZWNJ + "خوام یه چیزی بگم."),
                         "امروز می" + ZWNJ + "خوام یه چیزی بگم.")
        self.assertEqual(fa.strip_fillers("ببین، یعنی، این کار جواب می" + ZWNJ + "ده"),
                         "این کار جواب می" + ZWNJ + "ده")
        self.assertEqual(fa.strip_fillers("اممم من فکر می" + ZWNJ + "کنم"), "من فکر می" + ZWNJ + "کنم")
        self.assertEqual(fa.strip_fillers("به هر حال، بریم سراغ کار"), "بریم سراغ کار")
        self.assertEqual(fa.strip_fillers("so, um, I think"), "I think")

    def test_strip_keeps_meaningful_words(self):
        # «دیگه» = «anymore» here, «هم» = «also»: not standalone, so they stay
        self.assertEqual(fa.strip_fillers("این دیگه جواب نمی" + ZWNJ + "ده"), "این دیگه جواب نمی" + ZWNJ + "ده")
        self.assertEqual(fa.strip_fillers("این هم خوبه"), "این هم خوبه")
        self.assertEqual(fa.strip_fillers("سلام، «دنیا»"), "سلام، «دنیا»")
        self.assertEqual(fa.strip_fillers("حالا بریم"), "حالا بریم")

    def test_strip_aggressive(self):
        self.assertEqual(fa.strip_fillers("این دیگه جواب نمی" + ZWNJ + "ده", aggressive=True),
                         "این جواب نمی" + ZWNJ + "ده")
        self.assertEqual(fa.strip_fillers("you know I mean it", aggressive=True), "it")
        self.assertEqual(fa.strip_fillers("این هم خوبه", aggressive=True), "این هم خوبه")

    def test_strip_empty(self):
        self.assertEqual(fa.strip_fillers(""), "")
        self.assertEqual(fa.strip_fillers("خب، یعنی…"), "")

    def test_stopwords(self):
        self.assertIn("که", fa.STOPWORDS_FA)
        self.assertIn("می" + ZWNJ + "شه", fa.STOPWORDS_FA)
        self.assertIn("the", fa.STOPWORDS_EN)
        for w in fa.STOPWORDS_FA:
            self.assertEqual(w, fa.normalize(w))


class TestCopies(unittest.TestCase):
    """هر کپی _fatext.py باید دقیقاً همان lib/fatext.py باشد (scripts/sync_lib.py)."""

    def test_sync_check_passes(self):
        r = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "scripts", "sync_lib.py"), "--check"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(r.returncode, 0, r.stdout.decode("utf-8", "replace"))

    def test_copies_identical(self):
        with open(LIB, "rb") as fh:
            src = fh.read()
        sync = _load(os.path.join(ROOT, "scripts", "sync_lib.py"), "sync_lib_under_test")
        names = sync.targets()
        for need in ("yt-script", "yt-package", "yt-edit", "yt-chapters", "yt-retention", "yt-viral",
                     "yt-reel", "yt-results", "yt-subtitle", "yt-seo"):
            self.assertIn(need, names)
        for name in names:
            with self.subTest(skill=name):
                with open(os.path.join(ROOT, "skills", name, "_fatext.py"), "rb") as fh:
                    self.assertEqual(fh.read(), src)

    def test_copy_importable_under_isolated_mode(self):
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import _fatext as f; "
                "print(f.parse_number('۱٫۲ هزار'))")
        r = subprocess.run([sys.executable, "-I", "-c", code, os.path.join(ROOT, "skills", "yt-edit")],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        self.assertEqual(r.stdout.decode().strip(), "1200.0")

    def test_check_detects_drift(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "lib"))
            os.makedirs(os.path.join(tmp, "scripts"))
            os.makedirs(os.path.join(tmp, "skills", "yt-edit"))
            shutil.copy(LIB, os.path.join(tmp, "lib", "fatext.py"))
            shutil.copy(os.path.join(ROOT, "scripts", "sync_lib.py"), os.path.join(tmp, "scripts", "sync_lib.py"))
            script = os.path.join(tmp, "scripts", "sync_lib.py")
            r = subprocess.run([sys.executable, "-I", script, "--check"], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 1)  # copies missing
            subprocess.run([sys.executable, "-I", script], stdout=subprocess.PIPE, check=True)
            self.assertTrue(os.path.exists(os.path.join(tmp, "skills", "yt-reel", "_fatext.py")))
            r = subprocess.run([sys.executable, "-I", script, "--check"], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 0)
            with open(os.path.join(tmp, "skills", "yt-edit", "_fatext.py"), "a") as fh:
                fh.write("# drift\n")
            r = subprocess.run([sys.executable, "-I", script, "--check"], stdout=subprocess.PIPE)
            self.assertEqual(r.returncode, 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
