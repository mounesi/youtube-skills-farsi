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
سکوت گرد می‌شود. به فایل ویدیو دست نمی‌زند؛ فقط فهرست می‌دهد و خودت در ادیتور اعمالش می‌کنی.

بر پایه‌ی deadair.py در youtube-agent-skill اثر Jake Schincariol (مجوز MIT)، با اصلاح باگ‌هایش.
"""
import argparse
import bisect
import csv
import errno
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
    "جور", "گروه", "دسته", "خیلی", "نه", "آره", "بله", "باشه", "هی", "بدو",
    # adverbial / distributive doublings: «یکی یکی»، «تک تک»، «رفته رفته»، «آهسته آهسته»، «دو دو»…
    "یکی", "تک", "رفته", "آهسته", "دو", "سه", "چند", "زود", "ریز", "گاه", "جا", "همه", "بیا", "برو",
    "پشت", "کم‌کم", "کم کم", "یه", "دم", "پله", "صف", "خونه", "شهر",
    "very", "no", "yes", "bye", "so", "really", "ha", "ها"))
# a lone «می»/«نمی» belongs to the next word, a lone plural/comparative suffix to the previous one, so
# «می خوام» and «می‌خوام» (or «فایل ها» and «فایل‌ها») compare as the same word. «ام»، «ای»، «است» stay
# apart: they are real standalone words (the vocative «ای»), and gluing them would invent repeats.
_GLUE_NEXT = frozenset(fa.fold(w) for w in ("می", "نمی"))
_GLUE_PREV = frozenset(fa.fold(w) for w in ("ها", "های", "هایی", "تر", "ترین", "ی"))
# a cue that ends like this is a finished sentence, never the aborted first take of a restart
_SENT_END = tuple(".!?؟")
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


def _compact_groups(toks):
    """folded tokens → [[token, [indices]]]: a lone «می»/«نمی» joins the next token, a lone suffix
    («ها»، «تر»، «ی»…) joins the previous one."""
    groups, pend = [], None
    for i, t in enumerate(toks):
        if pend is not None:
            groups.append([pend[0] + t, pend[1] + [i]])
            pend = None
            continue
        if t in _GLUE_PREV and groups:
            groups[-1][0] += t
            groups[-1][1].append(i)
            continue
        if t in _GLUE_NEXT:
            pend = (t, [i])
            continue
        groups.append([t, [i]])
    if pend is not None:
        groups.append([pend[0], pend[1]])
    return groups


def compact_words(toks):
    """«می خوام» and «می‌خوام» → the same token list (see _GLUE_NEXT / _GLUE_PREV)"""
    return [g[0] for g in _compact_groups(toks)]


def find_segment_level(segs, units):
    """upstream rules on whole cues: filler-only cues, and the aborted first take of a restart"""
    by_seg = {}
    for u in units:
        by_seg.setdefault(u.seg, []).append(u)
    # «بله.» / «باشه» on their own are usually a real answer, not a filler
    filler = [fa.is_filler_only(t) and not (set(fa.fold(w) for w in fa.norm_words(t)) & _NOT_WORD_FILLER)
              for _, _, t in segs]
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
        ga = _compact_groups(fa.norm_words(segs[j][2]))
        a1, b1 = [g[0] for g in ga], compact_words(fa.norm_words(t))
        la = len(a1)
        # Only an ABORTED first take: at least 3 words, no longer than the retake, a prefix of it except
        # a possibly cut-off last word («درباره‌ی پرامپت… درباره‌ی پرامپت‌نویسی»), and not a finished
        # sentence. Two complete parallel sentences («اگر روی این دکمه کلیک کنید …») are both kept.
        if la < 3 or la > len(b1) or segs[j][2].rstrip().endswith(_SENT_END) or a1[:-1] != b1[:la - 1]:
            continue
        last_a, last_b = a1[-1], b1[la - 1]
        if not (last_a == last_b or la > 5 or (len(last_a) >= 2 and last_b.startswith(last_a))):
            continue
        n = min(la, 5)
        shown = fa.tokenize(segs[j][2])[:ga[n - 1][1][-1] + 1]
        for u in by_seg.get(j, []):
            mark(u, "REPEAT", "شروع دوباره: «%s»" % " ".join(shown))


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

    # stutters / restarts on what is left: «تو کلاد بخش تو کلاد بخش» → the first copy goes.
    # Whisper often writes «می» as its own word: a lone «می»/«نمی» unit is grouped with the next unit
    # and a lone suffix unit with the previous one, so «می تونی» and «می‌تونی» compare equal.
    live, toks = [], []  # live[g] = the units of group g
    pend = None
    for u in units:
        if u.removed or not u.toks:
            continue
        key = " ".join(compact_words(u.toks))
        if pend is not None:
            live.append(pend[0] + [u])
            toks.append(pend[1] + key)
            pend = None
            continue
        if key in _GLUE_PREV and live:
            live[-1].append(u)
            toks[-1] += key
            continue
        if key in _GLUE_NEXT:
            pend = ([u], key)
            continue
        live.append([u])
        toks.append(key)
    if pend is not None:
        live.append(pend[0])
        toks.append(pend[1])
    i = 0
    while i < len(live):
        done = False
        for k in range(min(6, (len(live) - i) // 2), 0, -1):
            a, b = toks[i:i + k], toks[i + k:i + 2 * k]
            same = a == b
            if not same and k >= 2:  # the restart's last word was cut off: «بخش پرو… بخش پروژه»
                same = (a[:-1] == b[:-1] and len(a[-1]) >= 2 and b[-1].startswith(a[-1])
                        and live[i + k - 1][0].seg == live[i][0].seg)
            if not same:
                continue
            if k == 1 and (a[0] in _REDUP_OK or a[0].isdigit()):
                continue
            words = " ".join(x.text.strip() for g in live[i:i + k] for x in g)
            why = ("تکرار «%s»" if k == 1 else "شروع دوباره: «%s»") % words
            for g in live[i:i + k]:
                for x in g:
                    mark(x, "REPEAT", why)
            i += k
            done = True
            break
        if not done:
            i += 1


def removed_runs(units, mode="suggest"):
    """consecutive removed units with the same reason → one cut each.

    In learning mode only units that TOUCH are joined: the silence between two removed units is where
    the pause that stays (`keep`) may have to come from, so it must not be swallowed by a filler cut."""
    runs, cur = [], None
    for u in sorted(units, key=lambda u: (u.start, u.end)):
        if u.removed and cur is not None and cur["kind"] == u.kind and cur["why"] == u.why \
                and (mode != "learning" or u.start - cur["end"] < 0.01):
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


class _Spans(object):
    """kept speech as disjoint intervals (overlapping units merged), for bisect lookups"""

    def __init__(self, kept):
        out = []
        for k in sorted(kept, key=lambda u: (u.start, u.end)):
            if out and k.start < out[-1][1]:
                out[-1][1] = max(out[-1][1], k.end)
            else:
                out.append([k.start, k.end])
        self.starts = [a for a, _ in out]
        self.ends = [b for _, b in out]

    def inside(self, t):
        """index of the kept interval with start < t < end, or -1"""
        i = bisect.bisect_left(self.starts, t) - 1
        return i if i >= 0 and t < self.ends[i] else -1


def snap(cut, kept):
    """never cut into a kept word/cue: pull each edge out of any kept unit it lands in"""
    spans = kept if isinstance(kept, _Spans) else _Spans(kept)
    a, b = cut["start"], cut["end"]
    i = spans.inside(a)
    if i >= 0:
        a = spans.ends[i]
    i = spans.inside(b)
    if i >= 0:
        b = spans.starts[i]
    cut["start"], cut["end"] = round(a, 3), round(b, 3)
    return cut


def _silent_parts(lo, up, removed):
    """[lo, up] minus the spans of removed speech → the real silent intervals, in order"""
    spans = sorted((max(lo, r.start), min(up, r.end)) for r in removed if r.end > lo and r.start < up)
    out, pos = [], lo
    for a, b in spans:
        if a > pos:
            out.append([pos, a])
        pos = max(pos, b)
    if up > pos:
        out.append([pos, up])
    return out


def _tighten_gap(lo, up, removed, keep):
    """learning mode, one gap between two kept units: keep `keep` s of REAL silence (half right after
    the earlier word, half right before the later one, taken inward across removed speech when an
    interval is too short) and cut the rest of the silence. Removed speech has its own cuts."""
    silent = _silent_parts(lo, up, removed)
    silence = sum(b - a for a, b in silent)
    if silence <= keep + 0.01:
        return []
    r = min(keep, silence)
    keepers, need = [], r / 2
    for a, b in silent:
        take = min(need, b - a)
        if take > 0:
            keepers.append((a, a + take))
            need -= take
        if need <= 1e-9:
            break
    need = r / 2
    for a, b in reversed(silent):
        take = min(need, b - a)
        if take > 0:
            keepers.append((b - take, b))
            need -= take
        if need <= 1e-9:
            break
    keepers.sort()
    why = "مکث %s ← %s ثانیه" % (fan(silence, "{:.2f}"), fan(r, "{:.2f}"))
    cuts = []
    for a, b in silent:
        pos = a
        for ka, kb in keepers:
            if kb <= a or ka >= b:
                continue
            if ka - pos > 0.005:
                cuts.append({"kind": "DEAD", "start": round(pos, 3), "end": round(ka, 3), "why": why})
            pos = max(pos, kb)
        if b - pos > 0.005:
            cuts.append({"kind": "DEAD", "start": round(pos, 3), "end": round(b, 3), "why": why})
    return cuts


def _gaps(units):
    """(lo, up, removed units in between) for every pause between two KEPT units, in order"""
    hi, pending = None, []
    for u in sorted(units, key=lambda u: (u.start, u.end)):
        if u.removed:
            pending.append(u)
            continue
        if hi is not None and u.start > hi:
            yield hi, u.start, pending
        hi = u.end if hi is None else max(hi, u.end)
        pending = [p for p in pending if p.end > hi]


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
    # learning: every pause between KEPT speech becomes `keep` seconds of real silence
    kept = [u for u in order if not u.removed]
    if kept and kept[0].start > keep / 2:
        cuts.append({"kind": "DEAD", "start": 0.0, "end": round(kept[0].start - keep / 2, 3),
                     "why": "سکوت اول کار"})
    for lo, up, removed in _gaps(units):
        cuts.extend(_tighten_gap(lo, up, removed, keep))
    return cuts


def _covered(lo, up, cuts):
    """seconds of [lo, up] covered by the (sorted, possibly overlapping) cuts"""
    tot, pos = 0.0, lo
    for c in cuts:
        a, b = max(pos, c["start"]), min(up, c["end"])
        if b > a:
            tot += b - a
            pos = b
    return tot


def _ensure_breath(cuts, units, keep):
    """learning safety net: if a kept-to-kept pause ended up with less than min(keep, real silence) of
    silence (rounding, snapping), pull DEAD cut edges back into that silence."""
    cuts.sort(key=lambda c: (c["start"], c["end"]))
    starts = [c["start"] for c in cuts]
    pmax, m = [], float("-inf")
    for c in cuts:
        m = max(m, c["end"])
        pmax.append(m)
    for lo, up, removed in _gaps(units):
        silent = _silent_parts(lo, up, removed)
        real = sum(b - a for a, b in silent)
        target = min(keep, real)
        if target <= 0.01:
            continue
        i0 = bisect.bisect_right(pmax, lo)
        i1 = bisect.bisect_left(starts, up)
        near = cuts[i0:i1]
        kept_sil = sum((b - a) - _covered(a, b, near) for a, b in silent)
        deficit = target - kept_sil
        if deficit <= 0.01:
            continue
        for c in reversed(near):
            if c["kind"] != "DEAD" or deficit <= 1e-9:
                continue
            back = min(deficit, c["end"] - c["start"])
            c["end"] = round(c["end"] - back, 3)
            deficit -= back


def _coalesce(cuts):
    """learning: a filler/repeat run that was split only by silence which is cut anyway is shown as
    ONE cut again («تو کلاد بخش» = one REPEAT, not three plus the DEAD bits between its words)"""
    merged = merge(cuts)
    mstarts = [a for a, _ in merged]

    def one_piece(a, b):  # is [a, b] inside a single merged (fully cut) interval?
        i = bisect.bisect_right(mstarts, a + 1e-9) - 1
        return i >= 0 and b <= merged[i][1] + 1e-9

    joined, last = [], {}
    for c in cuts:
        if c["kind"] == "DEAD":
            joined.append(c)
            continue
        p = last.get("run")
        if p is not None and p["kind"] == c["kind"] and p["why"] == c["why"] and one_piece(p["end"], c["start"]):
            p["end"] = max(p["end"], c["end"])
            continue
        joined.append(c)
        last["run"] = c
    runs = [c for c in joined if c["kind"] != "DEAD"]
    rstarts = [c["start"] for c in runs]

    def swallowed(d):  # a DEAD bit lying wholly inside one removed run
        i = bisect.bisect_right(rstarts, d["start"] + 1e-9) - 1
        return i >= 0 and d["end"] <= runs[i]["end"] + 1e-9

    return [c for c in joined if c["kind"] != "DEAD" or not swallowed(c)]


def _context_index(units):
    kept = sorted((u for u in units if not u.removed), key=lambda u: u.end)
    return kept, [u.end for u in kept]


def context_before(units, t, index=None):
    kept, ends = index or _context_index(units)
    lo = bisect.bisect_left(ends, t - _CONTEXT)
    hi = bisect.bisect_right(ends, t + 1e-6)
    s = " ".join(u.text.strip() for u in kept[lo:hi])
    return s[-60:]


def analyse(path, mode="suggest", floor=0.45, keep=0.2, use_words=True):
    segs, units, word_level = build_units(path, use_words)
    if not segs:
        return None
    find_segment_level(segs, units)
    if word_level:
        find_word_level(units)
    kept = _Spans([u for u in units if not u.removed])
    cuts = []
    for c in removed_runs(units, mode):
        cuts.append(snap(c, kept))
    for c in find_pauses(units, mode, floor, keep):
        cuts.append(snap(c, kept))
    cuts = [c for c in cuts if c["end"] > c["start"]]
    cuts.sort(key=lambda c: (c["start"], c["end"]))
    if mode == "learning":
        _ensure_breath(cuts, units, keep)
        cuts = [c for c in cuts if c["end"] > c["start"]]
        cuts.sort(key=lambda c: (c["start"], c["end"]))
        cuts = _coalesce(cuts)
    idx = _context_index(units)
    for c in cuts:
        c["level"] = "word" if word_level else "cue"
        c["label"] = LABELS[c["kind"]]
        c["before"] = context_before(units, c["start"], idx)
    dur = fa.duration(segs)
    merged = merge(cuts)  # overlapping cuts remove the same seconds once
    removed = sum(b - a for a, b in merged)
    return {"segs": segs, "units": units, "word_level": word_level, "cuts": cuts, "merged": merged,
            "removed": removed, "duration": dur, "out": max(0.0, dur - removed)}


def drop_subframe(rep, clock):
    """drop every cut that removes no whole frame (in == out timecode), so the printout, JSON, markers,
    counts and removed seconds all agree. A short cut that touches others is judged with them."""
    keep = []
    for a, b in merge(rep["cuts"]):
        if clock.f_out(b) > clock.f_in(a):
            keep.append((a, b))
    starts = [a for a, _ in keep]

    def alive(c):
        i = bisect.bisect_right(starts, c["start"] + 1e-9) - 1
        return i >= 0 and c["end"] <= keep[i][1] + 1e-9

    rep["cuts"] = [c for c in rep["cuts"] if alive(c)]
    rep["merged"] = merge(rep["cuts"])
    rep["removed"] = sum(b - a for a, b in rep["merged"])
    rep["out"] = max(0.0, rep["duration"] - rep["removed"])
    return rep


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
    # cuts in frames once, sorted by start; a running max of the ends makes "end > b" a bisect too
    cf = sorted(((clock.f_near(c["start"]), clock.f_near(c["end"]), n, c) for n, c in enumerate(rep["cuts"])),
                key=lambda x: (x[0], x[2]))
    cstarts = [x[0] for x in cf]
    pmax, m = [], -1
    for x in cf:
        m = max(m, x[1])
        pmax.append(m)
    out, rec = [], 0
    for i, (a, b) in enumerate(segs):
        rec += b - a
        if i == len(segs) - 1:
            break
        nxt = segs[i + 1][0]
        lo, hi = bisect.bisect_right(pmax, b), bisect.bisect_left(cstarts, nxt)
        inside = [x[3] for x in sorted((x for x in cf[lo:hi] if x[1] > b), key=lambda x: x[2])]
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
    if x is None or x < 1 or x > 240:  # the timecode base is round(fps) frames: below 1 there is none
        raise argparse.ArgumentTypeError("نرخ فریم باید عددی بین ۱ و ۲۴۰ باشد: %r" % v)
    return x


def _seconds(v):
    x = fa.parse_number(v)
    if x is None:
        raise argparse.ArgumentTypeError("عدد نیست: %r" % v)
    return x


class _FaHelpFormatter(argparse.RawDescriptionHelpFormatter):
    def add_usage(self, usage, actions, groups, prefix=None):
        return super(_FaHelpFormatter, self).add_usage(usage, actions, groups,
                                                       prefix="استفاده: " if prefix is None else prefix)


class _FaParserBase(argparse.ArgumentParser):
    """argparse with Persian headers and -h text (same as fatext.FaArgumentParser, kept here so this
    file also works with an older _fatext.py)"""

    def __init__(self, *a, **kw):
        kw.setdefault("formatter_class", _FaHelpFormatter)
        kw["add_help"] = False
        super(_FaParserBase, self).__init__(*a, **kw)
        self._positionals.title = "ورودی‌ها"
        self._optionals.title = "گزینه‌ها"   # «optional arguments» (3.9) / «options» (3.10+)
        self.add_argument("-h", "--help", action="help", default=argparse.SUPPRESS,
                          help="نمایش همین راهنما و خروج")


class _Parser(getattr(fa, "FaArgumentParser", None) or _FaParserBase):
    def error(self, message):  # Farsi first line, argparse detail after; exit 2 like argparse
        self.print_usage(sys.stderr)
        sys.stderr.write("خطا در ورودی: %s\n" % message)
        sys.exit(2)


def _write_all(jobs):
    """jobs = [(path, writer(tmp_path))]: write every file next to its target first and move them into
    place only when all succeeded, so a bad path never leaves half the output written"""
    done = []
    try:
        for path, _ in jobs:  # a folder as the target would only fail at the very end
            if os.path.isdir(path):
                raise IsADirectoryError(errno.EISDIR, os.strerror(errno.EISDIR), path)
        for path, fn in jobs:
            tmp = path + ".tmp"
            done.append(tmp)
            fn(tmp)
        for (path, _), tmp in zip(jobs, done):
            os.replace(tmp, path)
    except OSError:
        for tmp in done:
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


def main():
    ap = _Parser(description=__doc__, formatter_class=_FaHelpFormatter)
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
        else:
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
    drop_subframe(rep, clock)
    dur, removed, out = rep["duration"], rep["removed"], rep["out"]
    pct = removed / dur * 100 if dur > 0 else 0.0
    title = os.path.splitext(os.path.basename(src))[0]
    clip = args.clip or (title + ".mov")
    jobs = []
    if args.edl:
        if args.mode == "learning":
            jobs.append((args.edl, lambda p: write_cut_edl(p, rep, clock, title, clip)))
        else:
            sm = suggest_markers(rep, clock, args.latin_labels)
            jobs.append((args.edl, lambda p: write_marker_edl(p, sm, clock, title)))
    if args.markers:
        mk = (learning_markers if args.mode == "learning" else suggest_markers)(rep, clock, args.latin_labels)
        if args.markers.lower().endswith(".edl"):
            jobs.append((args.markers, lambda p: write_marker_edl(p, mk, clock, title)))
        else:
            jobs.append((args.markers, lambda p: write_marker_csv(p, mk, clock)))
    try:
        _write_all(jobs)
    except OSError as e:
        sys.stderr.write("فایل نوشته نشد: %s\n" % e)
        sys.exit(1)
    written = [p for p, _ in jobs]

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
        head = "%s پیشنهاد برش (%s)؛ اگر همه را بپذیری" % (fan(len(cuts), "{:d}"), "، ".join(counts) or "هیچ")
    else:
        head = "%s برش (%s):" % (fan(len(cuts), "{:d}"), "، ".join(counts) or "هیچ")
    print("\n  %s %s ثانیه کم می‌شود و %s ثانیه می‌ماند (%s٪ کوتاه‌تر)" % (
        head, fan(removed, "{:.2f}"), fan(out, "{:.2f}"), fan(pct)))
    if args.mode == "learning":
        print("  %s تکه‌ی ماندنی، یعنی %s جامپ‌کات" % (
            fan(len(kept_segments(rep, clock)), "{:d}"), fan(max(0, len(kept_segments(rep, clock)) - 1), "{:d}")))
        if not rep["word_level"]:
            print("  فقط تکه‌به‌تکه بررسی شد؛ برای برش کلمه‌به‌کلمه (پرکننده و تکرار وسط جمله)، JSON ویسپر با"
                  " زمان‌بندی کلمه‌ها بده.")
    else:
        print("  هیچ‌چیز حذف نشده: این‌ها پیشنهادند، روی تایم‌لاین کامل علامتشان بزن و خودت تصمیم بگیر.")
    for w in written:
        print("  نوشته شد: %s" % w)
    print("  قبل از هر برش، ۳ ثانیه‌ی آخرش را گوش کن؛ عدد بالا فقط حرف‌ها را می‌شمارد، نه دموی بی‌صدا.\n")


if __name__ == "__main__":
    main()
