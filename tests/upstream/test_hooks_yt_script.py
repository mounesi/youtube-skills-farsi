"""Regression tests for skills/yt-script/hooks.json (formula match patterns).

Every formula's own worked example must classify as that formula, and it must
win outright (strictly more pattern hits than any other formula), so the result
does not depend on file order or on how hookscore.classify() breaks ties.
"""
import importlib.util
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL = os.path.join(ROOT, "skills", "yt-script")
HOOKS = os.path.join(SKILL, "hooks.json")


def load_hookscore():
    spec = importlib.util.spec_from_file_location("yt_script_hookscore", os.path.join(SKILL, "hookscore.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def hits(formula, text):
    return sum(1 for p in formula["match"] if re.search(p, text, re.I))


class HooksJsonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(HOOKS, encoding="utf-8") as fh:
            cls.data = json.load(fh)
        cls.formulas = cls.data["hooks"]

    def test_21_formulas_with_valid_patterns(self):
        self.assertEqual(len(self.formulas), 21)
        for f in self.formulas:
            for key in ("id", "name", "shape", "example", "fails_when", "match"):
                self.assertIn(key, f, f.get("id"))
            self.assertTrue(f["match"], f["id"])
            for p in f["match"]:
                re.compile(p)

    def test_each_example_wins_outright(self):
        for f in self.formulas:
            with self.subTest(formula=f["id"]):
                own = hits(f, f["example"])
                self.assertGreater(own, 0, "own example matches none of its patterns")
                for g in self.formulas:
                    if g is f:
                        continue
                    self.assertLess(hits(g, f["example"]), own,
                                    "%s ties or beats it" % g["id"])

    def test_hookscore_classifies_each_example_as_its_formula(self):
        hs = load_hookscore()
        for f in self.formulas:
            with self.subTest(formula=f["id"]):
                name, n = hs.classify(f["example"])
                self.assertEqual(name, f["name"])
                self.assertGreater(n, 0)

    def test_previously_misclassified_examples(self):
        hs = load_hookscore()
        by_id = {f["id"]: f for f in self.formulas}
        for fid in ("the-mistake", "the-clock", "the-list", "the-warning", "the-receipt",
                    "the-comparison", "the-origin", "the-direct-address"):
            with self.subTest(formula=fid):
                self.assertEqual(hs.classify(by_id[fid]["example"])[0], by_id[fid]["name"])

    def test_spelled_out_numbers(self):
        hs = load_hookscore()
        self.assertEqual(hs.classify("Seven things I would change about my thumbnails.")[0], "The List")
        self.assertEqual(hs.classify("In the next six minutes you will have a script.")[0], "The Clock")
        self.assertEqual(hs.classify("Five tools every new creator should know.")[0], "The List")

    def test_do_not_is_not_a_question(self):
        hs = load_hookscore()
        self.assertNotEqual(hs.classify("Do not upload another video until you check this.")[0], "The Question")
        self.assertEqual(hs.classify("Do you really need a camera to start a channel?")[0], "The Question")
        self.assertEqual(hs.classify("Does posting daily actually grow a channel?")[0], "The Question")


if __name__ == "__main__":
    unittest.main()
