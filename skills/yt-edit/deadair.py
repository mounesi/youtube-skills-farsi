#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""deadair.py - فهرست برش (EDL) از روی رونوشت زمان‌دار؛ فارسی و انگلیسی.

    python3 -I deadair.py take.srt                         # srt، vtt یا json ویسپر
    python3 -I deadair.py take.json --json                 # خروجی ماشینی
    python3 -I deadair.py take.json --mode learning        # ویدیوی آموزشی: همه‌چیز بُریده، مکث‌ها ۰٫۲ ثانیه
    python3 -I deadair.py take.json --edl take.edl --markers take-markers.csv --fps 30

سه چیز پیدا می‌کند:
  سکوت      (DEAD)    مکث بین حرف‌ها که از آستانه بلندتر است
  پرکننده   (FILLER)  «اِ»، «اممم»، «خب»، «یعنی»، um، you know و… (تکه‌ی کامل یا کلمه‌ی تنها)
  تکرار     (REPEAT)  جمله یا چند کلمه‌ای که از اول گفته شده («تو کلاد بخش… تو کلاد بخش»)؛
                      برداشت اولِ نیمه‌کاره بریده می‌شود، برداشت آخر می‌ماند.

دو حالت:
  --mode suggest   (پیش‌فرض) هیچ‌چیز حذف نمی‌شود؛ بازه‌ها پیشنهاد برش‌اند و روی تایم‌لاین کامل علامت می‌خورند.
                   مکث‌های بلندتر از --floor (پیش‌فرض ۰٫۴۵) از وسط کوتاه می‌شوند.
  --mode learning  برای ویدیوی آموزشی: هر پرکننده و تکرار بریده می‌شود و همه‌ی مکث‌ها به --keep
                   (پیش‌فرض ۰٫۲ ثانیه) می‌رسند (جامپ‌کات).

خروجی‌ها:
  --edl FILE       EDL از نوع CMX3600 برای DaVinci Resolve.
                   پیشنهادی: مارکرها روی تایم‌لاین کامل (در Media Pool راست‌کلیک روی تایم‌لاین:
                   Timelines > Import > Timeline Markers from EDL).
                   آموزشی: فهرست تکه‌های ماندنی (File > Import > Timeline… با همان کلیپ).
  --markers FILE   فهرست مارکر: name, timecode, duration, note (CSV)؛ اگر پسوند .edl باشد، EDL مارکر.
                   پیشنهادی: بازه‌ها روی تایم‌لاین کامل. آموزشی: جای هر جامپ‌کات روی تایم‌لاین بریده.
  --fps N          نرخ فریم (پیش‌فرض ۳۰؛ 23.976 و 29.97 هم، بدون drop-frame)

هیچ‌وقت وسط کلمه نمی‌بُرد: لبه‌ی هر برش به مرز کلمه/تکه چسبانده می‌شود و در EDL به سمت داخلِ
سکوت گرد می‌شود. به فایل ویدیو دست نمی‌زند؛ فقط فهرست می‌دهد و شما در ادیتور اعمالش می‌کنید.

