"""Regression tests for skills/yt-package/title.py (upstream English behaviour)."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOL = os.environ.get("TITLE_PY_UNDER_TEST", os.path.join(ROOT, "skills", "yt-package", "title.py"))


def load():
    spec = importlib.util.spec_from_file_location("yt_package_title", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(*args):
    return subprocess.run([sys.executable, "-I", TOOL, *args], capture_output=True, text=True, timeout=30)


def kinds(result):
    return [k for k, _ in result["issues"]]


class TitleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = load()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data):
        path = os.path.join(self.tmp.name, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    # bug 1: four thumbnail words must be flagged
    def test_four_thumb_words_flagged(self):
        r = self.t.check("I tried 30 days of cold showers", "NEVER AGAIN EVER MORE")
        self.assertIn("thumb-length", kinds(r))
        self.assertNotIn("thumb-length", kinds(self.t.check("I tried 30 days of cold showers", "NEVER AGAIN EVER")))

    # bug 2: a flag without a value must not crash
    def test_missing_flag_value_no_traceback(self):
        f = self.write("t.txt", b"One 2\n")
        for args in (["--title"], [f, "--thumb"], ["--title", "--json"]):
            p = run(*args)
            self.assertNotEqual(p.returncode, 0, args)
            self.assertNotIn("Traceback", p.stderr, args)

    # bug 3: file mode works when the file is not the first argument
    def test_file_after_thumb_flag(self):
        f = self.write("t.txt", b"One 2\nTwo 3 more words\n")
        p = run("--thumb", "AI RAN IT", f, "--json")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        rows = json.loads(p.stdout)
        self.assertEqual(sorted(r["title"] for r in rows), ["One 2", "Two 3 more words"])

    # bug 4: a written date counts as concrete; message no longer claims to detect names
    def test_written_date_counts(self):
        r = self.t.check("What Changed In January For Creators")
        self.assertNotIn("no-number", kinds(r))
        r = self.t.check("Elon Musk Fired Twitter's Board")
        msg = dict(r["issues"]).get("no-number", "")
        # Changed on purpose (Farsi pack): messages are Persian now. Title Case English names are
        # still not detected, and the message still says so («... تشخیص نمی‌دهم، دستی چک کن»).
        self.assertIn("Title Case", msg)
        self.assertIn("دستی چک کن", msg)
        self.assertIn("no-number", kinds(self.t.check("You may like this one")))

    # bug 5: UTF-8 BOM is stripped from the first title
    def test_bom_stripped(self):
        f = self.write("bom.txt", b"\xef\xbb\xbfHow I made 5 dollars\r\nSecond 7 title\r\n")
        p = run(f, "--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        rows = {r["title"]: r for r in json.loads(p.stdout)}
        self.assertIn("How I made 5 dollars", rows)
        self.assertEqual(rows["How I made 5 dollars"]["chars"], 20)

    # bug 6: a whole word ending exactly at character 40 stays in the mobile preview
    def test_mobile_preview_keeps_full_word(self):
        r = self.t.check("abcdefghi abcdefghi abcdefghi abcdefghij more 5")
        msg = dict(r["issues"])["mobile"]
        # Changed on purpose (Farsi pack): the preview is quoted with Persian guillemets and an
        # ellipsis character («...…») instead of "...". The off-by-one fix itself is unchanged.
        self.assertIn('«abcdefghi abcdefghi abcdefghi abcdefghij…»', msg)
        r = self.t.check("abcdefghi abcdefghi abcdefghi abcdefghijkl more 5")
        self.assertIn('«abcdefghi abcdefghi abcdefghi…»', dict(r["issues"])["mobile"])

    # bug 7: hyphenated vague words are flagged, without losing hyphen-split matches
    def test_hyphenated_vague(self):
        r = self.t.check("This mind-blowing trick saves 3 hours")
        self.assertIn("mindblowing", dict(r["issues"]).get("vague", ""))
        r = self.t.check("The best-ever 3 step plan")
        self.assertIn("best", dict(r["issues"]).get("vague", ""))

    # bug 8: a directory argument gives usage, not IsADirectoryError
    def test_directory_argument(self):
        p = run(self.tmp.name)
        self.assertEqual(p.returncode, 1)
        self.assertNotIn("Traceback", p.stderr)

    def test_missing_file_reports_not_found(self):
        p = run(os.path.join(self.tmp.name, "nope.txt"))
        self.assertEqual(p.returncode, 1)
        # Changed on purpose (Farsi pack): the error message is Persian now.
        self.assertIn("فایل پیدا نشد", p.stderr)

    def test_basic_cli_unchanged(self):
        p = run("--title", "I tried 30 days of cold showers", "--thumb", "NEVER AGAIN", "--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)[0]["title"], "I tried 30 days of cold showers")


if __name__ == "__main__":
    unittest.main()
