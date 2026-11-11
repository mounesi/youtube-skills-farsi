"""Regression tests for skills/yt-script/hookscore.py (upstream English behaviour)."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOL = os.path.join(ROOT, "skills", "yt-script", "hookscore.py")


def _load():
    spec = importlib.util.spec_from_file_location("hookscore_yt_script", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


h = _load()


def run(*args):
    return subprocess.run([sys.executable, "-I", TOOL] + list(args),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, encoding="utf-8")


class BomAndIndentTest(unittest.TestCase):
    def test_bom_crlf_indent_file_classifies_like_clean_file(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bom.txt")
            with open(bad, "wb") as f:
                f.write(b"\xef\xbb\xbfWhy do 90% of channels die?\r\n"
                        b"   If you post twice a week, watch this.\r\n")
            r = run("--json", bad)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = {x["hook"]: x for x in json.loads(r.stdout)}
        self.assertIn("Why do 90% of channels die?", out)  # no BOM leak
        self.assertIn("If you post twice a week, watch this.", out)
        self.assertEqual(out["Why do 90% of channels die?"]["formula"], "The Question")
        self.assertEqual(out["If you post twice a week, watch this."]["formula"],
                         "The Direct Address")

    def test_hook_flag_value_is_stripped(self):
        r = run("--json", "--hook", "  Why do 90% of channels die?")
        self.assertEqual(r.returncode, 0, r.stderr)
        res = json.loads(r.stdout)[0]
        self.assertEqual(res["hook"], "Why do 90% of channels die?")
        self.assertEqual(res["formula"], "The Question")


class WordsPunctuationTest(unittest.TestCase):
    def test_full_stop_does_not_change_specificity(self):
        self.assertEqual(h.specificity("This is amazing."), h.specificity("This is amazing"))
        self.assertEqual(h.specificity("This is amazing."), 18)
        self.assertEqual(h.specificity("Watch this video."), h.specificity("Watch this video"))

    def test_lone_dot_is_not_a_word(self):
        self.assertEqual(h.words("wait . what"), ["wait", "what"])
        self.assertEqual(h.words("wait... what"), ["wait", "what"])

    def test_decimals_stay_one_token(self):
        self.assertEqual(h.words("3.5x $2.50 10.5k"), ["3.5x", "$2.50", "10.5k"])


class CliErrorsTest(unittest.TestCase):
    def test_hook_without_value(self):
        for args in (["--hook"], ["--hook", "--json"], ["--hook", "   "]):
            r = run(*args)
            self.assertEqual(r.returncode, 2, args)
            self.assertNotIn("Traceback", r.stderr)
            self.assertIn("--hook", r.stderr)

    def test_missing_file_is_an_error(self):
        r = run("/nonexistent/hooks-xyz.txt")
        self.assertNotEqual(r.returncode, 0)
        # messages are Farsi in the Persian pack («فایل پیدا نشد» = no such file)
        self.assertIn("پیدا نشد", r.stderr)
        self.assertEqual(r.stdout, "")

    def test_no_args_still_exit_1(self):
        self.assertEqual(run().returncode, 1)

    def test_help_exit_0(self):
        r = run("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("hookscore.py", r.stdout)

    def test_valid_file_still_works(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "h.txt")
            with open(p, "w", encoding="utf-8") as f:
                f.write("Why do 90% of channels die?\n\nYou are losing $500 a month.\n")
            r = run(p)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("برنده:", r.stdout)  # Farsi output: «برنده» = winner


class ProperNounTest(unittest.TestCase):
    def test_pronoun_i_is_not_a_name(self):
        self.assertEqual(h.specificity("Then I quit and I lost it all"),
                         h.specificity("Then we quit and we lost it all"))
        self.assertEqual(h.specificity("Then I'm out and I've lost"),
                         h.specificity("Then we're out and we've lost"))

    def test_sentence_starts_are_not_names(self):
        self.assertEqual(h.specificity("Stop. Do this. Now. Today."), 29)

    def test_real_names_still_count(self):
        self.assertEqual(h.specificity("He moved to Tokyo. Then Apple called."), 46)


if __name__ == "__main__":
    unittest.main()
