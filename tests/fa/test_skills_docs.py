# -*- coding: utf-8 -*-
"""آزمون مستندها و حریم خصوصی کل مخزن.

    python3 -I -m unittest discover -s tests -t . -p test_skills_docs.py

- هر skills/*/SKILL.md: name برابر نام پوشه، توضیح فارسی، جمله‌ی دروازه، فایل‌ها و فرمان‌هایی که نام می‌برد وجود دارند.
- هیچ سند فارسی‌ای «ي/ك» عربی ندارد (جز وقتی خود حرف به‌عنوان نمونه آمده یا داخل «» نقل شده).
- اسکن حریم خصوصی روی همه‌ی فایل‌های متنی مخزن (مخزن عمومی است).
- README هر چهارده مهارت را نام می‌برد؛ plugin.json و marketplace.json معتبرند.
"""
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILLS = os.path.join(ROOT, "skills")
GATE = "منتشرش کنیم یا تغییرش بدیم؟"
EXPECTED = ("yt-audit", "yt-chapters", "yt-comment", "yt-edit", "yt-package", "yt-plan", "yt-reel",
            "yt-results", "yt-retention", "yt-script", "yt-seo", "yt-shorts", "yt-subtitle", "yt-viral")
ARABIC = "يك"
FA_LETTERS = re.compile("[ء-غف-يپچژکگیآ]")
LATIN_LETTERS = re.compile("[A-Za-z]")
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "venv"}
TEXT_EXT = {".md", ".py", ".json", ".txt", ".srt", ".vtt", ".csv", ".yml", ".yaml", ".toml", ".cfg", ".sh", ""}


def read(path):
    with open(path, encoding="utf-8-sig") as fh:
        return fh.read()


def skill_dirs():
    return sorted(n for n in os.listdir(SKILLS) if os.path.isfile(os.path.join(SKILLS, n, "SKILL.md")))


def frontmatter(text):
    m = re.match(r"---\n(.*?)\n---\n", text.replace("\r\n", "\n"), re.S)
    if not m:
        return None
    fm, key, out = m.group(1), None, {}
    for line in fm.split("\n"):
        km = re.match(r"([A-Za-z_-]+):\s*(.*)$", line)
        if km and not line.startswith(" "):
            key = km.group(1)
            val = km.group(2).strip()
            out[key] = "" if val in (">-", ">", "|", "|-") else val.strip("\"'")
        elif key:
            out[key] = (out[key] + " " + line.strip()).strip()
    return out


def text_files():
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            if fn == ".DS_Store":
                continue
            p = os.path.join(dp, fn)
            if os.path.splitext(fn)[1].lower() not in TEXT_EXT:
                continue
            try:
                yield p, read(p)
            except (UnicodeDecodeError, OSError):
                continue


def bad_arabic(text):
    """کلمه‌هایی که «ي/ك» عربی دارند و نقل‌قول یا نمونه‌ی تک‌حرفی نیستند."""
    # quoted examples «…» and `code` are allowed: they show the wrong form on purpose
    stripped = re.sub(r"«[^»\n]*»", " ", text)
    stripped = re.sub(r"`[^`\n]*`", " ", stripped)
    bad = []
    for tok in re.split(r"[\s/↔،,;:()\[\]|]+", stripped):
        if any(c in tok for c in ARABIC):
            letters = FA_LETTERS.findall(tok)
            if len(letters) > 1:  # a lone letter like «ي» named as an example is fine
                bad.append(tok)
    return bad


