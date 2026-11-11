#!/usr/bin/env python3
"""retention.py - read a YouTube Studio audience-retention export and find the leaks.

    python3 retention.py retention.csv
    python3 retention.py retention.csv --transcript transcript.srt   # names what was said at each drop
    python3 retention.py retention.csv --json
    python3 retention.py retention.csv --duration 600 --axis pct     # force the axis when it is ambiguous

Get the file from Studio: Analytics -> a video -> Engagement -> the audience-retention chart ->
the download icon -> "Audience retention". Two columns, a position (percent or seconds) and a
percentage still watching.

It reports three things, because they are three different problems with three different fixes:
  HOOK LEAK    what you lost in the first 30 seconds
  CLIFFS       single steep drops - a specific moment people left at
  SLIDE        the steady bleed rate across the flat middle

With --transcript it prints what you were saying at each cliff, which is the only version of this
report you can act on without scrubbing the video yourself.
"""
import argparse, csv, json, os, re, sys

def _num(c):
    """One cell -> float. Handles '98%', '1,234', and h:mm:ss / m:ss positions. None if unreadable."""
    c = c.strip().replace("%", "").replace(",", "")
    if not c: return None
    try:
        if ":" in c:
            return sum(float(p) * 60 ** i for i, p in enumerate(reversed(c.split(":"))))
        return float(c)
    except ValueError:
        return None

def load_csv(path, info=None):
    """Rows of (position, retention). Position is column 0 and retention column 1, by index.
    If `info` is a dict it gets 'header' (first column name, if any) and 'colon' (mm:ss seen)."""
    rows = []
    header = None; colon = False
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
        for r in csv.reader(fh):
            if len(r) < 2: continue
            x, y = _num(r[0]), _num(r[1])
            if x is None or y is None:
                if header is None and not rows and r[0].strip(): header = r[0].strip()
                continue
            if ":" in r[0]: colon = True
            rows.append((x, y))
    if info is not None:
        info["header"] = header; info["colon"] = colon
    return rows

def _duration(v):
    try: f = float(v)
    except ValueError: raise argparse.ArgumentTypeError(f"not a number: {v!r}")
    if f <= 0: raise argparse.ArgumentTypeError("must be greater than 0 seconds")
    return f

def detect_axis(xs, dur=None, forced=None, header=None, colon=False):
    """-> (pct_axis, reason)."""
    if forced: return forced == "pct", "--axis"
    if colon: return False, "mm:ss positions"
    h = (header or "").lower()
    if "%" in h or "percent" in h: return True, "header"
    if "second" in h or "time" in h or re.search(r"\(s\)|\bsec", h): return False, "header"
    mx = max(xs)
    if dur:
        if abs(mx - dur) <= max(2.0, 0.05 * dur): return False, "--duration"
        if abs(mx - 100.0) <= 1.0 and dur > 105: return True, "--duration"
    return mx <= 100.5, "guess"

def main():
    ap = argparse.ArgumentParser(add_help=True, usage="python3 retention.py retention.csv [--transcript FILE] [--duration SECONDS] [--axis pct|seconds] [--json]")
    ap.add_argument("csv", nargs="?")
    ap.add_argument("--transcript", default=None)
    ap.add_argument("--duration", type=_duration, default=None)
    ap.add_argument("--axis", choices=["pct", "seconds"], default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    as_json = args.json; tr = args.transcript; dur = args.duration
    files = [args.csv] if args.csv else []
    if not files or not os.path.exists(files[0]): print(__doc__); sys.exit(1)
    info = {}
    rows = load_csv(files[0], info)
    if len(rows) < 8: print("could not read at least 8 data points from that csv"); sys.exit(1)
    xs = [r[0] for r in rows]; ys = [r[1] for r in rows]
    pct_axis, why = detect_axis(xs, dur, args.axis, info.get("header"), info.get("colon"))
    if why == "guess":
        print(f"note: assuming a {'percent' if pct_axis else 'seconds'} axis (max position {max(xs):g}); "
              "pass --axis pct|seconds to override", file=sys.stderr)
    def at(x): return (x / 100.0 * dur) if (pct_axis and dur) else x
    start = ys[0] or 100.0
    # HOOK: the first 30 seconds, or the first 10% when the axis is a percentage and we have no duration
    cutoff = 30.0 if not pct_axis else (30.0 / dur * 100 if dur else 10.0)
    hook_end = min((y for x, y in rows if x <= cutoff), default=start)
    hook_leak = start - hook_end
    drops = []
    for i in range(1, len(rows)):
        d = ys[i - 1] - ys[i]
        span = xs[i] - xs[i - 1] or 1
        drops.append((d / span, xs[i - 1], xs[i], d))
    # CLIFFS: the five biggest single drops by amount lost (filter first, then take the top 5)
    big = sorted((t for t in drops if t[3] > 0.8), key=lambda t: t[3], reverse=True)[:5]
    cliffs = [{"from": round(a1, 2), "to": round(b1, 2), "lost": round(d, 2),
               "at_seconds": round(at(a1), 1) if (not pct_axis or dur) else None}
              for _, a1, b1, d in big]
    cliff_set = {(a1, b1) for _, a1, b1, _ in big}
    # SLIDE: net loss over the time it took, after the hook, leaving out the cliffs
    mid = [(d, x1 - x0) for _, x0, x1, d in drops if x0 > cutoff and (x0, x1) not in cliff_set]
    tot_span = sum(s for _, s in mid)
    slide = sum(d for d, _ in mid) / tot_span if tot_span > 0 else 0
    said = {}
    if tr and os.path.exists(tr):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "yt-edit"))
        from deadair import load as load_cues
        cues = load_cues(tr)
        for c in cliffs:
            if c["at_seconds"] is None: continue
            t = c["at_seconds"]
            near = [q[2] for q in cues if q[0] <= t + 4 and q[1] >= t - 4]
            said[str(c["from"])] = " ".join(near)[:140]
    out = {"points": len(rows), "start": start, "hook_leak": round(hook_leak, 2),
           "end": ys[-1], "axis": "pct" if pct_axis else "seconds", "cliffs": cliffs, "slide_per_unit": round(slide, 3), "said": said}
    if as_json: print(json.dumps(out, indent=1)); return
    print(f"\n  {files[0]}   {len(rows)} points   {ys[0]:.1f}% -> {ys[-1]:.1f}%\n")
    verdict = "healthy" if hook_leak < 25 else "leaking" if hook_leak < 40 else "severe"
    print(f"  HOOK LEAK   {hook_leak:.1f}% lost in the opening   [{verdict}]")
    print(f"              under 25 is healthy for this length. Fix the first line before anything else.\n")
    print("  CLIFFS      the moments people actually left")
    for c in cliffs:
        where = f"{c['at_seconds']:.0f}s" if c["at_seconds"] is not None else f"{c['from']}"
        print(f"    -{c['lost']:5.1f}%  at {where:>8}" + (f"   \"{said.get(str(c['from']),'')}\"" if said else ""))
    if not cliffs: print("    none steeper than 0.8% - the loss is all slide, not moments")
    print(f"\n  SLIDE       {slide:.3f}% per unit across the middle")
    print( "              a flat slide is pacing, not content. Cut the middle, do not rewrite it.\n")

if __name__ == "__main__":
    main()
