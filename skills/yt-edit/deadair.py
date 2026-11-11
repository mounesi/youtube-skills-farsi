#!/usr/bin/env python3
"""deadair.py - an edit decision list from a timestamped transcript.

    python3 deadair.py transcript.srt            # or .vtt, or whisper .json
    python3 deadair.py transcript.srt --floor 0.35 --json

Finds three things and prints the cuts as a list you can act on, newest problem first:
  DEAD    gaps between spoken cues longer than the floor
  FILLER  cues that are only filler ("um", "so yeah", "basically")
  REPEAT  a sentence restarted - the second take of the same opening

WHAT IT DOES NOT DO. It does not cut the file. It prints an EDL, the total it would remove, and the
runtime you would land on, and you apply it in whatever editor you use. Nothing here touches media.
"""
import argparse, json, os, re, sys

# Separators allowed around filler words: whitespace and the punctuation real captions put there
# ("Um?", "Uh…", "You know?", "(um)").
_SEP = "[\\s,.!?;:…'\"“”‘’()\\[\\]-]*"
FILLER_ONLY = re.compile(r"^" + _SEP + r"((um+|uh+|er+|ah+|so|okay|ok|right|yeah|like|anyway|basically|"
                         r"actually|you know|i mean|let me see|hold on)" + _SEP + r")+$", re.I)

# Markup inside cue text: HTML-ish tags (<i>, <c>, <00:00:01.000>) and SSA override blocks ({\an8}).
_TAGS = re.compile(r"<[^>]*>|\{[^}]*\}")
_ENTITIES = (("&nbsp;", " "), ("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&"))

# Rolling-caption snapshot cues (YouTube auto VTT) are ~10 ms long and only repeat the line above.
_MIN_VTT_CUE = 0.05


def parse_ts(s):
    s = s.strip().replace(",", ".")
    p = s.split(":")
    return int(p[0]) * 3600 + int(p[1]) * 60 + float(p[2]) if len(p) == 3 else int(p[0]) * 60 + float(p[1])


def clean(text):
    text = _TAGS.sub("", text)
    for k, v in _ENTITIES:
        text = text.replace(k, v)
    return text.strip()


def _load_json(d):
    segs = d if isinstance(d, list) else ((d.get("segments") or []) if isinstance(d, dict) else [])
    out = [(float(s["start"]), float(s["end"]), clean(s.get("text") or "")) for s in segs
           if isinstance(s, dict)]
    return [c for c in out if c[2]]


def load(path):
    raw = open(path, encoding="utf-8-sig", errors="replace").read()
    if path.lower().endswith(".json") or raw.lstrip().startswith(("{", "[")):
        try:
            return _load_json(json.loads(raw))
        except ValueError:
            pass  # not JSON after all - try it as srt / vtt
    is_vtt = raw.lstrip().startswith("WEBVTT")
    cues, cur = [], None
    for line in raw.splitlines():
        m = re.match(r"\s*(\d[\d:.,]+)\s*-->\s*(\d[\d:.,]+)", line)
        if m:
            cur = [parse_ts(m.group(1)), parse_ts(m.group(2)), []]
            cues.append(cur)
        elif not line.strip():
            # A blank line ends the cue, so cue ids, SRT index lines and NOTE / STYLE / REGION
            # blocks that follow are never glued onto it. A whitespace-only line straight after
            # the timing line (YouTube auto VTT puts one there) does not end it.
            if cur is not None and (cur[2] or line == ""):
                cur = None
        elif cur is not None:
            t = clean(line)
            if t:
                cur[2].append(t)
    if is_vtt:
        kept, last = [], None
        for a, b, t in cues:
            if b - a < _MIN_VTT_CUE:
                continue
            while t and last is not None and t[0] == last:
                t = t[1:]
            if t:
                kept.append((a, b, t))
                last = t[-1]
        cues = kept
    return [(a, b, " ".join(t)) for a, b, t in cues if t]


def norm(t): return re.sub(r"[^a-z0-9 ]", "", t.lower()).split()


def merge(cuts):
    out = []
    for c in sorted(cuts, key=lambda c: c["start"]):
        if out and c["start"] <= out[-1][1]:
            out[-1][1] = max(out[-1][1], c["end"])
        else:
            out.append([c["start"], c["end"]])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?")
    ap.add_argument("--floor", type=float, default=0.45)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.floor < 0:
        ap.error("--floor must be 0 or more")
    floor, as_json = args.floor, args.json
    if not args.path or not os.path.exists(args.path): print(__doc__); sys.exit(1)
    src = args.path
    cues = load(src)
    if not cues: print("no cues found - is this an srt, vtt or whisper json?"); sys.exit(1)
    cues.sort(key=lambda c: (c[0], c[1]))
    dur = max(e for _, e, _ in cues)
    cuts = []
    hi = cues[0][1]  # latest end of any cue so far
    for i, (s, e, t) in enumerate(cues):
        if FILLER_ONLY.match(t):
            cuts.append({"kind": "FILLER", "start": s, "end": e, "why": t.strip()[:48]})
        if i:
            gap = s - hi
            if gap > floor:
                keep = floor / 2
                cuts.append({"kind": "DEAD", "start": round(hi + keep, 3),
                             "end": round(s - keep, 3), "why": f"{gap:.2f}s gap"})
        # A restart is compared against the last cue that was actually SPEECH. Comparing against
        # the literal previous cue misses every retake with an "um" between the two attempts, which
        # is most of them.
        if t.strip() and not FILLER_ONLY.match(t):
            j = i - 1
            while j >= 0 and (FILLER_ONLY.match(cues[j][2]) or not cues[j][2].strip()): j -= 1
            if j >= 0:
                a1, b1 = norm(cues[j][2]), norm(t)
                n = min(len(a1), 5)
                # The earlier take is the aborted one: it may be shorter, the later one may not.
                if n >= 3 and len(b1) >= n and a1[:n] == b1[:n]:
                    cuts.append({"kind": "REPEAT", "start": cues[j][0], "end": cues[j][1],
                                 "why": f'restart of "{" ".join(a1[:n])}"'})
        hi = max(hi, e)
    cuts = [c for c in cuts if c["end"] > c["start"]]
    cuts.sort(key=lambda c: c["start"])
    merged = merge(cuts)  # overlapping cuts remove the same seconds once
    removed = sum(b - a for a, b in merged)
    out = max(0.0, dur - removed)
    pct = removed / dur * 100 if dur > 0 else 0.0
    if as_json:
        print(json.dumps({"source": src, "duration": dur, "cuts": cuts,
                          "merged": [[round(a, 3), round(b, 3)] for a, b in merged],
                          "removed": round(removed, 3), "out": round(out, 3)}, indent=1)); return
    print(f"\n  {src}   {dur:.2f}s in, {len(cues)} cues, dead-air floor {floor}s\n")
    for c in cuts:
        print(f"    {c['kind']:<7} {c['start']:8.2f} -> {c['end']:8.2f}   {c['end']-c['start']:5.2f}s   {c['why']}")
    print(f"\n  {len(cuts)} cuts, {removed:.2f}s removed, {out:.2f}s out "
          f"({pct:.1f}% shorter)\n")


if __name__ == "__main__":
    main()
