"""Regression tests for skills/yt-chapters/chapters.py (upstream English behaviour).

Run from the repo root:  python3 -I -m unittest discover -s tests -t .
Set CHAPTERS_PY to point the tests at another copy of the tool.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOL = os.environ.get("CHAPTERS_PY") or os.path.join(ROOT, "skills", "yt-chapters", "chapters.py")


def srt_ts(t):
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return "%02d:%02d:%02d,%03d" % (h, m, int(s), round((s - int(s)) * 1000))


def write_srt(path, cues):
    with open(path, "w", encoding="utf-8") as f:
        for n, (a, b, text) in enumerate(cues, 1):
            f.write("%d\n%s --> %s\n%s\n\n" % (n, srt_ts(a), srt_ts(b), text))


def three_sections():
    cues = []
    for i in range(8):
        cues.append((i * 5, i * 5 + 4, "alpha apple orchard"))
    for i in range(8):
        cues.append((50 + i * 5, 50 + i * 5 + 4, "bravo banana market"))
    for i in range(8):
        cues.append((100 + i * 5, 100 + i * 5 + 4, "charlie cherry harbor"))
    return cues


class ChaptersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, *args):
        return subprocess.run([sys.executable, "-I", TOOL] + list(args),
                              capture_output=True, text=True, timeout=60)

    def chapters_json(self, *args):
        r = self.run_tool(*(list(args) + ["--json"]))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    # Bug 1: duration from the last cue's end instead of the max end.
    def test_duration_uses_latest_end_with_overlapping_cues(self):
        cues = [(i * 5, i * 5 + 4, "camera words lens") for i in range(20)]
        cues.append((100, 130, "music outro section playing"))
        cues.append((105, 106, "bye"))
        p = os.path.join(self.dir, "overlap2.srt")
        write_srt(p, cues)
        d = self.chapters_json(p)
        chs = d["chapters"]
        last = chs[-1]
        self.assertAlmostEqual(last["start"] + last["seconds"], 130.0, places=2)
        self.assertAlmostEqual(sum(c["seconds"] for c in chs), 130.0, places=2)
        titles = " ".join(c["draft_title"] for c in chs)
        self.assertTrue(any(w in titles for w in ("Music", "Outro", "Section", "Playing")), titles)

    def test_unsorted_cues_give_same_result_as_sorted(self):
        cues = three_sections()
        a = os.path.join(self.dir, "sorted.srt")
        b = os.path.join(self.dir, "unsorted.srt")
        write_srt(a, cues)
        write_srt(b, list(reversed(cues)))
        da, db = self.chapters_json(a, "--target", "3"), self.chapters_json(b, "--target", "3")
        self.assertEqual([c["start"] for c in da["chapters"]], [0.0, 50.0, 100.0])
        self.assertEqual([c["start"] for c in db["chapters"]], [0.0, 50.0, 100.0])
        self.assertAlmostEqual(sum(c["seconds"] for c in db["chapters"]), 139.0, places=2)
        self.assertTrue(db["valid"])

    # Bug 2: a cue that crosses a chapter boundary is in no chapter's text.
    def test_cue_straddling_boundary_counts_toward_a_title(self):
        segs = [{"start": i * 5, "end": i * 5 + 4, "text": "alpha apple orchard"} for i in range(6)]
        segs.append({"start": 30, "end": 70, "text": " ".join(["zebra"] * 20)})  # crosses 60
        segs += [{"start": i * 5, "end": i * 5 + 4, "text": "alpha apple orchard"} for i in range(6, 11)]
        segs += [{"start": 60 + i * 5, "end": 64 + i * 5, "text": "bravo banana market"} for i in range(8)]
        segs += [{"start": 110 + i * 5, "end": 114 + i * 5, "text": "charlie cherry harbor"} for i in range(8)]
        p = os.path.join(self.dir, "straddle.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"segments": segs}, f)
        chs = self.chapters_json(p, "--target", "3")["chapters"]
        self.assertEqual([c["start"] for c in chs], [0.0, 60.0, 110.0])
        self.assertIn("Zebra", chs[0]["draft_title"])

    # Bug 3: --target parsing.
    def test_target_without_value_is_clean_usage_error(self):
        p = os.path.join(self.dir, "t.srt")
        write_srt(p, three_sections())
        r = self.run_tool(p, "--target")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_target_non_integer_is_clean_usage_error(self):
        p = os.path.join(self.dir, "t.srt")
        write_srt(p, three_sections())
        r = self.run_tool(p, "--target", "1.5")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_target_equals_form_is_honoured(self):
        cues = [(i * 5, i * 5 + 4, "word%d alpha" % (i % 7)) for i in range(60)]
        p = os.path.join(self.dir, "long.srt")
        write_srt(p, cues)
        self.assertGreater(len(self.chapters_json(p)["chapters"]), 3)
        self.assertEqual(len(self.chapters_json(p, "--target=3")["chapters"]), 3)

    def test_target_below_three_is_rejected(self):
        p = os.path.join(self.dir, "t.srt")
        write_srt(p, three_sections())
        r = self.run_tool(p, "--target", "2")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--target", r.stderr)

    def test_all_digit_filename_is_accepted(self):
        p = os.path.join(self.dir, "20241001")
        write_srt(p, three_sections())
        old = os.getcwd()
        os.chdir(self.dir)
        try:
            r = self.run_tool("20241001", "--json")
        finally:
            os.chdir(old)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertGreaterEqual(len(json.loads(r.stdout)["chapters"]), 3)

    def test_missing_file_is_bad_input_exit_2(self):
        # Farsi pack contract (SKILL.md): 2 = bad input, message on stderr, stdout kept clean for --json.
        r = self.run_tool(os.path.join(self.dir, "nope.srt"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("nope.srt", r.stderr)
        self.assertEqual(r.stdout, "")

    def test_text_mode_still_works(self):
        p = os.path.join(self.dir, "t.srt")
        write_srt(p, three_sections())
        r = self.run_tool(p, "--target", "3")
        self.assertEqual(r.returncode, 0, r.stderr)
        # Intentional change (Farsi pack): text output is Persian now, so "3 chapters" became
        # "۳ فصل" and the "INVALID" warning became «نامعتبر». Same check, translated labels.
        self.assertIn("۳ فصل", r.stdout)
        self.assertNotIn("نامعتبر", r.stdout)


if __name__ == "__main__":
    unittest.main()
