# -*- coding: utf-8 -*-
"""آزمون‌های مهارت yt-plan (فقط SKILL.md، بدون ابزار).

بررسی می‌کند که SKILL.md قالب درست دارد، فارسیِ تمیز است (بدون ي/ك عربی و با نیم‌فاصله‌ی درست)،
قاعده‌های DrMounesi را دارد، اطلاعات خصوصی ندارد و با دروازه تمام می‌شود.

اجرا از ریشه‌ی مخزن:  python3 -I -m unittest discover -s tests -t .
"""
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL_DIR = os.path.join(ROOT, "skills", "yt-plan")
SKILL = os.path.join(SKILL_DIR, "SKILL.md")
FIX = os.path.join(ROOT, "tests", "fixtures", "yt-plan")
ZWNJ = "‌"


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _split_frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        raise AssertionError("SKILL.md has no YAML frontmatter")
    return m.group(1), m.group(2)


def _description(front):
    # folded scalar: "description: >-" then indented lines
    m = re.search(r"^description:\s*>-?\s*\n((?:[ \t]+.*\n?)+)", front, re.M)
    if m:
        return " ".join(line.strip() for line in m.group(1).splitlines())
    m = re.search(r"^description:\s*(.+)$", front, re.M)
    return m.group(1).strip() if m else ""


def _fa_ratio(text):
    fa = len(re.findall(r"[؀-ۿ]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    return fa / float(fa + latin) if fa + latin else 0.0


def _persian_quality_problems(text):
    """Common Persian typing mistakes; returns a list of problems."""
    probs = []
    if re.search("[يكى]", text):
        probs.append("Arabic ي/ك/ى")
    # «می» / «نمی» prefix glued with a plain space before a verb-looking word
    for m in re.finditer(r"(?<![؀-ۿ‌])(ن?می) (?=[؀-ۿ]{2,})", text):
        probs.append("space instead of ZWNJ after %r at %d" % (m.group(1), m.start()))
    # plural ها / ترین written with a space
    for m in re.finditer(r"[؀-ۿ]{2,} (ها|های|ترین)(?![؀-ۿ])", text):
        probs.append("space before %r at %d" % (m.group(1), m.start()))
    if re.search(ZWNJ + "{2,}", text):
        probs.append("double ZWNJ")
    if re.search("[​‎‏‪-‮﻿]", text):
        probs.append("bidi control / zero-width space / BOM")
    return probs


class TestSkillFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = _read(SKILL)
        cls.front, cls.body = _split_frontmatter(cls.text)
        cls.req = json.loads(_read(os.path.join(FIX, "required.json")))

    def test_frontmatter_name(self):
        self.assertRegex(self.front, r"(?m)^name:\s*yt-plan\s*$")

    def test_description_is_farsi_with_triggers(self):
        desc = _description(self.front)
        self.assertTrue(desc, "empty description")
        self.assertGreater(_fa_ratio(desc), 0.8, "description must be mostly Farsi")
        for p in self.req["description_fa_phrases"]:
            self.assertIn(p, desc)
        for p in self.req["description_en_phrases"]:
            self.assertIn(p, desc)
        # English triggers sit in parentheses
        self.assertRegex(desc, r"\([^)]*plan my week[^)]*\)")
        # one paragraph: no blank line inside the folded block
        self.assertNotIn("\n\n", self.front)

    def test_body_is_farsi(self):
        self.assertGreater(_fa_ratio(self.body), 0.75)

    def test_required_rules_present(self):
        missing = [p for p in self.req["body_must_contain"] if p not in self.body]
        self.assertEqual(missing, [], "missing in SKILL.md body: %r" % missing)

    def test_week_table_columns(self):
        header = [l for l in self.body.splitlines() if l.startswith("| روز |")]
        self.assertTrue(header, "no week table header")
        cols = [c.strip() for c in header[0].strip("|").split("|")]
        for c in self.req["table_columns"]:
            self.assertIn(c, cols)

    def test_ends_with_gate(self):
        self.assertIn(self.req["gate_heading"], self.body)
        after_gate = self.body.split(self.req["gate_heading"], 1)[1]
        self.assertIn(self.req["gate_question"], after_gate)
        last = [l for l in self.body.splitlines() if l.strip()][-1]
        self.assertIn(self.req["gate_question"], last)
        # gate is the last section
        self.assertNotRegex(after_gate, r"(?m)^## ")

    def test_persian_typing(self):
        self.assertEqual(_persian_quality_problems(self.text), [])

    def test_no_private_data(self):
        t = self.text
        self.assertNotRegex(t, r"/Users/|/home/|[A-Za-z]:\\\\")
        self.assertNotRegex(t, r"[\w.+-]+@[\w-]+\.[\w.]+")
        self.assertNotRegex(t, r"(?i)(api[_-]?key|sk-[A-Za-z0-9]{8,}|agenttask)")
        self.assertNotRegex(t, r"(?i)peyman")

    def test_publish_time_has_source_and_check(self):
        # the Tehran window is labelled as experience and paired with "check your own analytics"
        i = self.body.index("۱۰ تا ۱۴ به وقت تهران")
        window = self.body[i:i + 600]
        self.assertIn("تجربه‌ی کانال DrMounesi", window)
        self.assertIn("When your viewers are on YouTube", window)

    def test_one_keyword_reel_and_dm_ready(self):
        self.assertIn("هر هفته فقط یک ریلز کلمه‌ی کامنتی", self.body)
        self.assertRegex(self.body, r"نوشته و امتحان شده")

    def test_prompt_only_no_tools(self):
        # yt-plan is prompt-only: no python tool, so no _fatext.py copy is needed
        py = [f for f in os.listdir(SKILL_DIR) if f.endswith(".py")]
        self.assertEqual(py, [])
        self.assertNotIn("python3", self.body)

    def test_referenced_skills_exist(self):
        for name in set(re.findall(r"`/(yt-[a-z]+)`", self.body)):
            self.assertTrue(os.path.isdir(os.path.join(ROOT, "skills", name)), name)

    def test_voice_template_exists(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "templates", "voice.md")))


class TestExampleWeek(unittest.TestCase):
    """A sample of the hand-back table: the shape SKILL.md asks for."""

    @classmethod
    def setUpClass(cls):
        cls.text = _read(os.path.join(FIX, "example_week.md"))
        cls.rows = [l for l in cls.text.splitlines() if l.startswith("|") and "---" not in l]

    def test_five_posts_matching_mix(self):
        header, data = self.rows[0], self.rows[1:]
        cols = [c.strip() for c in header.strip("|").split("|")]
        role_i = cols.index("نقش")
        roles = [[c.strip() for c in r.strip("|").split("|")][role_i] for r in data]
        self.assertEqual(len(roles), 5)
        self.assertEqual(roles.count("اصلی"), 1)
        self.assertEqual(roles.count("کم‌هزینه"), 1)
        self.assertEqual(roles.count("کلمه‌ی کامنتی"), 1)
        self.assertIn("خبری/ری‌اکشن", roles)
        self.assertIn("آموزش ابزار", roles)

    def test_no_invented_hours(self):
        header, data = self.rows[0], self.rows[1:]
        cols = [c.strip() for c in header.strip("|").split("|")]
        i = cols.index("ساعت لازم")
        for r in data:
            self.assertEqual([c.strip() for c in r.strip("|").split("|")][i], "؟")

    def test_example_persian_and_gate(self):
        self.assertEqual(_persian_quality_problems(self.text), [])
        self.assertTrue(self.text.strip().endswith("منتشرش کنیم یا تغییرش بدیم؟"))


if __name__ == "__main__":
    unittest.main()