بر پایه‌ی deadair.py در youtube-agent-skill اثر Jake Schincariol (مجوز MIT)، با اصلاح باگ‌هایش.
"""
import argparse
import csv
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fatext as fa  # noqa: E402  (shared Persian text library, copied into this folder)

LABELS = {"DEAD": "سکوت", "FILLER": "پرکننده", "REPEAT": "تکرار"}
COLORS = {"DEAD": "Blue", "FILLER": "Yellow", "REPEAT": "Red"}
MODES = {"suggest": "پیشنهادی (هیچ‌چیز حذف نمی‌شود)", "learning": "آموزشی (همه‌ی پرکننده‌ها و تکرارها بریده، مکث‌ها کوتاه)"}

_PUNCT_END = tuple("،,.!?؟…;؛:")
# hesitation sounds that are never a real word: removed wherever they stand (word level)
_SURE = frozenset(fa.fold(w) for w in ("ا", "اه", "اوم", "اهم", "اوهوم", "هوم", "مم", "ممم", "ااا", "اممم",
                                       "um", "umm", "uh", "uhh", "erm", "er", "ah", "hmm", "mm"))
# fillers that are more often a real answer than a filler: never removed word by word
_NOT_WORD_FILLER = frozenset(fa.fold(w) for w in ("بله", "باشه"))
# Persian/English reduplication that is meaning, not a stutter («کم کم»، «خیلی خیلی»)
_REDUP_OK = frozenset(fa.fold(w) for w in (
    "کم", "آروم", "یواش", "تند", "ذره", "دونه", "تیکه", "جدا", "کنار", "خرده", "قطره", "لحظه", "رنگ",
    "جور", "گروه", "دسته", "خیلی", "نه", "آره", "بله", "باشه", "هی", "بدو", "very", "no", "yes", "bye",
    "so", "really", "ha", "ها"))
_STANDALONE_GAP = 0.3   # a pause this long on a side counts as a boundary for a standalone filler
_CONTEXT = 3.0          # seconds of kept speech shown before each cut ("check the last 3 s")


# ---------------------------------------------------------------- compatibility helpers
# chapters.py / retention.py used to import these; kept so old copies of those tools still work.

def parse_ts(s):
    """تایم‌کد → ثانیه؛ ورودی بد ValueError می‌دهد (مثل نسخه‌ی قدیمی)."""
    t = fa.parse_timestamp(s)
    if t is None:
        raise ValueError("bad timestamp %r" % (s,))
    return t


def clean(text):
    return fa.clean_cue_text(text)


def load(path, words=False):
    """رونوشت را می‌خواند (fatext.load_cues): فهرست مرتب Cue(start, end, text)."""
    return fa.load_cues(path, words=words)


def norm(text):
    return fa.norm_words(text)


def merge(cuts):
    out = []
    for c in sorted(cuts, key=lambda c: c["start"]):
        if out and c["start"] <= out[-1][1]:
            out[-1][1] = max(out[-1][1], c["end"])
        else:
            out.append([c["start"], c["end"]])
    return out


# ---------------------------------------------------------------- numbers / timecode

def fan(x, fmt="{:.1f}"):
    """a number for Persian prose: Persian digits, ٫ as decimal point"""
    return fa.to_fa_digits(fmt.format(x), separators=True)


def frames_to_tc(frames, base):
    frames = max(0, int(frames))
    f = frames % base
    s = frames // base
    return "%02d:%02d:%02d:%02d" % (s // 3600, (s // 60) % 60, s % 60, f)


def tc_to_frames(tc, base):
    p = fa.to_ascii_digits(tc.strip()).replace(";", ":").split(":")
    if len(p) != 4 or not all(x.isdigit() for x in p):
        raise ValueError(tc)
    h, m, s, f = (int(x) for x in p)
    if m > 59 or s > 59 or f >= base:
        raise ValueError(tc)
    return ((h * 60 + m) * 60 + s) * base + f


# ---------------------------------------------------------------- units

class Unit(object):
    """one timed piece of speech: a word (whisper word timings) or a whole cue"""
    __slots__ = ("start", "end", "text", "seg", "toks", "removed", "kind", "why")

    def __init__(self, start, end, text, seg):
        self.start, self.end, self.text, self.seg = start, end, text, seg
        self.toks = fa.norm_words(text)
        self.removed, self.kind, self.why = False, None, ""


def build_units(path, use_words):
    """segments (sentences) and units (words when the json has word timings, else the cues)"""
    segs = fa.load_cues(path)
    if not use_words or not segs:
        return segs, [Unit(s, e, t, i) for i, (s, e, t) in enumerate(segs)], False
    wcues = fa.load_cues(path, words=True)
    if len(wcues) <= len(segs):
        return segs, [Unit(s, e, t, i) for i, (s, e, t) in enumerate(segs)], False
    units, j = [], 0
    for s, e, t in wcues:
        while j + 1 < len(segs) and segs[j + 1][0] <= s + 0.01:
            j += 1
        units.append(Unit(s, e, t, j))
    return segs, units, True


def _ends_punct(text):
    return text.rstrip().endswith(_PUNCT_END)


def _sure_hes(text, toks):
    if len(toks) != 1:
        return False
    f = toks[0]
    if f in _SURE or ("ِ" in text and fa.is_filler(f)):  # «اِ»، «اِم» written with kasra
        return True
    # drawn out: اِاِاِ، اممم، ااام، ummm (few distinct letters, three or more long)
    return fa.is_filler(f) and len(f) >= 3 and len(set(f)) <= 2


def _phrases():
    out = set()
    for p in fa.FILLER_PHRASES_FA + fa.FILLER_PHRASES_EN:
        t = tuple(fa.norm_words(p))
        if len(t) > 1:
            out.add(t)
    return sorted(out, key=lambda p: -len(p))


def mark(u, kind, why):
    if not u.removed:
        u.removed, u.kind, u.why = True, kind, why


def find_segment_level(segs, units):
    """upstream rules on whole cues: filler-only cues, and the aborted first take of a restart"""
    by_seg = {}
    for u in units:
        by_seg.setdefault(u.seg, []).append(u)
    filler = [fa.is_filler_only(t) for _, _, t in segs]
    for i, (s, e, t) in enumerate(segs):
        if filler[i]:
            for u in by_seg.get(i, []):
                mark(u, "FILLER", "«%s»" % t.strip()[:40])
            continue
        if not t.strip():
            continue
        # A restart is compared against the last cue that was actually SPEECH: most retakes have an
        # «اِ» / "um" between the two attempts.
        j = i - 1
        while j >= 0 and (filler[j] or not segs[j][2].strip()):
            j -= 1
        if j < 0:
            continue
        a1, b1 = fa.norm_words(segs[j][2]), fa.norm_words(t)
        n = min(len(a1), 5)
        # The earlier take is the aborted one: it may be shorter, the later one may not.
        if n >= 3 and len(b1) >= n and a1[:n] == b1[:n]:
            for u in by_seg.get(j, []):
                mark(u, "REPEAT", "شروع دوباره: «%s»" % " ".join(fa.tokenize(segs[j][2])[:n]))


def find_word_level(units):
    """with word timings: standalone fillers inside a sentence, then stutters and short restarts"""
    phrases = _phrases()
    n = len(units)

    def boundary_before(i):
        return (i == 0 or units[i - 1].seg != units[i].seg or _ends_punct(units[i - 1].text)
                or units[i].start - units[i - 1].end >= _STANDALONE_GAP)

    def boundary_after(i):
        return (i == n - 1 or units[i + 1].seg != units[i].seg or _ends_punct(units[i].text)
                or units[i + 1].start - units[i].end >= _STANDALONE_GAP)

    i = 0
    while i < n:
        u = units[i]
        if u.removed or not u.toks:
            i += 1
            continue
        if _sure_hes(u.text, u.toks):
            mark(u, "FILLER", "«%s»" % u.text.strip())
            i += 1
            continue
        hit = 0
        for ph in phrases:
            k = len(ph)
            grp = units[i:i + k]
            if len(grp) == k and all(len(g.toks) == 1 and not g.removed for g in grp) \
                    and tuple(g.toks[0] for g in grp) == ph and boundary_before(i) and boundary_after(i + k - 1):
                hit = k
                break
        if hit:
            txt = " ".join(g.text.strip() for g in units[i:i + hit])
            for g in units[i:i + hit]:
                mark(g, "FILLER", "«%s»" % txt)
            i += hit
            continue
        if len(u.toks) == 1 and fa.is_filler(u.toks[0]) and u.toks[0] not in _NOT_WORD_FILLER \
                and boundary_before(i) and boundary_after(i):
            mark(u, "FILLER", "«%s» (تنها)" % u.text.strip())
        i += 1

    # stutters / restarts on what is left: «تو کلاد بخش تو کلاد بخش» → the first copy goes
    live = [u for u in units if not u.removed and u.toks]
    toks = [" ".join(u.toks) for u in live]
    i = 0
    while i < len(live):
        done = False
        for k in range(min(6, (len(live) - i) // 2), 0, -1):
            a, b = toks[i:i + k], toks[i + k:i + 2 * k]
            same = a == b
            if not same and k >= 2:  # the restart's last word was cut off: «بخش پرو… بخش پروژه»
                same = (a[:-1] == b[:-1] and len(a[-1]) >= 2 and b[-1].startswith(a[-1])
                        and live[i + k - 1].seg == live[i].seg)
            if not same:
                continue
            if k == 1 and (a[0] in _REDUP_OK or a[0].isdigit()):
                continue
            words = " ".join(x.text.strip() for x in live[i:i + k])
            why = ("تکرار «%s»" if k == 1 else "شروع دوباره: «%s»") % words
            for x in live[i:i + k]:
                mark(x, "REPEAT", why)
            i += k
            done = True
            break
        if not done:
            i += 1


def removed_runs(units):
    """consecutive removed units with the same reason → one cut each"""
    runs, cur = [], None
    for u in sorted(units, key=lambda u: (u.start, u.end)):
        if u.removed and cur is not None and cur["kind"] == u.kind and cur["why"] == u.why:
            cur["end"] = max(cur["end"], u.end)
            continue
        if cur is not None:
            runs.append(cur)
            cur = None
        if u.removed:
            cur = {"kind": u.kind, "start": u.start, "end": u.end, "why": u.why}
    if cur is not None:
        runs.append(cur)
    return runs


def snap(cut, kept):
    """never cut into a kept word/cue: pull each edge out of any kept unit it lands in"""
    a, b = cut["start"], cut["end"]
    for k in kept:
        if k.start < a < k.end:
            a = k.end
        if k.start < b < k.end:
            b = k.start
    cut["start"], cut["end"] = round(a, 3), round(b, 3)
    return cut


def find_pauses(units, mode, floor, keep):
    cuts = []
    order = sorted(units, key=lambda u: (u.start, u.end))
    if mode == "suggest":
        # upstream rule: every gap above the floor, trimmed from the MIDDLE so both sides keep a breath
        hi = None
        for u in order:
            if hi is not None:
                gap = u.start - hi
                if gap > floor:
                    cuts.append({"kind": "DEAD", "start": round(hi + floor / 2, 3),
                                 "end": round(u.start - floor / 2, 3),
                                 "why": "مکث %s ثانیه" % fan(gap, "{:.2f}")})
            hi = u.end if hi is None else max(hi, u.end)
        return cuts
    # learning: every pause between KEPT speech becomes `keep` seconds (removed speech counts as gone)
    kept = [u for u in order if not u.removed]
    if kept and kept[0].start > keep / 2:
        cuts.append({"kind": "DEAD", "start": 0.0, "end": round(kept[0].start - keep / 2, 3),
                     "why": "سکوت اول کار"})
    hi = None
    gone = 0.0  # removed speech between the last kept unit and this one
    for u in order:
        if u.removed:
            if hi is not None:
                gone += max(0.0, u.end - max(u.start, hi))
            continue
        if hi is not None:
            gap = u.start - hi
            silence = max(0.0, gap - gone)
            r = min(keep, silence)
            # a pause already short enough needs no DEAD cut (removed speech has its own cut)
            if silence > keep + 0.01 and gap - r > 0.01:
                cuts.append({"kind": "DEAD", "start": round(hi + r / 2, 3), "end": round(u.start - r / 2, 3),
                             "why": "مکث %s ← %s ثانیه" % (fan(silence, "{:.2f}"), fan(r, "{:.2f}"))})
        hi = u.end if hi is None else max(hi, u.end)
        gone = 0.0
    return cuts


def context_before(units, t):
    ws = [u.text.strip() for u in units if not u.removed and u.end <= t + 1e-6 and u.end >= t - _CONTEXT]
    s = " ".join(ws)
    return s[-60:]


def analyse(path, mode="suggest", floor=0.45, keep=0.2, use_words=True):
    segs, units, word_level = build_units(path, use_words)
    if not segs:
        return None
    find_segment_level(segs, units)
    if word_level:
        find_word_level(units)
    kept = [u for u in units if not u.removed]
    cuts = []
    for c in removed_runs(units):
        c["level"] = "word" if word_level else "cue"
        cuts.append(snap(c, kept))
    for c in find_pauses(units, mode, floor, keep):
        c["level"] = "word" if word_level else "cue"
        cuts.append(snap(c, kept))
    cuts = [c for c in cuts if c["end"] > c["start"]]
    cuts.sort(key=lambda c: (c["start"], c["end"]))
    for c in cuts:
        c["label"] = LABELS[c["kind"]]
        c["before"] = context_before(units, c["start"])
    dur = fa.duration(segs)
    merged = merge(cuts)  # overlapping cuts remove the same seconds once
    removed = sum(b - a for a, b in merged)
    return {"segs": segs, "units": units, "word_level": word_level, "cuts": cuts, "merged": merged,
            "removed": removed, "duration": dur, "out": max(0.0, dur - removed)}


# ---------------------------------------------------------------- frames, EDL, markers

class Clock(object):
    def __init__(self, fps, record_tc, source_tc):
        self.fps = fps
        self.base = int(round(fps))
        self.rec0 = tc_to_frames(record_tc, self.base)
        self.src0 = tc_to_frames(source_tc, self.base)

    def f_in(self, sec):   # cut start: round later, into the silence
        return int(math.ceil(sec * self.fps - 1e-6))

    def f_out(self, sec):  # cut end: round earlier, into the silence
        return int(math.floor(sec * self.fps + 1e-6))

    def f_near(self, sec):
        return int(round(sec * self.fps))

    def tc(self, frames, origin=0):
        return frames_to_tc(origin + frames, self.base)


def frame_cuts(rep, clock):
    """merged cuts in frames, rounded inward so no frame of kept speech is lost"""
    out = []
    for a, b in rep["merged"]:
        fa_, fb = clock.f_in(a), clock.f_out(b)
        if fb > fa_:
            if out and fa_ <= out[-1][1]:
                out[-1][1] = max(out[-1][1], fb)
            else:
                out.append([fa_, fb])
    return out


def kept_segments(rep, clock):
    total = int(math.ceil(rep["duration"] * clock.fps - 1e-6))
    segs, pos = [], 0
    for a, b in frame_cuts(rep, clock):
        if a > pos:
            segs.append([pos, min(a, total)])
        pos = max(pos, b)
    if pos < total:
        segs.append([pos, total])
    return [s for s in segs if s[1] > s[0]]


def _marker_name(c, latin):
    return c["kind"] if latin else c["label"]


def _one_line(s):
    return " ".join(str(s).replace("|", "/").split())


def suggest_markers(rep, clock, latin):
    """one marker per suggested cut, on the UNCUT timeline"""
    out = []
    for c in rep["cuts"]:
        f0 = clock.f_in(c["start"])
        f1 = max(f0 + 1, clock.f_out(c["end"]))
        note = c["why"] + (("  | قبلش: " + c["before"]) if c.get("before") else "")
        out.append({"name": _marker_name(c, latin), "frame": f0, "dur": f1 - f0, "note": note,
                    "short": c["why"], "color": COLORS[c["kind"]]})
    return out


def learning_markers(rep, clock, latin):
    """one marker per jump cut, on the EDITED timeline: where to check the cut"""
    segs = kept_segments(rep, clock)
    out, rec = [], 0
    for i, (a, b) in enumerate(segs):
        rec += b - a
        if i == len(segs) - 1:
            break
        nxt = segs[i + 1][0]
        inside = [c for c in rep["cuts"] if clock.f_near(c["start"]) < nxt and clock.f_near(c["end"]) > b]
        kinds = []
        for c in inside:
            if c["kind"] not in kinds:
                kinds.append(c["kind"])
        kinds = kinds or ["DEAD"]
        name = "+".join(k if latin else LABELS[k] for k in kinds)
        why = "؛ ".join(c["why"] for c in inside if c["kind"] != "DEAD") or (inside[0]["why"] if inside else "")
        sec = (nxt - b) / clock.fps
        note = "%s ثانیه بریده شد%s" % (fan(sec, "{:.2f}"), ("؛ " + why) if why else "")
        out.append({"name": name, "frame": rec, "dur": 1, "note": note, "short": note,
                    "color": COLORS["REPEAT" if "REPEAT" in kinds else "FILLER" if "FILLER" in kinds else "DEAD"]})
    return out


def write_marker_csv(path, markers, clock):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "timecode", "duration", "note", "color"])
        for m in markers:
            w.writerow([m["name"], clock.tc(m["frame"], clock.rec0), frames_to_tc(m["dur"], clock.base),
                        m["note"], m["color"]])


def write_marker_edl(path, markers, clock, title):
    """the marker EDL DaVinci Resolve itself exports and imports (Import > Timeline Markers from EDL)"""
    lines = ["TITLE: %s" % title, "FCM: NON-DROP FRAME", ""]
    for n, m in enumerate(markers, 1):
        a = clock.tc(m["frame"], clock.rec0)
        b = clock.tc(m["frame"] + 1, clock.rec0)
        lines.append("%03d  001      V     C        %s %s %s %s  " % (n, a, b, a, b))
        lines.append(" |C:ResolveColor%s |M:%s |D:%d" % (m["color"], _one_line(m["name"] + " - " + m["short"])[:100],
                                                       m["dur"]))
        lines.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def write_cut_edl(path, rep, clock, title, clip):
    """CMX3600 cut list of the KEPT pieces (learning mode): one V and one AA event per piece"""
    lines = ["TITLE: %s" % title, "FCM: NON-DROP FRAME", ""]
    rec, n = 0, 0
    for a, b in kept_segments(rep, clock):
        s_in, s_out = clock.tc(a, clock.src0), clock.tc(b, clock.src0)
        r_in, r_out = clock.tc(rec, clock.rec0), clock.tc(rec + b - a, clock.rec0)
        for track in ("V", "AA"):
            n += 1
            lines.append("%03d  AX       %-5s C        %s %s %s %s" % (n, track, s_in, s_out, r_in, r_out))
            lines.append("* FROM CLIP NAME: %s" % clip)
        lines.append("")
        rec += b - a
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------- CLI

def _positive_fps(v):
    x = fa.parse_number(v)
    if x is None or x <= 0 or x > 240:
        raise argparse.ArgumentTypeError("نرخ فریم باید عددی بین ۰ و ۲۴۰ باشد: %r" % v)
    return x


def _seconds(v):
    x = fa.parse_number(v)
    if x is None:
        raise argparse.ArgumentTypeError("عدد نیست: %r" % v)
    return x


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # Farsi first line, argparse detail after; exit 2 like argparse
        self.print_usage(sys.stderr)
        sys.stderr.write("خطا در ورودی: %s\n" % message)
        sys.exit(2)


def main():
    ap = _Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", help="رونوشت: .srt، .vtt یا .json ویسپر")
    ap.add_argument("--mode", choices=("suggest", "learning"), default="suggest",
                    help="suggest = فقط پیشنهاد (پیش‌فرض)، learning = برش کامل برای ویدیوی آموزشی")
    ap.add_argument("--floor", type=_seconds, default=0.45, help="حالت پیشنهادی: مکث بلندتر از این (ثانیه)")
    ap.add_argument("--keep", type=_seconds, default=0.2, help="حالت آموزشی: طول هر مکث بعد از برش (ثانیه)")
    ap.add_argument("--json", action="store_true", help="خروجی JSON")
    ap.add_argument("--no-words", action="store_true", help="زمان‌بندی کلمه‌ها را نادیده بگیر (فقط تکه‌ها)")
    ap.add_argument("--edl", metavar="FILE", help="نوشتن EDL برای DaVinci Resolve")
    ap.add_argument("--markers", metavar="FILE", help="نوشتن فهرست مارکر (.csv یا .edl)")
    ap.add_argument("--fps", type=_positive_fps, default=30.0, help="نرخ فریم تایم‌لاین (پیش‌فرض ۳۰)")
    ap.add_argument("--clip", help="نام فایل ویدیو برای EDL برش (پیش‌فرض: نام رونوشت + .mov)")
    ap.add_argument("--record-tc", default="01:00:00:00", help="تایم‌کد شروع تایم‌لاین در Resolve")
    ap.add_argument("--source-tc", default="00:00:00:00", help="تایم‌کد شروع خود کلیپ")
    ap.add_argument("--latin-labels", action="store_true",
                    help="نام مارکرها DEAD/FILLER/REPEAT به‌جای فارسی (اگر Resolve حروف فارسی را نشان نداد)")
    args = ap.parse_args()
    if args.floor < 0:
        ap.error("--floor باید صفر یا بیشتر باشد (floor must be 0 or more)")
    if args.keep < 0:
        ap.error("--keep باید صفر یا بیشتر باشد")
    try:
        clock = Clock(args.fps, args.record_tc, args.source_tc)
    except ValueError:
        ap.error("تایم‌کد باید به شکل HH:MM:SS:FF باشد")
    if not args.path or not os.path.isfile(args.path):
        if args.path:
            sys.stderr.write("فایل پیدا نشد: %s\n" % args.path)
        print(__doc__)
        sys.exit(1)
    src = args.path
    try:
        rep = analyse(src, args.mode, args.floor, args.keep, use_words=not args.no_words)
    except OSError as e:
        sys.stderr.write("فایل خوانده نشد: %s\n" % e)
        sys.exit(1)
    if rep is None:
        print("هیچ تکه‌ی زمان‌داری پیدا نشد؛ این فایل srt، vtt یا json ویسپر است؟")
        sys.exit(1)
    dur, removed, out = rep["duration"], rep["removed"], rep["out"]
    pct = removed / dur * 100 if dur > 0 else 0.0
    title = os.path.splitext(os.path.basename(src))[0]
    clip = args.clip or (title + ".mov")
    written = []
    if args.edl:
        if args.mode == "learning":
            write_cut_edl(args.edl, rep, clock, title, clip)
        else:
            write_marker_edl(args.edl, suggest_markers(rep, clock, args.latin_labels), clock, title)
        written.append(args.edl)
    if args.markers:
        mk = (learning_markers if args.mode == "learning" else suggest_markers)(rep, clock, args.latin_labels)
        if args.markers.lower().endswith(".edl"):
            write_marker_edl(args.markers, mk, clock, title)
        else:
            write_marker_csv(args.markers, mk, clock)
        written.append(args.markers)

    cuts = [{k: c[k] for k in ("kind", "label", "start", "end", "why", "level", "before")} for c in rep["cuts"]]
    for c in cuts:
        c["tc_in"] = clock.tc(clock.f_in(c["start"]), clock.src0)
        c["tc_out"] = clock.tc(clock.f_out(c["end"]), clock.src0)
    if args.json:
        doc = {"source": src, "mode": args.mode, "duration": dur, "fps": args.fps,
               "word_level": rep["word_level"], "cuts": cuts,
               "merged": [[round(a, 3), round(b, 3)] for a, b in rep["merged"]],
               "removed": round(removed, 3), "out": round(out, 3), "written": written}
        if args.mode == "learning":
            doc["keep"] = [[round(a / clock.fps, 3), round(b / clock.fps, 3)] for a, b in kept_segments(rep, clock)]
        print(json.dumps(doc, ensure_ascii=False, indent=1))
        return

    level = "کلمه‌به‌کلمه (زمان‌بندی ویسپر)" if rep["word_level"] else "تکه‌به‌تکه"
    if args.mode == "learning":
        rule = "مکث‌ها ← %s ثانیه" % fan(args.keep, "{:g}")
    else:
        rule = "آستانه‌ی سکوت %s ثانیه" % fan(args.floor, "{:g}")
    pieces = "%s تکه" % fan(len(rep["segs"]), "{:d}")
    if rep["word_level"]:
        pieces += " و %s کلمه" % fan(len(rep["units"]), "{:d}")
    print("\n  %s   %s ثانیه، %s، %s" % (src, fan(dur, "{:.2f}"), pieces, rule))
    print("  حالت: %s   بررسی: %s   نرخ فریم: %s\n" % (MODES[args.mode], level, fan(args.fps, "{:g}")))
    for c in cuts:
        print("    %-8s %s → %s   %7.2f → %7.2f   (%s ث)   %s" % (
            c["label"], c["tc_in"], c["tc_out"], c["start"], c["end"],
            fan(c["end"] - c["start"], "{:.2f}"), c["why"]))
        if c["before"]:
            print("             قبلش: …%s" % c["before"])
    counts = []
    for k in ("DEAD", "FILLER", "REPEAT"):
        n = sum(1 for c in cuts if c["kind"] == k)
        if n:
            counts.append("%s %s" % (LABELS[k], fan(n, "{:d}")))
    if args.mode == "suggest":
        head = "%s پیشنهاد برش (%s)؛ اگر همه را بپذیرید" % (fan(len(cuts), "{:d}"), "، ".join(counts) or "هیچ")
    else:
        head = "%s برش (%s):" % (fan(len(cuts), "{:d}"), "، ".join(counts) or "هیچ")
    print("\n  %s %s ثانیه کم می‌شود و %s ثانیه می‌ماند (%s٪ کوتاه‌تر)" % (
        head, fan(removed, "{:.2f}"), fan(out, "{:.2f}"), fan(pct)))
    if args.mode == "learning":
        print("  %s تکه‌ی ماندنی، یعنی %s جامپ‌کات" % (
            fan(len(kept_segments(rep, clock)), "{:d}"), fan(max(0, len(kept_segments(rep, clock)) - 1), "{:d}")))
        if not rep["word_level"]:
            print("  فقط تکه‌به‌تکه بررسی شد؛ برای برش کلمه‌به‌کلمه (پرکننده و تکرار وسط جمله)، JSON ویسپر با"
                  " زمان‌بندی کلمه‌ها بدهید.")
    else:
        print("  هیچ‌چیز حذف نشده: این‌ها پیشنهادند، روی تایم‌لاین کامل علامتشان بزنید و خودتان تصمیم بگیرید.")
    for w in written:
        print("  نوشته شد: %s" % w)
    print("  قبل از هر برش، ۳ ثانیه‌ی آخرش را گوش کنید؛ عدد بالا فقط حرف‌ها را می‌شمارد، نه دموی بی‌صدا.\n")


if __name__ == "__main__":
    main()
