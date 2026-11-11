"""Regression tests for skills/yt-edit/deadair.py (upstream English behaviour).

Run from the repo root:  python3 -I -m unittest discover -s tests -t .
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
TOOL = os.environ.get("DEADAIR_TOOL") or os.path.join(ROOT, "skills", "yt-edit", "deadair.py")


def _module():
    spec = importlib.util.spec_from_file_location("deadair_under_test", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def srt(*cues):
    out = []
    for i, (a, b, text) in enumerate(cues, 1):
        out.append("%d\n%s --> %s\n%s\n" % (i, a, b, text))
    return "\n".join(out)


class DeadairTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dm = _module()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name, content, binary=False):
        p = os.path.join(self.tmp, name)
        with open(p, "wb" if binary else "w", **({} if binary else {"encoding": "utf-8"})) as f:
            f.write(content)
        return p

    def run_tool(self, *args, cwd=None):
        return subprocess.run([sys.executable, "-I", TOOL] + list(args), capture_output=True,
                              text=True, cwd=cwd or self.tmp)

    def report(self, path, *extra):
        r = self.run_tool(path, "--json", *extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def kinds(self, rep, kind):
        return [c for c in rep["cuts"] if c["kind"] == kind]

    # 1 + 14: whisper JSON as a top-level list (deadair and chapters share this loader)
    def test_json_top_level_list(self):
        p = self.write("list.json", json.dumps([{"start": 0, "end": 2, "text": "hello there friend"},
                                                 {"start": 3, "end": 5, "text": "um"}]))
        self.assertEqual(len(self.dm.load(p)), 2)
        rep = self.report(p)
        self.assertEqual(len(self.kinds(rep, "FILLER")), 1)

    def test_json_segments_null_or_scalar(self):
        self.assertEqual(self.dm.load(self.write("n.json", '{"segments": null}')), [])
        self.assertEqual(self.dm.load(self.write("s.json", '"just a string"')), [])

    # 2: UTF-8 BOM
    def test_bom_json(self):
        p = self.write("bom.json", b'\xef\xbb\xbf{"segments":[{"start":0,"end":2,"text":"hello there friend"}]}',
                       binary=True)
        self.assertEqual(self.dm.load(p), [(0.0, 2.0, "hello there friend")])

    def test_bom_timestamp_first_srt_keeps_cue_one(self):
        body = "00:00:00,000 --> 00:00:02,000\nfirst cue\n\n00:00:03,000 --> 00:00:04,000\nsecond cue\n"
        p = self.write("bom.srt", b"\xef\xbb\xbf" + body.encode("utf-8"), binary=True)
        self.assertEqual([c[2] for c in self.dm.load(p)], ["first cue", "second cue"])

    # 3: duration zero
    def test_zero_duration_no_crash(self):
        p = self.write("zero.srt", "1\n00:00:00,000 --> 00:00:00,000\nhello\n")
        r = self.run_tool(p)
        self.assertNotIn("ZeroDivisionError", r.stderr)
        self.assertEqual(r.returncode, 0, r.stderr)

    # 4: overlapping cuts counted once
    def test_overlapping_cuts_union(self):
        p = self.write("overlap.srt", srt(("00:00:00,000", "00:00:04,000", "So I was going to say"),
                                          ("00:00:01,000", "00:00:04,000", "um"),
                                          ("00:00:04,000", "00:00:05,000", "So I was going to say this")))
        rep = self.report(p)
        self.assertAlmostEqual(rep["removed"], 4.0)
        self.assertAlmostEqual(rep["out"], 1.0)
        self.assertGreaterEqual(rep["out"], 0)
        txt = self.run_tool(p).stdout
        self.assertIn("80.0% shorter", txt)

    # 5 + 16: WebVTT cue ids / NOTE blocks
    def test_vtt_cue_ids_not_glued(self):
        p = self.write("ids.vtt", "WEBVTT\n\nc1\n00:00:00.000 --> 00:00:02.000\nWelcome back to the channel\n\n"
                                  "c2\n00:00:02.100 --> 00:00:03.000\num\n\n"
                                  "c3\n00:00:03.100 --> 00:00:05.000\nWelcome back to the channel everyone\n")
        self.assertEqual([c[2] for c in self.dm.load(p)],
                         ["Welcome back to the channel", "um", "Welcome back to the channel everyone"])
        rep = self.report(p)
        self.assertEqual([(c["start"], c["end"]) for c in self.kinds(rep, "FILLER")], [(2.1, 3.0)])
        self.assertEqual([(c["start"], c["end"]) for c in self.kinds(rep, "REPEAT")], [(0.0, 2.0)])

    def test_vtt_note_block_ignored(self):
        p = self.write("notes.vtt", "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nhello there\n\n"
                                    "NOTE this is a comment\nspanning lines\n\n"
                                    "speaker-segment\n00:00:02.100 --> 00:00:04.000\nmore words here\n")
        self.assertEqual([c[2] for c in self.dm.load(p)], ["hello there", "more words here"])

    # 6: digit-only cue text is speech
    def test_numeric_cue_text_kept(self):
        p = self.write("num.srt", srt(("00:00:00,000", "00:00:02,000", "How many did we sell?"),
                                      ("00:00:02,100", "00:00:03,000", "500"),
                                      ("00:00:05,000", "00:00:06,000", "That is a lot of units")))
        self.assertIn("500", [c[2] for c in self.dm.load(p)])
        dead = self.kinds(self.report(p), "DEAD")
        self.assertEqual(len(dead), 1)
        self.assertGreaterEqual(dead[0]["start"], 3.0)

    # 7: short aborted first take
    def test_short_restart_detected(self):
        p = self.write("short.srt", srt(("00:00:00,000", "00:00:01,200", "So the reason I"),
                                        ("00:00:01,300", "00:00:01,600", "um"),
                                        ("00:00:01,700", "00:00:04,000", "So the reason I started this channel")))
        rep = self.kinds(self.report(p), "REPEAT")
        self.assertEqual([(c["start"], c["end"]) for c in rep], [(0.0, 1.2)])

    def test_shorter_later_cue_is_not_a_restart(self):
        p = self.write("later.srt", srt(("00:00:00,000", "00:00:03,000", "So the reason I started this channel"),
                                        ("00:00:03,100", "00:00:04,000", "So the reason")))
        self.assertEqual(self.kinds(self.report(p), "REPEAT"), [])

    # 8: digits kept in norm()
    def test_numbered_steps_not_repeat(self):
        p = self.write("digits.srt", srt(("00:00:00,000", "00:00:03,000", "Step 1 open the settings menu"),
                                         ("00:00:03,100", "00:00:06,000", "Step 2 open the settings menu and pick a theme")))
        self.assertEqual(self.kinds(self.report(p), "REPEAT"), [])

    # 9: filler with punctuation / markup
    def test_filler_punctuation_and_markup(self):
        texts = ["Um?", "Uh…", "You know?", "<i>um</i>", "Um!", "um", "(uh)"]
        cues = [("00:00:0%d,000" % i, "00:00:0%d,900" % i, t) for i, t in enumerate(texts)]
        p = self.write("punct.srt", srt(*cues))
        self.assertEqual(len(self.kinds(self.report(p), "FILLER")), len(texts))

    def test_restart_across_punctuated_filler(self):
        p = self.write("retake.srt", srt(("00:00:00,000", "00:00:02,000", "Today we are going to"),
                                         ("00:00:02,100", "00:00:02,800", "Um?"),
                                         ("00:00:02,900", "00:00:05,000", "Today we are going to build an app")))
        self.assertEqual(len(self.kinds(self.report(p), "REPEAT")), 1)

    # 10: YouTube auto-caption VTT
    def test_youtube_auto_vtt(self):
        p = self.write("yt.vtt", (
            "WEBVTT\nKind: captions\nLanguage: en\n\n"
            "00:00:00.160 --> 00:00:02.869 align:start position:0%\n \n"
            "so<00:00:00.480><c> today</c><00:00:00.880><c> we're</c><00:00:01.120><c> going</c>"
            "<00:00:01.360><c> to</c><00:00:01.600><c> build</c>\n\n"
            "00:00:02.869 --> 00:00:02.879 align:start position:0%\nso today we're going to build\n \n\n"
            "00:00:02.879 --> 00:00:05.150 align:start position:0%\nso today we're going to build\n"
            "a<00:00:03.200><c> little</c><00:00:03.600><c> app</c><00:00:04.000><c> from</c>"
            "<00:00:04.400><c> scratch</c>\n\n"
            "00:00:05.150 --> 00:00:05.160 align:start position:0%\na little app from scratch\n \n\n"
            "00:00:05.160 --> 00:00:07.990 align:start position:0%\na little app from scratch\n"
            "and<00:00:05.500><c> then</c><00:00:06.000><c> ship</c><00:00:06.500><c> it</c>\n"))
        texts = [c[2] for c in self.dm.load(p)]
        self.assertEqual(texts, ["so today we're going to build", "a little app from scratch", "and then ship it"])
        self.assertEqual(self.kinds(self.report(p), "REPEAT"), [])

    # 11: empty whisper segments are not speech
    def test_empty_json_segments_dropped(self):
        p = self.write("empty.json", json.dumps({"segments": [
            {"start": 0, "end": 2, "text": "hello there friend"}, {"start": 2, "end": 9, "text": ""},
            {"start": 9, "end": 11, "text": "and we are back"}]}))
        dead = self.kinds(self.report(p), "DEAD")
        self.assertEqual(len(dead), 1)
        self.assertGreater(dead[0]["end"] - dead[0]["start"], 6)

    # 12: unsorted cues / duration = max end
    def test_unsorted_cues(self):
        p = self.write("unsorted.srt", "2\n00:00:10,000 --> 00:00:12,000\nsecond line here\n\n"
                                       "1\n00:00:00,000 --> 00:00:02,000\nfirst line here\n")
        rep = self.report(p)
        self.assertEqual(rep["duration"], 12.0)
        self.assertEqual(len(self.kinds(rep, "DEAD")), 1)

    def test_duration_is_max_end(self):
        p = self.write("endearly.srt", srt(("00:00:00,000", "00:00:30,000", "a very long first cue"),
                                           ("00:00:05,000", "00:00:06,000", "a short later one")))
        rep = self.report(p)
        self.assertEqual(rep["duration"], 30.0)
        self.assertEqual(self.kinds(rep, "DEAD"), [])

    # 13: argument parsing
    def _g(self):
        return self.write("g.srt", srt(("00:00:00,000", "00:00:01,000", "hello there friend"),
                                       ("00:00:01,500", "00:00:02,000", "more talking here")))

    def test_floor_equals_form(self):
        r = self.run_tool(self._g(), "--floor=0.1")
        self.assertIn("dead-air floor 0.1s", r.stdout)

    def test_floor_missing_value_clean_error(self):
        r = self.run_tool(self._g(), "--floor")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_numeric_filename(self):
        shutil.copy(self._g(), os.path.join(self.tmp, "2024.10"))
        r = self.run_tool("2024.10")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("2 cues", r.stdout)

    def test_negative_floor_rejected(self):
        r = self.run_tool("--floor", "-0.1", self._g())
        self.assertEqual(r.returncode, 2)
        self.assertIn("floor", r.stderr)

    def test_floor_space_form_still_works(self):
        r = self.run_tool(self._g(), "--floor", "0.35")
        self.assertIn("dead-air floor 0.35s", r.stdout)

    # 15: uppercase .JSON extension
    def test_uppercase_json_extension(self):
        p = self.write("whisper.JSON", json.dumps({"segments": [
            {"start": i * 4.0, "end": i * 4 + 3.5, "text": "cameras lenses"} for i in range(60)]}))
        self.assertEqual(len(self.dm.load(p)), 60)


if __name__ == "__main__":
    unittest.main()
