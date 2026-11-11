# -*- coding: utf-8 -*-
"""آزمون‌های اسکیل yt-comment (فقط SKILL.md، ابزار پایتونی نداره).

اجرا از ریشه‌ی مخزن:  python3 -I -m unittest discover -s tests -t .
"""
import importlib.util
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL_DIR = os.path.join(ROOT, "skills", "yt-comment")
SKILL = os.path.join(SKILL_DIR, "SKILL.md")
FIX = os.path.join(ROOT, "tests", "fixtures", "yt-comment", "comments_fa.txt")


def _load_fatext():
    spec = importlib.util.spec_from_file_location("fatext_yt_comment", os.path.join(ROOT, "lib", "fatext.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fa = _load_fatext()


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return m.group(1) if m else None


class SkillMdTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = _read(SKILL)
        cls.fm = _frontmatter(cls.text)
        cls.body = cls.text[len(cls.fm) + 8:] if cls.fm else ""

    def test_frontmatter(self):
        self.assertIsNotNone(self.fm)
        self.assertIn("name: yt-comment", self.fm)
        desc = self.fm.split("description:", 1)[1]
        self.assertTrue(fa.is_persian(desc), "description must be Persian")
        # Persian trigger phrases + English ones in parentheses
        self.assertIn("«جواب کامنت‌ها رو بنویس»", desc)
        self.assertRegex(desc, r"\((?:[^()]*reply[^()]*)\)")

    def test_body_is_persian(self):
        self.assertGreater(fa.script_ratio(self.body), 0.8)

    def test_no_arabic_letters_or_bad_zwnj(self):
        for ch in "يكىة":
            self.assertNotIn(ch, self.text, ch)
        # normalize() also trims spaces, so compare word content line by line
        for line in self.text.splitlines():
            self.assertEqual(" ".join(line.split()), fa.normalize(line).strip(), line)
        # common missing-ZWNJ spellings
        for bad in (" می شه", " نمی شه", "ویدیو ها", "کامنت ها"):
            self.assertNotIn(bad, self.text)

    def test_four_piles_and_rules(self):
        for word in ("سؤال", "اصلاح", "تعریف", "تحریک", "voice.md", "templates/voice.md",
                     "keyword.py", "/yt-reel", "پین", "ارسال نشد", "اگه بلدی خودت بساز",
                     "مهندسیِ کار", "دسته‌های کوچیک", "چند ساعت اول", "قول"):
            self.assertIn(word, self.text, word)

    def test_spelling_variants_example(self):
        for v in ("ارتیفکت", "ارتیفکیت", "اردیفکت"):
            self.assertIn(v, self.text)

    def test_source_labels(self):
        for label in ("[تجربه‌ی DrMounesi", "[قانون رسمی", "[قاعده‌ی سرانگشتی]"):
            self.assertIn(label, self.text)

    def test_gate_last(self):
        self.assertIn("## دروازه", self.text)
        self.assertTrue(self.text.rstrip().endswith("**منتشرش کنیم یا تغییرش بدیم؟**"))

    def test_example_replies_under_30_words(self):
        block = re.search(r"```\n(.*?)```", self.body, re.S).group(1)
        replies, cur = [], None
        for line in block.splitlines():
            if line.startswith("جواب:"):
                cur = [line.split(":", 1)[1]]
                replies.append(cur)
            elif cur is not None and line.startswith(" "):
                cur.append(line)
            else:
                cur = None
        self.assertGreaterEqual(len(replies), 4)
        for r in replies:
            self.assertLess(fa.word_count(" ".join(r)), 30, r)

    def test_privacy(self):
        self.assertNotRegex(self.text, r"/Users/|@[\w.-]+\.\w+|sk-[A-Za-z0-9]")

    def test_prompt_only_folder(self):
        # no tool here, so no _fatext.py copy is needed
        py = [f for f in os.listdir(SKILL_DIR) if f.endswith(".py") and f != "_fatext.py"]
        self.assertEqual(py, [])


class FixtureTest(unittest.TestCase):
    def test_fixture_is_clean_persian(self):
        text = _read(FIX)
        self.assertEqual(text.strip(), fa.normalize(text).strip())
        lines = [l for l in text.splitlines() if l.strip()]
        self.assertGreaterEqual(len(lines), 10)
        for l in lines:
            self.assertEqual(len(l.split(" | ")), 3, l)

    def test_keyword_variants_fold_close(self):
        # the variants a real audience typed differ from the keyword even after fold();
        # this is why the skill points to /yt-reel keyword.py instead of exact matching.
        kw = fa.fold("آرتیفکت")
        self.assertEqual(fa.fold("ارتیفکت"), kw)
        self.assertNotEqual(fa.fold("اردیفکت"), kw)


if __name__ == "__main__":
    unittest.main()
