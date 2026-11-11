# -*- coding: utf-8 -*-
"""آزمون‌های skills/yt-edit/deadair.py (نسخه‌ی فارسی و دوزبانه).

اجرا از ریشه‌ی مخزن:  python3 -I -m unittest discover -s tests -t .
"""
import csv
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL = os.path.join(ROOT, "skills", "yt-edit")
TOOL = os.path.join(SKILL, "deadair.py")
FIX = os.path.join(ROOT, "tests", "fixtures", "yt-edit")
TAKE = os.path.join(FIX, "learning_take_fa.json")
SRT = os.path.join(FIX, "talking_head_fa.srt")


def _module():
    spec = importlib.util.spec_from_file_location("deadair_fa_under_test", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def words_json(segments):
    """segments = [[(word, start, end), ...], ...] -> whisper json with word timings"""
    out = {"segments": []}
    for ws in segments:
        out["segments"].append({"start": ws[0][1], "end": ws[-1][2], "text": " ".join(w for w, _, _ in ws),
                                "words": [{"word": " " + w, "start": a, "end": b} for w, a, b in ws]})
    return json.dumps(out, ensure_ascii=False)


class YtEditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dm = _module()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name, content):
        p = os.path.join(self.tmp, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return p

    def run_tool(self, *args, cwd=None):
        return subprocess.run([sys.executable, "-I", TOOL] + list(args), capture_output=True, text=True,
                              cwd=cwd or self.tmp)

    def report(self, path, *extra):
        r = self.run_tool(path, "--json", *extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def kinds(self, rep, kind):
        return [c for c in rep["cuts"] if c["kind"] == kind]

    def words_of(self, path):
        return self.dm.load(path, words=True)

    # ---------------------------------------------------------- Persian fillers

    def test_cue_level_persian_fillers(self):
        rep = self.report(SRT)
        fill = [(c["start"], c["end"]) for c in self.kinds(rep, "FILLER")]
        self.assertEqual(fill, [(4.1, 4.8), (8.3, 8.9)])  # «اِ…» and «خب، یعنی…»
        self.assertEqual(self.kinds(rep, "FILLER")[0]["label"], "پرکننده")

    def test_elongated_hesitations_word_level(self):
        rep = self.report(TAKE)
        whys = [c["why"] for c in self.kinds(rep, "FILLER")]
        self.assertIn("«اِاِاِ»", whys)
        self.assertIn("«اممم»", whys)

    def test_standalone_only_for_discourse_words(self):
        rep = self.report(TAKE)
        texts = " ".join(c["why"] for c in self.kinds(rep, "FILLER"))
        self.assertIn("خب", texts)          # «خب،» stands alone before a comma
        self.assertNotIn("حالا", texts)     # «حالا بریم سراغ…» is a real word here

    def test_inline_filler_in_suggest_and_learning(self):
        p = self.write("in.json", words_json([[("این", 0.0, 0.3), ("اِ", 0.35, 0.6), ("دکمه", 0.65, 1.0),
                                                 ("رو", 1.05, 1.2), ("بزنید.", 1.25, 1.7)]]))
        for mode in ("suggest", "learning"):
            fill = self.kinds(self.report(p, "--mode", mode), "FILLER")
            self.assertEqual([(c["start"], c["end"]) for c in fill], [(0.35, 0.6)], mode)

    def test_he_is_not_a_filler(self):
        p = self.write("ham.json", words_json([[("من", 0.0, 0.2), ("هم", 0.25, 0.4), ("خسته", 0.45, 0.8),
                                                  ("ام.", 0.85, 1.0)]]))
        self.assertEqual(self.kinds(self.report(p, "--mode", "learning"), "FILLER"), [])

    # ---------------------------------------------------------- repeats / restarts

    def test_persian_restart_word_level(self):
        rep = self.report(TAKE)
        rpt = self.kinds(rep, "REPEAT")
        self.assertEqual([(c["start"], c["end"]) for c in rpt], [(6.6, 7.45)])  # first «تو کلاد بخش»
        self.assertIn("تو کلاد بخش", rpt[0]["why"])
        self.assertEqual(rpt[0]["label"], "تکرار")

    def test_reduplication_is_not_a_stutter(self):
        rep = self.report(TAKE)
        self.assertFalse(any("کم" == c["why"].strip("«»تکرار ") for c in self.kinds(rep, "REPEAT")))
        self.assertEqual(len(self.kinds(rep, "REPEAT")), 1)

    def test_cut_off_last_word_restart(self):
        p = self.write("cut.json", words_json([[("بخش", 0.0, 0.3), ("پرو", 0.35, 0.6), ("بخش", 0.9, 1.2),
                                                  ("پروژه‌ها", 1.25, 1.8), ("رو", 1.85, 2.0), ("ببینید.", 2.05, 2.5)]]))
        rpt = self.kinds(self.report(p), "REPEAT")
        self.assertEqual([(c["start"], c["end"]) for c in rpt], [(0.0, 0.6)])

    def test_cue_level_persian_restart_and_digits(self):
        rep = self.report(SRT)
        self.assertEqual([(c["start"], c["end"]) for c in self.kinds(rep, "REPEAT")], [(6.2, 8.0)])
        # «۱۲ هزار» is a bare number: speech, not dead air
        self.assertTrue(all(not (c["start"] < 14.0 < c["end"]) for c in rep["cuts"]))

    def test_restart_across_filler_persian_digits_norm(self):
        p = self.write("d.srt", "1\n00:00:00,000 --> 00:00:02,000\nقدم ۱ تنظیمات رو باز کنید\n\n"
                                "2\n00:00:02,100 --> 00:00:04,000\nقدم ۲ تنظیمات رو باز کنید و تم رو عوض کنید\n")
        self.assertEqual(self.kinds(self.report(p), "REPEAT"), [])  # different numbers, not a restart

    # ---------------------------------------------------------- modes

    def test_learning_tightens_every_pause_to_keep(self):
        rep = self.report(TAKE, "--mode", "learning")
        keep = rep["keep"]
        self.assertGreater(len(keep), 1)
        words = [w for w in self.words_of(TAKE)]
        kept_words = [w for w in words if any(a - 0.001 <= w.start and w.end <= b + 0.001 for a, b in keep)]
        # no kept piece of speech ends with more than ~0.1 s + one frame of silence before the jump
        cut_spans = [(a, b) for a, b in rep["merged"]]
        for a, b in cut_spans:
            before = [w.end for w in kept_words if w.end <= a + 1e-6]
            if before:
                self.assertLessEqual(a - max(before), 0.1 + 1e-6)
        self.assertLess(rep["out"], self.report(TAKE)["out"])

    def test_suggest_keeps_floor_breath(self):
        rep = self.report(TAKE)
        for c in self.kinds(rep, "DEAD"):
            self.assertIn("مکث", c["why"])
        self.assertEqual(rep["mode"], "suggest")
        self.assertNotIn("keep", rep)

    def test_learning_keep_value(self):
        a = self.report(TAKE, "--mode", "learning", "--keep", "0.2")
        b = self.report(TAKE, "--mode", "learning", "--keep", "۰٫۴")  # Persian digits work
        self.assertGreater(b["out"], a["out"])

    def test_never_cuts_mid_word(self):
        words = self.words_of(TAKE)
        for mode in ("suggest", "learning"):
            rep = self.report(TAKE, "--mode", mode)
            removed = {(c["start"], c["end"]) for c in rep["cuts"] if c["kind"] != "DEAD"}
            for a, b in rep["merged"]:
                for w in words:
                    inside_cut = a <= w.start and w.end <= b
                    if inside_cut:
                        continue  # a whole removed word
                    self.assertFalse(w.start < a < w.end, (mode, a, w))
                    self.assertFalse(w.start < b < w.end, (mode, b, w))
            self.assertTrue(removed)

    def test_snap_keeps_overlapping_speech(self):
        # a filler cue that overlaps a kept speech cue must not eat the speech
        p = self.write("ov.srt", "1\n00:00:00,000 --> 00:00:03,000\nامروز درباره‌ی ریتنشن حرف می‌زنیم\n\n"
                                 "2\n00:00:02,000 --> 00:00:03,500\nاممم\n")
        fill = self.kinds(self.report(p), "FILLER")
        self.assertEqual([(c["start"], c["end"]) for c in fill], [(3.0, 3.5)])

    # ---------------------------------------------------------- bilingual

    def test_english_word_level(self):
        p = self.write("en.json", words_json([[("So,", 0.0, 0.3), ("the", 0.4, 0.5), ("the", 0.6, 0.7),
                                                 ("reason", 0.75, 1.1), ("um", 1.15, 1.4), ("I", 1.45, 1.5),
                                                 ("started.", 1.55, 2.0)]]))
        rep = self.report(p, "--mode", "learning")
        self.assertEqual([(c["start"], c["end"]) for c in self.kinds(rep, "REPEAT")], [(0.4, 0.5)])
        fills = sorted((c["start"], c["end"]) for c in self.kinds(rep, "FILLER"))
        self.assertEqual(fills, [(0.0, 0.3), (1.15, 1.4)])

    def test_mixed_language_restart(self):
        p = self.write("mix.srt", "1\n00:00:00,000 --> 00:00:01,500\nتو Claude Code بخش\n\n"
                                  "2\n00:00:01,600 --> 00:00:02,000\nاِ\n\n"
                                  "3\n00:00:02,100 --> 00:00:05,000\nتو Claude Code بخش پروژه‌ها رو باز کنید\n")
        self.assertEqual([(c["start"], c["end"]) for c in self.kinds(self.report(p), "REPEAT")], [(0.0, 1.5)])

    # ---------------------------------------------------------- exports

    def test_marker_csv_suggest(self):
        out = os.path.join(self.tmp, "m.csv")
        r = self.run_tool(SRT, "--markers", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[0], ["name", "timecode", "duration", "note", "color"])
        self.assertEqual(rows[1][0], "پرکننده")
        self.assertEqual(rows[1][1], "01:00:04:03")       # 4.10 s at 30 fps on a 01:00:00:00 timeline
        self.assertEqual(rows[1][2], "00:00:00:21")       # 0.70 s = 21 frames
        self.assertIn("سکوت", [row[0] for row in rows[1:]])

    def test_marker_edl_suggest_resolve_format(self):
        out = os.path.join(self.tmp, "m.edl")
        self.assertEqual(self.run_tool(SRT, "--edl", out).returncode, 0)
        with open(out, encoding="utf-8") as f:
            txt = f.read()
        self.assertTrue(txt.startswith("TITLE: talking_head_fa\nFCM: NON-DROP FRAME\n"))
        self.assertIn("001  001      V     C        01:00:04:03 01:00:04:04 01:00:04:03 01:00:04:04", txt)
        self.assertIn("|C:ResolveColorYellow |M:پرکننده", txt)
        self.assertIn("|D:21", txt)

    def test_latin_labels(self):
        out = os.path.join(self.tmp, "m.edl")
        self.run_tool(SRT, "--edl", out, "--latin-labels")
        with open(out, encoding="utf-8") as f:
            self.assertIn("|M:FILLER", f.read())

    def test_cut_edl_learning(self):
        out = os.path.join(self.tmp, "cut.edl")
        r = self.run_tool(TAKE, "--mode", "learning", "--edl", out, "--clip", "take01.mov", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        rep = json.loads(r.stdout)
        with open(out, encoding="utf-8") as f:
            lines = f.read().splitlines()
        events = [l for l in lines if l[:3].isdigit()]
        self.assertEqual(len(events), 2 * len(rep["keep"]))  # one V and one AA per kept piece
        self.assertIn("* FROM CLIP NAME: take01.mov", lines)
        # record side is continuous: each event starts where the previous piece ended
        vids = [l.split() for l in events if l.split()[2] == "V"]
        self.assertEqual(vids[0][6], "01:00:00:00")
        for prev, cur in zip(vids, vids[1:]):
            self.assertEqual(prev[7], cur[6])
        # source side: the first piece starts after the leading silence, at a frame of silence
        self.assertEqual(vids[0][4], "00:00:00:15")

    def test_learning_markers_on_edited_timeline(self):
        out = os.path.join(self.tmp, "jumps.csv")
        rep = json.loads(self.run_tool(TAKE, "--mode", "learning", "--markers", out, "--json").stdout)
        with open(out, encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))[1:]
        self.assertEqual(len(rows), len(rep["keep"]) - 1)  # one marker per jump cut
        self.assertTrue(all(r[2] == "00:00:00:01" for r in rows))
        self.assertIn("تکرار", rows[0][0])

    def test_fps_variants(self):
        a = self.report(SRT, "--fps", "25")
        self.assertEqual(a["cuts"][0]["tc_in"], "00:00:04:03")  # 4.1 s * 25 = 102.5 -> frame 103
        b = self.report(SRT, "--fps", "۲۴")
        self.assertEqual(b["fps"], 24)
        c = self.report(SRT, "--fps", "29.97")
        self.assertEqual(c["cuts"][0]["tc_in"], "00:00:04:03")
        r = self.run_tool(SRT, "--fps", "0")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_bad_timecode_flag(self):
        r = self.run_tool(SRT, "--record-tc", "1:00")
        self.assertEqual(r.returncode, 2)
        self.assertIn("تایم‌کد", r.stderr)

    # ---------------------------------------------------------- report text / CLI

    def test_farsi_report(self):
        r = self.run_tool(TAKE)
        self.assertEqual(r.returncode, 0, r.stderr)
        for word in ("سکوت", "پرکننده", "تکرار", "پیشنهاد برش", "هیچ‌چیز حذف نشده", "کلمه‌به‌کلمه", "قبلش"):
            self.assertIn(word, r.stdout)
        self.assertNotIn("ي", r.stdout)
        self.assertNotIn("ك", r.stdout)
        r2 = self.run_tool(TAKE, "--mode", "learning")
        self.assertIn("جامپ‌کات", r2.stdout)
        self.assertIn("مکث‌ها ← ۰٫۲ ثانیه", r2.stdout)

    def test_missing_file_and_directory(self):
        r = self.run_tool(os.path.join(self.tmp, "nope.srt"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("فایل پیدا نشد", r.stderr)
        r = self.run_tool(self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Traceback", r.stderr)

    def test_no_words_flag(self):
        rep = self.report(TAKE, "--no-words")
        self.assertFalse(rep["word_level"])
        self.assertTrue(self.report(TAKE)["word_level"])

    def test_portable_copy_alone(self):
        # the skill folder works on its own (copied alone into ~/.claude/skills/)
        dst = os.path.join(self.tmp, "yt-edit")
        shutil.copytree(SKILL, dst)
        r = subprocess.run([sys.executable, "-I", os.path.join(dst, "deadair.py"), TAKE, "--json"],
                           capture_output=True, text=True, cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads(r.stdout)["cuts"])

    def test_compat_exports_for_old_tools(self):
        cues = self.dm.load(SRT)
        self.assertEqual(cues[0][0], 0.5)
        self.assertEqual(self.dm.parse_ts("00:01:05,250"), 65.25)
        with self.assertRaises(ValueError):
            self.dm.parse_ts("nope")


    # ---------------------------------------------------------- review fixes (regressions)

    def test_learning_breath_survives_fillers_touching_kept_words(self):
        # «اِ» touches both kept neighbours; the real silence lies between the two fillers
        p = self.write("zero.json", words_json([[("سلام", 0.0, 0.5), ("دوستان.", 0.5, 1.0), ("اِ", 1.0, 1.4),
                                                   ("اِ", 2.4, 2.8), ("امروز", 2.8, 3.3), ("شروع", 3.35, 3.8),
                                                   ("کنیم.", 3.85, 4.2)]]))
        rep = self.report(p, "--mode", "learning")
        keep = rep["keep"]
        kept_between = sum(max(0.0, min(b, 2.8) - max(a, 1.0)) for a, b in keep)
        self.assertAlmostEqual(kept_between, 0.2, places=2)
        for a, b in ((1.0, 1.4), (2.4, 2.8)):  # both «اِ» fully cut
            self.assertTrue(any(x <= a + 1e-6 and b <= y + 1e-6 for x, y in rep["merged"]), (a, b))
        # a filler, then a removed repeat, both away from the kept word: the 0.2 s stays too
        p2 = self.write("t1.json", words_json([[("کنید.", 7.5, 8.0), ("خب،", 9.0, 9.3), ("the", 9.6, 9.8),
                                                  ("the", 9.8, 10.0), ("end.", 10.05, 10.4)]]))
        rep2 = self.report(p2, "--mode", "learning")
        kept2 = sum(max(0.0, min(b, 9.8) - max(a, 8.0)) for a, b in rep2["keep"])
        self.assertAlmostEqual(kept2, 0.2, places=2)

    def test_learning_restart_is_one_cut(self):
        rep = self.report(TAKE, "--mode", "learning")
        self.assertEqual(len(self.kinds(rep, "REPEAT")), 1)

    def test_parallel_sentences_are_not_a_restart(self):
        p = self.write("a.srt", "1\n00:00:01,000 --> 00:00:04,000\nاگر روی این دکمه کلیک کنید منوی تنظیمات باز می‌شود.\n\n"
                                "2\n00:00:04,200 --> 00:00:07,000\nاگر روی این دکمه کلیک کنید پنجره‌ی ذخیره را می‌بینید.\n")
        for mode in ("suggest", "learning"):
            self.assertEqual(self.kinds(self.report(p, "--mode", mode), "REPEAT"), [], mode)

    def test_more_persian_reduplications_are_meaning(self):
        text = "فایل‌ها رو یکی یکی باز کنید و تک تک خط‌ها رو رفته رفته آهسته آهسته بخونید که که بعد"
        p = self.write("redup.json", words_json([[(w, i * 0.4, i * 0.4 + 0.35)
                                                    for i, w in enumerate(text.split())]]))
        rpt = self.kinds(self.report(p, "--mode", "learning"), "REPEAT")
        self.assertEqual([c["why"] for c in rpt], ["تکرار «که»"])  # only the real stutter

    def test_answer_yes_is_not_a_filler(self):
        p = self.write("b.srt", "1\n00:00:00,000 --> 00:00:03,000\nآیا این ابزار رایگان است؟\n\n"
                                "2\n00:00:03,300 --> 00:00:03,800\nبله.\n\n"
                                "3\n00:00:04,000 --> 00:00:04,800\nخب، یعنی…\n\n"
                                "4\n00:00:05,000 --> 00:00:07,000\nو همین الان امتحانش کنید.\n")
        for mode in ("suggest", "learning"):
            fill = self.kinds(self.report(p, "--mode", mode), "FILLER")
            self.assertEqual([(c["start"], c["end"]) for c in fill], [(4.0, 4.8)], mode)

    def test_zwnj_or_space_restart(self):
        p = self.write("zw.srt", "1\n00:00:00,000 --> 00:00:02,000\nسلام به همه\n\n"
                                 "2\n00:00:02,200 --> 00:00:04,000\nامروز می‌خوام درباره‌ی پرامپت\n\n"
                                 "3\n00:00:04,300 --> 00:00:07,000\nامروز می خوام درباره‌ی پرامپت حرف بزنم\n")
        self.assertEqual([(c["start"], c["end"]) for c in self.kinds(self.report(p), "REPEAT")], [(2.2, 4.0)])
        j = self.write("zw.json", words_json([[("تو", 0.0, 0.2), ("کلاد", 0.25, 0.5), ("می", 0.55, 0.7),
                                                 ("تونی", 0.75, 1.0), ("تو", 1.3, 1.5), ("کلاد", 1.55, 1.8),
                                                 ("می‌تونی", 1.85, 2.2), ("پروژه", 2.25, 2.6),
                                                 ("بسازی.", 2.65, 3.0)]]))
        rpt = self.kinds(self.report(j, "--mode", "learning"), "REPEAT")
        self.assertEqual([(c["start"], c["end"]) for c in rpt], [(0.0, 1.0)])

    def test_cue_level_cut_off_last_word(self):
        p = self.write("cut.srt", "1\n00:00:00,000 --> 00:00:02,000\nامروز می‌خوام درباره‌ی پرامپت\n\n"
                                  "2\n00:00:02,300 --> 00:00:05,000\nامروز می‌خوام درباره‌ی پرامپت‌نویسی حرف بزنم\n")
        self.assertEqual([(c["start"], c["end"]) for c in self.kinds(self.report(p), "REPEAT")], [(0.0, 2.0)])

    def test_no_zero_frame_cuts(self):
        p = self.write("sub.srt", "1\n00:00:00,000 --> 00:00:02,000\nسلام دوستان\n\n"
                                  "2\n00:00:02,460 --> 00:00:04,000\nامروز شروع می‌کنیم\n")
        out = os.path.join(self.tmp, "m.edl")
        rep = self.report(p, "--edl", out)
        self.assertEqual(rep["cuts"], [])
        self.assertEqual(rep["removed"], 0)
        with open(out, encoding="utf-8") as f:
            self.assertNotIn("|D:", f.read())

    def test_unwritable_output_paths(self):
        r = self.run_tool(SRT, "--edl", os.path.join(self.tmp, "no", "such", "x.edl"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("فایل نوشته نشد", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        folder = os.path.join(self.tmp, "dir.srt")
        os.mkdir(folder)
        ok = os.path.join(self.tmp, "ok.edl")
        r = self.run_tool(SRT, "--edl", ok, "--markers", folder)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Traceback", r.stderr)
        self.assertFalse(os.path.exists(ok))           # nothing half-written
        self.assertEqual(sorted(os.listdir(self.tmp)), ["dir.srt"])

    def test_fps_below_one_rejected(self):
        r = self.run_tool(SRT, "--fps", "0.4")
        self.assertEqual(r.returncode, 2)
        self.assertIn("نرخ فریم", r.stderr)

    def test_help_is_persian(self):
        for args in (["--help"], ["--bogus"]):
            r = self.run_tool(*args)
            text = r.stdout + r.stderr
            self.assertIn("استفاده:", text)
            for en in ("usage:", "positional arguments", "optional arguments", "options:", "show this help"):
                self.assertNotIn(en, text, (args, en))

    def test_addresses_user_as_to(self):
        for mode in ("suggest", "learning"):
            out = self.run_tool(SRT, "--mode", mode).stdout
            for shoma in ("بپذیرید", "بزنید و", "خودتان", "گوش کنید", "بدهید"):
                self.assertNotIn(shoma, out)

    def test_long_take_is_fast(self):
        import time
        words = "امروز درباره‌ی کلاد حرف می‌زنیم اِ خب این دکمه رو بزنید پروژه".split()
        segs, t = [], 0.0
        for s in range(400):
            ws = []
            for k in range(10):
                ws.append((words[(s * 7 + k * 3) % len(words)], round(t, 3), round(t + 0.25, 3)))
                t += 0.25 + (0.6 if k % 3 == 0 else 0.05)
            segs.append(ws)
            t += 0.8
        p = self.write("big.json", words_json(segs))
        t0 = time.time()
        rep = self.dm.analyse(p, "learning")
        clock = self.dm.Clock(30.0, "01:00:00:00", "00:00:00:00")
        self.dm.learning_markers(rep, clock, False)
        self.dm.suggest_markers(self.dm.analyse(p, "suggest"), clock, False)
        self.assertLess(time.time() - t0, 1.0)

if __name__ == "__main__":
    unittest.main()
