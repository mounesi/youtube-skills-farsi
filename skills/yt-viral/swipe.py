#!/usr/bin/env python3
"""swipe.py - rank collected videos by how far each beat its OWN channel, then name the formula.

    python3 swipe.py collected.json
    python3 swipe.py collected.json --min 2.0 --json

Input is a list you collected - one object per video:

    [{"channel":"Some Channel","title":"...","views":412000,"url":"...","duration":613}, ...]

{"videos": [...]} and `yt-dlp --flat-playlist -J` output ("entries", "view_count") are read as-is.
Videos with no view count are skipped, not counted as 0.

Raw view counts rank channel size, not ideas. A 400k video on a 2M-subscriber channel is a normal
Tuesday; a 400k video on a channel whose median is 30k is the thing worth studying. So every video
is scored as a MULTIPLE OF ITS OWN CHANNEL'S MEDIAN, which needs at least four videos per channel
to mean anything - the tool says so rather than quietly ranking on noise.

The formula comes from skills/yt-script/hooks.json, matched against the TITLE. It is a judgement
about the words on screen, not a claim about why the video worked.
"""
import argparse, json, os, re, statistics, sys

HERE = os.path.dirname(os.path.abspath(__file__))
FORMULAS = json.load(open(os.path.join(HERE, "..", "yt-script", "hooks.json")))["hooks"]

def classify(title):
    # Same tie-break as yt-script/hookscore.py: most matching patterns wins, and on a tie the
    # formula listed first in hooks.json wins.
    title = title or ""
    best, hits = None, 0
    for f in FORMULAS:
        n = sum(1 for p in f["match"] if re.search(p, title, re.I))
        if n > hits: best, hits = f, n
    return best["name"] if best else "Unclassified"

def _views(v):
    """A view count as a float, or None when it is missing/unknown (live, upcoming, premiere)."""
    x = v.get("views")
    if x is None or str(x).strip() == "": return None
    try:
        n = float(str(x).replace(",", "").strip())
    except ValueError:
        return None
    return n if n >= 0 else None

def _flatten(node, parent_ch=None):
    """Accept a plain list, {"videos": [...]}, or yt-dlp -J output (playlist with "entries")."""
    if isinstance(node, list):
        for x in node:
            yield from _flatten(x, parent_ch)
        return
    if not isinstance(node, dict):
        return
    ch = node.get("channel") or node.get("uploader") or parent_ch
    kids = node.get("videos") if node.get("videos") is not None else node.get("entries")
    if kids is not None and (node.get("_type") == "playlist" or "videos" in node or "entries" in node):
        yield from _flatten(kids, ch or node.get("title"))
        return
    v = dict(node)
    if not v.get("channel"): v["channel"] = ch or "?"
    if v.get("views") is None: v["views"] = v.get("view_count")
    v["url"] = v.get("url") or v.get("webpage_url") or ""
    yield v

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file")
    p.add_argument("--min", type=float, default=1.5)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    as_json, lo = args.json, args.min
    if not os.path.exists(args.file): print(__doc__); sys.exit(1)
    with open(args.file) as fh:
        rows = list(_flatten(json.load(fh)))
    if not rows or not any(_views(v) for v in rows):
        print(f"swipe.py: no videos with a view count found in {args.file} - expected a list of "
              "{channel, title, views}, {\"videos\": [...]}, or yt-dlp -J output", file=sys.stderr)
        sys.exit(2)
    by, unknown = {}, 0
    for r in rows:
        n = _views(r)
        if n is None:
            unknown += 1
            continue
        by.setdefault(str(r.get("channel") or "?"), []).append((r, n))
    out, thin = [], []
    for ch, vids in by.items():
        views = [n for _, n in vids]
        med = statistics.median(views) if views else 0
        if len(vids) < 4:
            thin.append((ch, len(vids)))
            continue
        for v, n in vids:
            m = (n / med) if med else 0
            title = v.get("title") or ""
            out.append({"channel": ch, "title": title, "views": int(n),
                        "median": int(med), "multiple": round(m, 2),
                        "formula": classify(title), "url": v.get("url") or ""})
    out = [r for r in out if r["multiple"] >= lo]
    out.sort(key=lambda r: -r["multiple"])
    if as_json:
        print(json.dumps({"outliers": out, "skipped_thin_channels": thin,
                          "skipped_unknown_views": unknown}, indent=1)); return
    print(f"\n  {len(rows)} videos across {len(by)} channels, outliers at {lo}x or better\n")
    for r in out[:25]:
        print(f"    {r['multiple']:5.2f}x  {r['views']:>9,}  vs {r['median']:>9,} median   {r['channel'][:22]:<22} {r['title'][:52]}")
        print(f"            {r['formula']}")
    if not out: print("    nothing cleared the threshold - collect more per channel or lower --min")
    if thin:
        print(f"\n  skipped {len(thin)} channel(s) with under 4 videos collected - a median off one or")
        print( "  two videos is not a median: " + ", ".join(f"{c} ({n})" for c, n in thin[:6]))
    if unknown:
        print(f"\n  skipped {unknown} video(s) with no view count (live, upcoming or premiere) - not counted as 0")
    counts = {}
    for r in out: counts[r["formula"]] = counts.get(r["formula"], 0) + 1
    if counts:
        print("\n  formulas among the outliers")
        for f, n in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"    {n:2d}x  {f}")
    print()

if __name__ == "__main__":
    main()
