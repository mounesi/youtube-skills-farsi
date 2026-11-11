"""Regression tests for skills/yt-retention/retention.py (upstream English behaviour)."""
import json, os, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOL = os.path.join(ROOT, "skills", "yt-retention", "retention.py")


def run(*args):
    return subprocess.run([sys.executable, "-I", TOOL] + list(args),
                          capture_output=True, text=True, timeout=60)


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, name, lines):
        p = os.path.join(self.tmp.name, name)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        return p

    def jrun(self, *args):
        r = run(*args, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    # seconds axis 0..600 at 5 s steps, real slide 0.01/s, one 10-point cliff at 300,
    # six tiny 0.5-point dips over 0.1 s (steepest rate, small amount)
    def steep_csv(self):
        lines = ["pos,ret"]; y = 100.0
        wig = {100, 150, 200, 350, 400, 450}
        for x in range(0, 601, 5):
            if x > 0:
                y -= 0.05
            if x == 305:
                y -= 10.0
            lines.append(f"{x},{y:.3f}")
            if x in wig:
                y -= 0.5
                lines.append(f"{x + 0.1},{y:.3f}")
        return self.write("steep.csv", lines)

    def pct_csv(self):
        lines = ["Video position (%),Absolute audience retention (%)"]; y = 100.0
        for x in range(0, 101):
            if x > 0:
                y -= 0.3
            if x == 50:
                y -= 10.0
            lines.append(f"{x},{y:.2f}")
        return self.write("pct.csv", lines)

    def short90_csv(self):
        lines = ["Video position (s),Audience retention (%)"]
        for x in range(0, 91):
            y = 100 - 1.5 * x if x <= 30 else 55 - 0.1 * (x - 30)
            if x == 60:
                y -= 5  # a cliff at 59 -> 60 s
            if x > 60:
                y -= 5
            lines.append(f"{x},{y:.2f}")
        return self.write("short90.csv", lines)

    # bug 1: cliffs below rank 5 by rate vanished
    def test_cliff_below_rate_rank_five_is_found(self):
        out = self.jrun(self.steep_csv())
        froms = [c["from"] for c in out["cliffs"]]
        self.assertIn(300.0, froms)
        self.assertAlmostEqual(out["cliffs"][0]["lost"], 10.05, places=1)

    def test_cliffs_ranked_by_amount_lost(self):
        lines = ["pos,ret"]; y = 100.0
        for x in range(0, 300, 10):
            lines.append(f"{x},{y:.2f}")
            if x in (50, 100, 150, 200, 250):
                y -= 1.0; lines.append(f"{x + 0.1},{y:.2f}")  # steep but small
            if x == 120:
                y -= 6.0  # big, slower drop over 10 s
        out = self.jrun(self.write("rank.csv", lines))
        self.assertEqual(out["cliffs"][0]["from"], 120.0)
        self.assertEqual(out["cliffs"][0]["lost"], 6.0)

    # bug 2: seconds axis on a short video read as percent
    def test_short_seconds_axis(self):
        p = self.short90_csv()
        # Intentional change (Farsi pack): videos of 3 min or less are Shorts/Reels and their hook
        # window is the first 3 s, not 30 s. --hook-window 30 keeps this test about the axis fix.
        out = self.jrun(p, "--hook-window", "30")
        self.assertEqual(out["axis"], "seconds")
        self.assertAlmostEqual(out["hook_leak"], 45.0, places=1)
        self.assertTrue(all(c["at_seconds"] is not None for c in out["cliffs"]))
        out = self.jrun(p, "--duration", "90")
        for c in out["cliffs"]:
            self.assertEqual(c["at_seconds"], round(c["from"], 1))

    def test_axis_flag_and_duration_hint(self):
        lines = ["pos,ret"] + [f"{x},{100 - x * 0.2:.2f}" for x in range(0, 91)]
        p = self.write("noheader.csv", lines)
        self.assertEqual(self.jrun(p, "--axis", "seconds")["axis"], "seconds")
        self.assertEqual(self.jrun(p, "--duration", "90")["axis"], "seconds")
        self.assertEqual(self.jrun(p, "--axis", "pct")["axis"], "pct")
        r = run(p, "--json")
        # Intentional change: the axis note is now Farsi («فرض کردم»); it still names --axis.
        self.assertIn("--axis", r.stderr)
        self.assertIn("فرض کردم", r.stderr)

    # bug 3: slide included cliffs and was a plain mean of rates
    def test_slide_excludes_cliffs(self):
        out = self.jrun(self.pct_csv())
        self.assertAlmostEqual(out["slide_per_unit"], 0.3, places=2)

    def test_slide_is_span_weighted(self):
        out = self.jrun(self.steep_csv())
        self.assertLess(out["slide_per_unit"], 0.05)

    # bug 4: CLI argument handling
    def test_missing_values_are_usage_errors(self):
        p = self.pct_csv()
        for args in ([p, "--duration"], [p, "--transcript"], [p, "--duration", "abc"],
                     [p, "--duration", "-600"], [p, "--duration", "0"]):
            r = run(*args)
            self.assertNotEqual(r.returncode, 0, args)
            self.assertNotIn("Traceback", r.stderr, args)
            self.assertIn("usage", r.stderr.lower(), args)

    def test_duration_before_csv(self):
        out = self.jrun("--duration", "600", self.pct_csv())
        self.assertEqual(out["points"], 101)
        self.assertEqual(out["axis"], "pct")

    # bug 5: cells by index, mm:ss positions
    def test_mmss_positions(self):
        lines = ["Video position,Audience retention"]
        for i in range(0, 21):
            s = i * 3
            lines.append(f"{s // 60}:{s % 60:02d},{100 - i * 2}%")
        # Intentional change: a 60 s video counts as a Short (3 s hook window); --hook-window 30
        # keeps the upstream expectation about mm:ss parsing.
        out = self.jrun(self.write("mmss.csv", lines), "--hook-window", "30")
        self.assertEqual(out["points"], 21)
        self.assertEqual(out["axis"], "seconds")
        self.assertAlmostEqual(out["hook_leak"], 20.0, places=1)

    def test_columns_do_not_shift(self):
        lines = ["pos,ret,extra"] + [f"{x},{100 - x}%,1.1" for x in range(0, 12)]
        lines.append("12,n/a,1.1")  # unreadable retention -> skipped, not shifted
        out = self.jrun(self.write("cols.csv", lines))
        self.assertEqual(out["points"], 12)
        self.assertEqual(out["end"], 89.0)

    def test_hms_parse(self):
        sys.path.insert(0, os.path.dirname(TOOL))
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("retention_mod", TOOL)
            m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        finally:
            sys.path.pop(0)
        self.assertEqual(m._num("1:02:03"), 3723.0)
        self.assertEqual(m._num("0:30"), 30.0)
        self.assertEqual(m._num("98%"), 98.0)
        self.assertIsNone(m._num("abc"))


if __name__ == "__main__":
    unittest.main()