class SkillDocsTest(unittest.TestCase):

    def test_all_fourteen_skills_present(self):
        self.assertEqual(tuple(skill_dirs()), EXPECTED)

    def test_frontmatter_name_and_farsi_description(self):
        for name in skill_dirs():
            with self.subTest(skill=name):
                fm = frontmatter(read(os.path.join(SKILLS, name, "SKILL.md")))
                self.assertIsNotNone(fm, "frontmatter missing")
                self.assertEqual(fm.get("name"), name)
                desc = fm.get("description", "")
                fa, la = len(FA_LETTERS.findall(desc)), len(LATIN_LETTERS.findall(desc))
                self.assertGreater(fa, 100, "description too short / not Persian")
                self.assertGreater(fa, 2 * la, "description is not mostly Persian (%d fa / %d latin)" % (fa, la))

    def test_body_mostly_persian_and_has_gate(self):
        for name in skill_dirs():
            with self.subTest(skill=name):
                text = read(os.path.join(SKILLS, name, "SKILL.md"))
                body = re.sub(r"```.*?```", " ", text, flags=re.S)
                self.assertGreater(len(FA_LETTERS.findall(body)), len(LATIN_LETTERS.findall(body)))
                self.assertIn(GATE, text)
                self.assertIn("دروازه", text)

    def _resolve(self, skill, ref):
        ref = ref.rstrip(".,;:)»،")
        if ref.startswith(("skills/", "scripts/", "templates/", "lib/", "tests/")):
            return [os.path.join(ROOT, ref)]
        return [os.path.join(SKILLS, skill, ref), os.path.join(ROOT, ref)]

    def test_referenced_files_and_commands_exist(self):
        for name in skill_dirs():
            text = read(os.path.join(SKILLS, name, "SKILL.md"))
            refs = set(re.findall(r"python3 -I ([^\s`'\"]+\.py)", text))
            refs |= set(re.findall(r"\]\(([^)#\s]+)\)", text))
            refs |= set(re.findall(r"(?:\.\./yt-[a-z]+/|templates/)[A-Za-z0-9_.-]+", text))
            for ref in refs:
                if ref.startswith(("http://", "https://", "mailto:", "~")):
                    continue
                with self.subTest(skill=name, ref=ref):
                    self.assertTrue(any(os.path.exists(p) for p in self._resolve(name, ref)),
                                    "%s names %s which does not exist" % (name, ref))

    def test_readme_commands_exist(self):
        text = read(os.path.join(ROOT, "README.md"))
        refs = set(re.findall(r"python3 -I ([^\s`'\"]+\.py)", text))
        refs |= set(r for r in re.findall(r"\]\(([^)#\s]+)\)", text) if not r.startswith("http"))
        self.assertTrue(refs)
        for ref in refs:
            with self.subTest(ref=ref):
                self.assertTrue(os.path.exists(os.path.join(ROOT, ref)), ref)

    def test_readme_lists_all_skills(self):
        text = read(os.path.join(ROOT, "README.md"))
        for name in EXPECTED:
            with self.subTest(skill=name):
                self.assertIn("/" + name, text)

    def test_no_arabic_letters_in_farsi_docs(self):
        for p, text in text_files():
            if not p.endswith(".md") or os.sep + "fixtures" + os.sep in p:
                continue
            with self.subTest(path=os.path.relpath(p, ROOT)):
                self.assertEqual(bad_arabic(text), [])

    def test_bad_arabic_helper(self):
        self.assertEqual(bad_arabic("حرف «ي» و «ويديو» و ی/ي"), [])
        self.assertEqual(bad_arabic("مي‌خوام"), ["مي‌خوام"])


class PluginJsonTest(unittest.TestCase):

    def test_plugin_and_marketplace(self):
        base = os.path.join(ROOT, ".claude-plugin")
        plugin = json.loads(read(os.path.join(base, "plugin.json")))
        market = json.loads(read(os.path.join(base, "marketplace.json")))
        url = "https://github.com/mounesi/youtube-skills-farsi"
        self.assertEqual(plugin["repository"], url)
        self.assertEqual(plugin["homepage"], url)
        self.assertEqual(plugin["license"], "MIT")
        names = [p["name"] for p in market["plugins"]]
        self.assertIn(plugin["name"], names)
        for p in market["plugins"]:
            self.assertEqual(p["homepage"], url)
        self.assertIn("mounesi/youtube-skills-farsi", read(os.path.join(ROOT, "README.md")))


# Forbidden strings are assembled at runtime so this file does not trip its own scan.
_HOME = "/" + "Users" + "/"
PRIVATE_PATTERNS = [
    ("local path", re.compile(re.escape(_HOME) + "|/home/[a-z]")),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}")),
    ("gmail", re.compile("@" + "gmail", re.I)),
    ("private name", re.compile("Pey" + "man", re.I)),
    ("task-tracker name", re.compile("agent" + r"[-_ ]?" + "task", re.I)),
    ("ticket id", re.compile(r"\b(?:AI|CONT|MOBI|QA)-P?\d{2,}\b")),
    ("api key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}|\bAKIA[0-9A-Z]{16}\b|\bAIza[0-9A-Za-z_-]{30,}"
                           r"|\bgh[pousr]_[A-Za-z0-9]{30,}|\bxox[abprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY")),
]


def privacy_hits(path, text):
    hits = []
    in_tests = (os.sep + "tests" + os.sep) in path and path.endswith(".py")
    for n, line in enumerate(text.split("\n"), 1):
        # tests may name a forbidden string only to assert it is absent
        if in_tests and re.search(r"assertNot|NotRegex|NotIn", line):
            continue
        for label, rx in PRIVATE_PATTERNS:
            if rx.search(line):
                hits.append("%s:%d %s" % (os.path.relpath(path, ROOT), n, label))
    return hits


class PrivacyTest(unittest.TestCase):

    def test_repo_privacy_scan(self):
        hits, seen = [], 0
        for p, text in text_files():
            seen += 1
            hits += privacy_hits(p, text)
        self.assertGreater(seen, 50)
        self.assertEqual(hits, [])

    def test_scanner_catches(self):
        fake = os.path.join(ROOT, "README.md")
        self.assertTrue(privacy_hits(fake, "see " + _HOME + "x/a.py"))
        self.assertTrue(privacy_hits(fake, "mail me a.b" + "@" + "example.com"))
        self.assertTrue(privacy_hits(fake, "key sk-" + "a" * 24))
        self.assertTrue(privacy_hits(fake, "Agent" + "Task board"))
        self.assertFalse(privacy_hits(fake, "یوتیوب @DrMounesi و t.me/DrMounesi"))


if __name__ == "__main__":
    unittest.main()
