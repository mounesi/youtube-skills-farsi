"""Tests for skills/yt-shorts (prompt-only skill: checks SKILL.md)."""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL = os.path.join(ROOT, "skills", "yt-shorts")
sys.path.insert(0, os.path.join(ROOT, "lib"))
import fatext as fa  # noqa: E402


def _read():
    with open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8") as f:
        return f.read()


def _split(text):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        raise AssertionError("SKILL.md has no YAML frontmatter")
    return m.group(1), m.group(2)


def _description(front):
    m = re.search(r"^description:\s*>-?\n((?:[ \t]+.*\n?)+)", front + "\n", re.M)
    if not m:
        raise AssertionError("no folded description")
    return " ".join(line.strip() for line in m.group(1).splitlines())


class FrontmatterTest(unittest.TestCase):
    def setUp(self):
        self.front, self.body = _split(_read())

    def test_name(self):
        self.assertRegex(self.front, r"(?m)^name: yt-shorts$")

    def test_description_is_persian_with_english_triggers(self):
        d = _description(self.front)
        self.assertGreater(fa.script_ratio(d), 0.7)
        paren = re.findall(r"\(([^)]*)\)", d)
        self.assertTrue(paren, "English triggers in parentheses missing")
        triggers = [t.strip() for t in paren[-1].split(",") if t.strip()]
        self.assertTrue(2 <= len(triggers) <= 4, triggers)
        for t in triggers:
            self.assertFalse(fa.is_persian(t), t)
        # Persian phrases a creator would type
        for phrase in ("شورت دربیار", "کلیپ کنم", "هوک"):
            self.assertIn(phrase, d)


class BodyTest(unittest.TestCase):
    def setUp(self):
        self.text = _read()
        self.front, self.body = _split(self.text)

    def test_body_is_persian(self):
        prose = re.sub(r"```.*?```", "", self.body, flags=re.S)
        self.assertGreater(fa.script_ratio(prose), 0.85)

    def test_persian_letters_not_arabic(self):
        self.assertNotRegex(self.text, "[يكى]")  # ي ك ى

    def test_zwnj_on_mi_prefix(self):
        # «می شه» / «نمی کنه» written with a space instead of ZWNJ
        bad = re.findall(r"(?:^|[\s«(])(?:نمی|می) [؀-ۿ]", self.body)
        self.assertEqual(bad, [])

    def test_ends_with_gate(self):
        self.assertIn("## دروازه", self.body)
        last = [l for l in self.body.splitlines() if l.strip()][-1]
        self.assertIn("منتشرش کنیم یا تغییرش بدیم؟", last)

    def test_reads_voice_file(self):
        self.assertIn("~/.claude/youtube/voice.md", self.body)
        self.assertIn("templates/voice.md", self.body)

    def test_core_shorts_rules_present(self):
        b = fa.to_ascii_digits(self.body)
        for needle in (
            "20 تا 55 ثانیه",      # span length
            "خط اول تازه",          # new first line
            "فریم صفر",             # on-screen text for frame 0
            "با جمله‌ی گفتاری فرق",  # different from the spoken line
            "نقطه‌ی لوپ",           # loop point
            "1080×1920",            # vertical framing
            "3 دقیقه",              # Shorts <= 3 min
            "40 نویسه‌ی اول",        # title hook in first 40 chars
            "ویدیوی کامل",          # related video = full video
            "220 پیکسل",            # Instagram hidden top
            "y ≥ 250",              # text placement
            "2 ثانیه",              # text >= 2 s on screen
            "گرافیک فقط فارسی",     # Persian-only graphics
            "کلمه‌ی کامنت",          # comment-keyword ending
            "منبعی برای فرستادن",    # ... only with a resource
        ):
            self.assertIn(needle, b, needle)

    def test_rule_sources_are_labelled(self):
        for label in ("تجربه‌ی کانال DrMounesi", "قانون رسمی یوتیوب",
                      "قاعده‌ی سرانگشتی"):
            self.assertIn(label, self.body, label)

    def test_never_invent_numbers(self):
        self.assertIn("هیچ عدد، نتیجه یا منبعی از خودت نساز", self.body)

    def test_hookscore_reference_is_relative_and_optional(self):
        self.assertIn("python3 -I ../yt-script/hookscore.py", self.body)
        # must describe what to do when the sibling skill is absent
        self.assertIn("اگه این فایل نیست", self.body)

    def test_prompt_only_folder_is_portable(self):
        tools = [f for f in os.listdir(SKILL)
                 if f.endswith(".py") and f != "_fatext.py"
                 and not f.startswith("test_")]
        self.assertEqual(tools, [], "yt-shorts is prompt-only")

    def test_privacy(self):
        self.assertNotRegex(self.text, r"/Users/|/home/")
        self.assertNotRegex(self.text, r"[\w.+-]+@[\w-]+\.[\w.]+")
        self.assertNotRegex(self.text, r"(?i)api[_ -]?key|sk-[A-Za-z0-9]{8}")
        self.assertNotIn("Peyman", self.text)
        self.assertNotIn("AgentTask", self.text)


if __name__ == "__main__":
    unittest.main()
