"""تست‌های SKILL.md مهارت yt-audit (مهارت فقط-دستوری، بدون ابزار پایتون)."""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL_DIR = os.path.join(ROOT, "skills", "yt-audit")
SKILL_MD = os.path.join(SKILL_DIR, "SKILL.md")

sys.path.insert(0, os.path.join(ROOT, "lib"))
import fatext as fa  # noqa: E402

ZWNJ = "‌"


def _read():
    with open(SKILL_MD, encoding="utf-8") as f:
        return f.read()


def _split():
    text = _read()
    m = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", text, re.S)
    if not m:
        raise AssertionError("frontmatter missing")
    return m.group(1), m.group(2)


def _description(front):
    m = re.search(r"^description:\s*>-?\s*\n((?:[ \t]+.*\n?)+)", front, re.M)
    if not m:
        raise AssertionError("description missing")
    return " ".join(line.strip() for line in m.group(1).splitlines())


class FrontmatterTest(unittest.TestCase):
    def test_name_is_ascii_slug(self):
        front, _ = _split()
        self.assertRegex(front, r"(?m)^name: yt-audit$")

    def test_description_is_persian_with_triggers(self):
        front, _ = _split()
        desc = _description(front)
        self.assertGreater(fa.script_ratio(desc), 0.6)
        for phrase in ("کانالم رو بررسی کن", "چرا کانالم رشد نمی‌کنه", "اول چی رو درست کنم"):
            self.assertIn(phrase, desc)
        m = re.search(r"\(([A-Za-z' ,]+)\)", desc)
        self.assertIsNotNone(m, "English triggers in parentheses")
        self.assertGreaterEqual(len([p for p in m.group(1).split(",") if p.strip()]), 2)
        self.assertLessEqual(len([p for p in m.group(1).split(",") if p.strip()]), 4)


class BodyTest(unittest.TestCase):
    def setUp(self):
        self.front, self.body = _split()

    def test_body_is_persian(self):
        self.assertGreater(fa.script_ratio(self.body), 0.6)

    def test_ends_with_gate(self):
        self.assertIn("## دروازه", self.body)
        last = [ln for ln in self.body.splitlines() if ln.strip()][-1]
        self.assertIn("منتشرش کنیم یا تغییرش بدیم؟", last)

    def test_reads_voice_file_and_template(self):
        self.assertIn("~/.claude/youtube/voice.md", self.body)
        self.assertIn("templates/voice.md", self.body)

    def test_uses_other_skill_outputs(self):
        for skill in ("/yt-retention", "/yt-package", "/yt-viral", "/yt-results"):
            self.assertIn(skill, self.body)

    def test_drmounesi_basics_checklist(self):
        for item in (
            "فصل‌بندی", "پلی‌لیست", "بعدش این را ببین", "بلوک انگلیسی",
            "«فارسی» (عمومی)", "فارسی (ایران)", "ساخته‌نشده برای کودکان", "Not made for kids",
            "خصوصی", "HD", "ساعت انتشار", "When your viewers are on YouTube",
            "زیرنویس", "SRT", "فالو در هزار",
        ):
            self.assertIn(item, self.body, item)

    def test_follows_per_1k_by_format_not_views(self):
        self.assertRegex(self.body, r"به تفکیک فرمت")
        self.assertIn("نه فقط بازدید", self.body)

    def test_one_fix(self):
        self.assertIn("یک اصلاح", self.body)
        self.assertIn("بیست", self.body)

    def test_rule_sources_are_labelled(self):
        for label in ("رسمی YouTube", "تجربه‌ی کانال DrMounesi", "قاعده‌ی سرانگشتی"):
            self.assertIn(label, self.body)

    def test_never_invent_numbers(self):
        self.assertIn("از خودت نساز", self.body)
        self.assertIn("نامعلوم", self.body)

    def test_commands_are_isolated_and_relative(self):
        cmds = re.findall(r"(?m)^python3 .*$", self.body)
        self.assertTrue(cmds)
        for c in cmds:
            self.assertTrue(c.startswith("python3 -I "), c)
            self.assertNotIn("/Users/", c)

    def test_referenced_sibling_tools_exist(self):
        for rel in re.findall(r"\.\./(yt-[a-z]+/[a-z_]+\.py)", self.body):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, "skills", rel)), rel)


class HygieneTest(unittest.TestCase):
    def setUp(self):
        self.text = _read()

    def test_persian_letters_not_arabic(self):
        for ch in ("ي", "ك", "ى"):
            self.assertNotIn(ch, self.text)

    def test_zwnj_on_common_affixes(self):
        self.assertIn(ZWNJ, self.text)
        self.assertEqual(re.findall(r"(?:^|\s)ن?می [؀-ۿ]", self.text), [])
        self.assertEqual(re.findall(r"[؀-ۿ] (?:ها|های|هایی|تر|ترین)(?=[\s.،؛:])", self.text), [])

    def test_privacy(self):
        self.assertNotRegex(self.text, r"/Users/|/home/")
        self.assertNotRegex(self.text, r"[\w.+-]+@[\w-]+\.[\w.]+")
        self.assertNotRegex(self.text, r"(?i)sk-[a-z0-9]{10,}|api[_-]?key\s*[:=]")
        self.assertNotIn("AgentTask", self.text)

    def test_prompt_only_folder(self):
        py = [f for f in os.listdir(SKILL_DIR) if f.endswith(".py") and f != "_fatext.py"]
        self.assertEqual(py, [])


if __name__ == "__main__":
    unittest.main()
