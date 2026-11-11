"""Tests for skills/yt-retention/retention.py (Farsi pack)."""
import importlib.util, json, os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL = os.path.join(ROOT, "skills", "yt-retention")
TOOL = os.path.join(SKILL, "retention.py")
FIX = os.path.join(ROOT, "tests", "fixtures", "yt-retention")


def fx(name):
    return os.path.join(FIX, name)


def run(*args, tool=TOOL):
    return subprocess.run([sys.executable, "-I", tool] + list(args),
                          capture_output=True, text=True, timeout=60)


def load_module():
    sys.path.insert(0, SKILL)
    try:
        spec = importlib.util.spec_from_file_location("retention_fa_mod", TOOL)
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    finally:
        sys.path.pop(0)
    return m


class RetentionFaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, name, text, encoding="utf-8"):
        p = os.path.join(self.tmp.name, name)
        with open(p, "w", encoding=encoding, newline="") as fh:
            fh.write(text)
        return p

    def jrun(self, *args):
        r = run(*args, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    # --- reading Persian Studio exports
    def test_persian_headers_digits_and_percent_sign(self):
        out = self.jrun(fx("long_fa.csv"), "--duration", "600")
        self.assertEqual(out["points"], 101)
        self.assertEqual(out["axis"], "pct")          # «زمان ویدیو (٪)» -> percent axis
        self.assertEqual(out["kind"], "long")
        self.assertAlmostEqual(out["hook_leak"], 35.0, places=1)
        self.assertEqual(out["cliffs"][0]["from"], 39.0)
        self.assertAlmostEqual(out["cliffs"][0]["at_seconds"], 234.0, places=1)
        self.assertEqual(out["diagnosis"]["main"], "hook")

    def test_duration_accepts_mmss_and_persian_digits(self):
        a = self.jrun(fx("long_fa.csv"), "--duration", "۱۰:۰۰")
        self.assertEqual(a["duration"], 600.0)

    def test_semicolon_decimal_comma_short(self):
        out = self.jrun(fx("short_fa.csv"))
        self.assertEqual(out["axis"], "seconds")      # «(ثانیه)»
        self.assertEqual(out["kind"], "short")
        self.assertEqual(out["hook_window_s"], 3.0)
        self.assertAlmostEqual(out["hook_leak"], 24.6, places=1)
        self.assertEqual(out["cliffs"], [])
        self.assertEqual(len(out["bumps"]), 1)        # the loop at the end is a bump, not netted in
        self.assertAlmostEqual(out["slide_per_minute"], 36.0, places=1)

    def test_tab_utf16_and_arabic_digits(self):
        rows = ["Video position (s)\tAudience retention (%)"]
        for x in range(0, 300, 10):
            y = 100 - x * 0.1 - (8 if x >= 150 else 0)
            rows.append("%s\t%s" % (str(x).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")), "%.1f" % y))
        p = self.write("u16.csv", "\r\n".join(rows) + "\r\n", encoding="utf-16")
        out = self.jrun(p)
        self.assertEqual(out["points"], 30)
        self.assertEqual(out["cliffs"][0]["from"], 140.0)

    def test_picks_absolute_column_over_relative_and_by_header(self):
        rows = ["نسبی,زمان ویدیو,درصد بینندگان (نسبی),درصد بینندگان (مطلق)"]
        for x in range(0, 21):
            rows.append("1.1,%d,50,%d" % (x * 10, 100 - x))
        out = self.jrun(self.write("cols.csv", "\n".join(rows)), "--axis", "seconds")
        self.assertEqual(out["points"], 21)
        self.assertEqual(out["start"], 100.0)
        self.assertEqual(out["end"], 80.0)

    def test_fraction_retention_is_scaled(self):
        rows = ["pos,ret"] + ["%d,%.3f" % (x * 10, 1 - x * 0.01) for x in range(0, 30)]
        r = run(self.write("frac.csv", "\n".join(rows)), "--json")
        out = json.loads(r.stdout)
        self.assertEqual(out["start"], 100.0)
        self.assertIn("ضرب", r.stderr)

    def test_num_cells(self):
        m = load_module()
        self.assertEqual(m._num("۹۸٫۵٪"), 98.5)
        self.assertEqual(m._num("98,5"), 98.5)
        self.assertEqual(m._num("1,234"), 1234.0)
        self.assertEqual(m._num("۱:۰۵"), 65.0)
        self.assertIsNone(m._num("درصد بینندگان"))
        self.assertIsNone(m._num("n/a"))

    # --- transcript at each cliff
    def test_transcript_line_at_cliff_and_opening(self):
        out = self.jrun(fx("long_fa.csv"), "--duration", "600", "--transcript", fx("transcript_fa.srt"))
        line = out["cliffs"][0]["line"]
        self.assertIn("اسپانسر", line)
        self.assertEqual(out["said"]["39.0"], line)
        self.assertIn("سلام دوستان", out["opening"])

    def test_transcript_without_duration_warns(self):
        r = run(fx("long_fa.csv"), "--transcript", fx("transcript_fa.srt"), "--json")
        self.assertEqual(r.returncode, 0)
        self.assertIn("--duration", r.stderr)

    def test_missing_transcript_is_farsi_error(self):
        r = run(fx("long_fa.csv"), "--duration", "600", "--transcript", fx("nope.srt"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("رونوشت خوانده نشد", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    # --- compare
    def test_compare_two_videos(self):
        out = self.jrun(fx("long_fa.csv"), "--duration", "600", "--compare", fx("other_fa.csv"),
                        "--compare-duration", "600")
        c = out["compare"]
        self.assertEqual(c["main_gap"], "hook")
        self.assertAlmostEqual(c["lost_diff"]["hook"], 20.0, places=1)
        self.assertTrue(c["same_kind"])
        self.assertEqual(c["other"]["file"], "other_fa.csv")

    def test_compare_text_report(self):
        r = run(fx("long_fa.csv"), "--duration", "600", "--compare", fx("other_fa.csv"),
                "--compare-duration", "600")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("مقایسه‌ی دو ویدیو", r.stdout)
        self.assertIn("بیشترین فاصله در «نشت هوک»", r.stdout)

    def test_compare_missing_file(self):
        r = run(fx("long_fa.csv"), "--compare", fx("nope.csv"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("فایل مقایسه پیدا نشد", r.stderr)

    # --- Farsi report
    def test_text_report_is_farsi_and_ends_with_gate(self):
        r = run(fx("long_fa.csv"), "--duration", "600", "--transcript", fx("transcript_fa.srt"))
        self.assertEqual(r.returncode, 0, r.stderr)
        for word in ("نشت هوک", "پرتگاه", "سرازیری", "تشخیص", "۳:۵۴", "«"):
            self.assertIn(word, r.stdout)
        self.assertEqual(r.stdout.strip().splitlines()[-1].strip(), "منتشرش کنیم یا تغییرش بدیم؟")
        self.assertNotIn("ي", r.stdout); self.assertNotIn("ك", r.stdout)

    def test_short_report_mentions_first_seconds(self):
        r = run(fx("short_fa.csv"))
        self.assertIn("۳ ثانیه‌ی اول", r.stdout)
        self.assertIn("/yt-reel", r.stdout)
        self.assertIn("برگشت‌ها", r.stdout)

    def test_cliff_diagnosis(self):
        rows = ["pos,ret"]; y = 100.0
        for x in range(0, 601, 5):
            if 0 < x <= 30: y -= 1.0          # healthy hook: 6 points
            elif x > 30: y -= 0.02
            if x == 300: y -= 15.0
            rows.append("%d,%.2f" % (x, y))
        out = self.jrun(self.write("cliff.csv", "\n".join(rows)))
        self.assertEqual(out["diagnosis"]["main"], "cliff")
        r = run(self.write("cliff2.csv", "\n".join(rows)))
        self.assertIn("برو سر ۴:۵۵", r.stdout)

    def test_fine_video_points_to_packaging(self):
        rows = ["pos,ret"] + ["%d,%.2f" % (x, 100 - (x * 0.3 if x <= 30 else 9 + (x - 30) * 0.01))
                              for x in range(0, 601, 5)]
        out = self.jrun(self.write("fine.csv", "\n".join(rows)))
        self.assertTrue(out["diagnosis"]["fine"])
        r = run(self.write("fine2.csv", "\n".join(rows)))
        self.assertIn("/yt-package", r.stdout)

    # --- errors
    def test_bad_files_do_not_traceback(self):
        empty = self.write("empty.csv", "زمان,درصد\n")
        for args in ([empty], [fx("nope.csv")], [self.tmp.name]):
            r = run(*args)
            self.assertEqual(r.returncode, 1, args)
            self.assertNotIn("Traceback", r.stderr, args)

    # --- portability: the skill folder works on its own
    def test_folder_copied_alone(self):
        dst = os.path.join(self.tmp.name, "yt-retention")
        shutil.copytree(SKILL, dst)
        r = run(fx("long_fa.csv"), "--duration", "600", "--transcript", fx("transcript_fa.srt"), "--json",
                tool=os.path.join(dst, "retention.py"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("اسپانسر", json.loads(r.stdout)["cliffs"][0]["line"])

    def test_no_cross_skill_imports(self):
        with open(TOOL, encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn("deadair", src)
        self.assertNotIn('"..", "yt-', src)   # never reach into another skill folder


if __name__ == "__main__":
    unittest.main()
