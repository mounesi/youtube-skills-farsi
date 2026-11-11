#!/usr/bin/env python3
"""retention.py - خروجی «ماندگاری مخاطب» (Audience retention) از YouTube Studio را می‌خواند و نشت‌ها را پیدا می‌کند.

    python3 -I retention.py retention.csv
    python3 -I retention.py retention.csv --duration 600 --transcript transcript.srt   # جمله‌ی هر پرتگاه
    python3 -I retention.py retention.csv --duration 600 --compare other.csv --compare-duration 540
    python3 -I retention.py retention.csv --json
    python3 -I retention.py retention.csv --axis pct --duration 600      # وقتی محور مبهم است
    python3 -I retention.py short.csv --kind short                       # شورت/ریلز (۳ ثانیه‌ی اول)

گرفتن فایل: Studio ← Content (محتوا) ← ویدیو ← Analytics ← Engagement (تعامل) ← کارت «ماندگاری مخاطب» ←
SEE MORE (حالت پیشرفته / Advanced mode) ← بالای صفحه: Export current view ← CSV.
دو ستون لازم است: موقعیت (درصد یا ثانیه یا mm:ss) و درصد بیننده‌هایی که هنوز نگاه می‌کنند. سرستون
انگلیسی و فارسی («زمان ویدیو»، «درصد بینندگان»…)، رقم فارسی، ٪ و ٫ و جداکننده‌ی , ; یا Tab همه خوانده می‌شوند.

سه مشکل جدا، با سه راه‌حل جدا:
  نشت هوک   آنچه در شروع از دست رفت (ویدیوی بلند: ۳۰ ثانیه‌ی اول؛ شورت/ریلز تا ۳ دقیقه: ۳ ثانیه‌ی اول)
  پرتگاه    افت تند در یک لحظه‌ی مشخص (با --transcript جمله‌ی همان لحظه چاپ می‌شود)
  سرازیری   ریزش آرام و پیوسته‌ی بخش میانی (بدون پرتگاه‌ها)

--duration برای محور درصدی لازم است تا موقعیت به زمان تبدیل شود. --compare دو ویدیو را کنار هم می‌گذارد.
هیچ عددی ساخته نمی‌شود: هر عدد از خود فایل می‌آید.
"""
import argparse, csv, io, json, math, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fatext as fa  # noqa: E402

SHORT_MAX_S = 180.0      # YouTube Shorts: up to 3 minutes
LONG_HOOK_S = 30.0       # upstream heuristic: hook = first 30 s
SHORT_HOOK_S = 3.0       # heuristic of this tool (IG skip rate = <3 s; YouTube publishes no window)
HEALTHY_HOOK = 25.0      # upstream heuristic for long videos
CLIFF_MIN = 0.8          # a drop bigger than this between two points counts as a cliff (upstream)
BIG_CLIFF = 3.0          # heuristic of this tool: a cliff worth fixing on its own
FLAT_SLIDE_PER_MIN = 1.0  # heuristic of this tool: <= 1 point per minute counts as a flat slide

POS_KEYS = ("position", "time", "موقعیت", "زمان", "لحظه", "ثانیه", "دقیقه")
RET_KEYS = ("retention", "audience", "viewer", "watching", "ماندگاری", "حفظ", "مخاطب", "بینند",
            "تماشا", "نگهداشت", "نگه داشت")
PCT_MARKS = ("%", "٪", "percent", "درصد")
SEC_MARKS = ("second", "(s)", "sec", "ثانیه")
TIME_WORDS = ("time", "زمان")

_NUMERIC = re.compile(r"^[-−]?[\d.,٫٬،']+$")


class DataError(Exception):
    """A file that can be read but is not a usable retention export (message is Farsi)."""


# ---------------------------------------------------------------- reading

def _num(c):
    """One cell -> float. '98%', '۹۸٫۵٪', '1,234', '98,5', h:mm:ss / m:ss (also in Persian digits). None if unreadable."""
    if c is None:
        return None
    if isinstance(c, (int, float)) and not isinstance(c, bool):
        v = float(c)
    else:
        c = fa.normalize(str(c), digits="ascii")
        c = re.sub(r"[%٪\s ]", "", c)
        if not c or not re.search(r"\d", c):
            return None
        if ":" in c:
            v = fa.parse_timestamp(c)
        elif not _NUMERIC.match(c):
            return None
        else:
            v = fa.parse_number(c)
    # a 400-digit cell is float('inf'): unreadable, not a number to report
    return v if v is not None and math.isfinite(v) else None


def _comma_decimal(c):
    """'100,000' -> 100.0 when ',' is the decimal mark (a single comma, no '.' and no other grouping mark)."""
    t = re.sub(r"[%٪\s ]", "", fa.normalize(str(c), digits="ascii"))
    if not re.fullmatch(r"[-−]?\d+,\d+", t):
        return None
    v = float(t.replace("−", "-").replace(",", "."))
    return v if math.isfinite(v) else None


_NOT_CSV = "این فایل CSV نیست (عکس یا اکسل است)؛ از Studio خروجی CSV بگیر: %s"


def _decode(data):
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1256", errors="replace")  # Persian Windows Excel


def _delimiter(text):
    lines = [l for l in text.splitlines() if l.strip()][:5]
    for d in ("\t", ";", ",", "،"):
        counts = [l.count(d) for l in lines]
        if counts and min(counts) >= 1 and len(set(counts)) == 1:
            return d
    for d in ("\t", ";", ","):
        if lines and lines[0].count(d):
            return d
    return ","


def _has(h, keys):
    h = fa.fold(h or "")
    return any(fa.fold(k) in h for k in keys)


def _pick_columns(header):
    """Header cells -> (pos_index, ret_index). Defaults to 0, 1 (upstream: by index)."""
    if not header:
        return 0, 1
    pos = [i for i, h in enumerate(header) if _has(h, POS_KEYS) and not _has(h, RET_KEYS)]
    pos = pos or [i for i, h in enumerate(header) if _has(h, POS_KEYS)]
    p = pos[0] if pos else 0
    rets = [i for i, h in enumerate(header) if i != p and _has(h, RET_KEYS)]
    best = [i for i in rets if _has(header[i], ("absolute", "مطلق"))]
    plain = [i for i in rets if not _has(header[i], ("relative", "نسبی"))]
    r = (best or plain or rets or [1 if p != 1 else 0])[0]
    return p, r


def load_csv(path, info=None):
    """Rows of (position, retention), sorted by position.
    If `info` is a dict it gets 'header' (position column name), 'ret_header', 'colon' (mm:ss seen)
    and 'scaled' (retention given as 0..1 and turned into percent)."""
    with open(path, "rb") as fh:
        data = fh.read()
    # a PNG/JPEG screenshot or an .xlsx (zip) passed as the CSV
    if data[:8] == b"\x89PNG\r\n\x1a\n" or data[:4] == b"PK\x03\x04" or data[:3] == b"\xff\xd8\xff":
        raise DataError(_NOT_CSV % path)
    if data[:2] not in (b"\xff\xfe", b"\xfe\xff") and b"\x00" in data:
        raise DataError(_NOT_CSV % path)
    try:
        text = _decode(data)
        # newline=None: '\r' (old Excel for Mac) and '\r\n' line ends both read as '\n'
        reader = csv.reader(io.StringIO(text, newline=None), delimiter=_delimiter(text))
        table = [r for r in reader if any(c.strip() for c in r)]
    except (csv.Error, UnicodeError) as e:
        raise DataError("فایل CSV خراب است یا CSV نیست؛ دوباره از Studio خروجی CSV بگیر: %s" % path) from e
    # the header is the last non-data row before the first data row (a row with 2+ numeric cells);
    # leading text columns (Content, Video title) no longer make data rows look like headers
    pre = []
    for r in table:
        if len(r) >= 2 and sum(_num(c) is not None for c in r) >= 2:
            break
        if len(r) >= 2:
            pre.append([c.strip() for c in r])
    keyed = [h for h in pre if any(_has(c, POS_KEYS) or _has(c, RET_KEYS) for c in h)]
    header_row = (keyed or pre or [None])[-1]
    pi, ri = _pick_columns(header_row)
    rows, colon, pct_cells = [], False, False
    for r in table:
        if len(r) <= max(pi, ri):
            continue
        x, y = _num(r[pi]), _num(r[ri])
        if x is None or y is None:
            continue
        if ":" in r[pi]:
            colon = True
        if "%" in r[pi] or "٪" in r[pi]:
            pct_cells = True
        rows.append((x, y, r[ri]))
    ret_name = header_row[ri] if header_row and ri < len(header_row) else None
    col = "«%s»" % ret_name if ret_name else "ستون %s" % fa.to_fa_digits(str(ri + 1))
    if rows and max(y for _, y, _ in rows) > 1000:
        # '100,000' in a comma-decimal file with 3 decimals is 100.0, not a hundred thousand
        again = [(x, _comma_decimal(c) if "," in c else y, c) for x, y, c in rows]
        if all(y is not None and 0 <= y <= 1000 for _, y, _ in again):
            rows = again
        else:
            bad = max(rows, key=lambda t: t[1])[2].strip()
            raise DataError("ماندگاری در %s بیشتر از ۱۰۰۰٪ خوانده شد (مثلاً «%s»)؛ این عدد درصد بیننده نیست. "
                            "ستون درست را از Studio خروجی بگیر: %s" % (col, bad, path))
    neg = [c for _, y, c in rows if y < 0]
    if neg:
        raise DataError("مقدار منفی برای ماندگاری معنا ندارد: «%s» در %s (%s)" % (neg[0].strip(), col, path))
    rows = [(x, y) for x, y, _ in rows]
    rows.sort(key=lambda t: t[0])
    scaled = False
    if rows and rows[0][1] <= 1.5 and max(y for _, y in rows) <= 3.0:
        rows = [(x, y * 100.0) for x, y in rows]
        scaled = True
    if info is not None:
        info["header"] = header_row[pi] if header_row and pi < len(header_row) else None
        info["ret_header"] = ret_name
        info["colon"] = colon
        info["pct_cells"] = pct_cells
        info["scaled"] = scaled
    return rows


def _duration(v):
    f = _num(v)
    if f is None:
        raise argparse.ArgumentTypeError("عدد نیست: %r (ثانیه بده، مثلاً 600 یا 10:00)" % v)
    if f <= 0:
        raise argparse.ArgumentTypeError("باید بیشتر از ۰ ثانیه باشد")
    return f


def _seconds(v):
    f = _num(v)
    if f is None or f <= 0:
        raise argparse.ArgumentTypeError("ثانیه‌ی مثبت بده: %r" % v)
    return f


def detect_axis(xs, dur=None, forced=None, header=None, colon=False, pct_cells=False):
    """-> (pct_axis, reason). reason "ratio" means a 0..1 position axis: multiply positions by 100.
    Order: --axis, mm:ss cells, % marks (header or cells), explicit seconds in the header, --duration,
    a 0..1 ratio axis, a plain «زمان»/time header, a guess from the largest position."""
    if forced:
        return forced == "pct", "--axis"
    if colon:
        return False, "mm:ss positions"
    if pct_cells or (header and _has(header, PCT_MARKS)):
        return True, "header" if not pct_cells else "% cells"
    if header and (_has(header, SEC_MARKS) or re.search(r"\bsec", header.lower())):
        return False, "header"
    mx = max(xs)
    if dur:
        if abs(mx - dur) <= max(2.0, 0.05 * dur):
            return False, "--duration"
        if abs(mx - 100.0) <= 1.0 and dur > 105:
            return True, "--duration"
    if mx <= 1.0 and (dur or (header and "ratio" in header.lower())):
        return True, "ratio"
    if header and _has(header, TIME_WORDS):
        return False, "header"
    return mx <= 100.5, "guess"


# ---------------------------------------------------------------- analysis

def _interp(rows, x):
    if x <= rows[0][0]:
        return rows[0][1]
    for (x0, y0), (x1, y1) in zip(rows, rows[1:]):
        if x0 <= x <= x1:
            return y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return rows[-1][1]


def analyze(path, dur=None, axis=None, kind=None, hook_window=None, notes=None):
    """One export -> dict of numbers (all read from the file). Raises OSError / DataError."""
    notes = notes if notes is not None else []
    info = {}
    rows = load_csv(path, info)
    name = os.path.basename(path)
    # a 0 at the very start (some API exports) is not a real start: leaving it in would make up a 100% start
    lead = 0
    while lead < len(rows) and rows[lead][1] == 0:
        lead += 1
    if rows and lead == len(rows):
        raise DataError("همه‌ی نقطه‌های ماندگاری صفرند: %s" % path)
    if lead:
        notes.append("%s: %s نقطه‌ی اول ماندگاری صفر داشت و کنار گذاشته شد."
                     % (name, fa.to_fa_digits(str(lead), True)))
        rows = rows[lead:]
    if len(rows) < 8:
        raise DataError("از این فایل حتی ۸ نقطه‌ی داده خوانده نشد: %s" % path)
    xs = [r[0] for r in rows]
    header = info.get("header")
    pct_axis, why = detect_axis(xs, dur, axis, header, info.get("colon"), info.get("pct_cells"))
    if why == "ratio":
        rows = [(x * 100.0, y) for x, y in rows]
        notes.append("%s: موقعیت به شکل ۰ تا ۱ (نسبت طول ویدیو) بود؛ در ۱۰۰ ضرب شد و محور درصدی شد." % name)
    xs = [r[0] for r in rows]; ys = [r[1] for r in rows]
    if why in ("guess", "header"):
        notes.append("%s: محور را %s فرض کردم (%s، بیشترین موقعیت %s)؛ برای تغییرش --axis pct یا --axis seconds بده."
                     % (name, "درصدی" if pct_axis else "ثانیه",
                        "از روی سرستون «%s»" % header if why == "header" else "حدس",
                        fa.to_fa_digits("%g" % max(xs), True)))
    elif why == "--duration" and pct_axis and header and _has(header, TIME_WORDS):
        notes.append("%s: سرستون «%s» زمان را نشان می‌دهد، اما با --duration محور را درصدی فرض کردم "
                     "(بیشترین موقعیت ۱۰۰ است، نه طول ویدیو)؛ برای تغییرش --axis seconds بده." % (name, header))
    ret_header = info.get("ret_header") or ""
    relative = _has(ret_header, ("relative", "نسبی"))
    if relative:
        notes.append("%s: ستون «%s» ماندگاری نسبی است (مقایسه با ویدیوهای مشابه)، نه سهم بیننده‌هایی که هنوز "
                     "نگاه می‌کنند؛ عددهای این گزارش درصد واقعی بیننده نیستند. از Studio ستون ماندگاری مطلق "
                     "(Absolute audience retention) را خروجی بگیر." % (name, ret_header))
    elif info.get("scaled"):
        notes.append("%s: ماندگاری به شکل ۰ تا ۱ بود؛ در ۱۰۰ ضرب شد." % name)
    length = dur if dur else (None if pct_axis else max(xs))
    if kind is None:
        kind = "short" if (length is not None and length <= SHORT_MAX_S) else "long"
        if length is None:
            notes.append("%s: طول ویدیو معلوم نیست (محور درصدی بدون --duration)؛ ویدیوی بلند فرض شد." % name)

    def at(x):  # position -> seconds, or None
        if not pct_axis:
            return x
        return x / 100.0 * dur if dur else None

    def to_x(sec):  # seconds -> position on this axis, or None
        if not pct_axis:
            return sec
        return sec / dur * 100.0 if dur else None

    hw = hook_window if hook_window else (SHORT_HOOK_S if kind == "short" else LONG_HOOK_S)
    if hook_window and length is not None and hw >= length:
        raise DataError("--hook-window (%s ثانیه) از طول ویدیو (%s ثانیه) کمتر نیست؛ بازه‌ی هوک باید کوتاه‌تر از خود ویدیو باشد."
                        % (fa.to_fa_digits("%g" % hw, True), fa.to_fa_digits("%g" % length, True)))
    cutoff = to_x(hw)
    hook_s = hw
    if cutoff is None:
        cutoff = 10.0  # upstream: first 10% when the axis is percent and the length is unknown
        hook_s = None
        notes.append("%s: محور درصدی است و طول ویدیو معلوم نیست؛ نشت هوک روی ۱۰٪ اول ویدیو حساب شد، نه %s ثانیه. "
                     "برای پنجره‌ی درست --duration بده." % (name, fa.to_fa_digits("%g" % hw)))
    start = ys[0]
    hook_end = min([y for x, y in rows if x <= cutoff] + [_interp(rows, cutoff)])
    hook_leak = start - hook_end

    drops = []
    for i in range(1, len(rows)):
        d = ys[i - 1] - ys[i]
        span = xs[i] - xs[i - 1] or 1
        drops.append((d / span, xs[i - 1], xs[i], d))
    # CLIFFS: filter by size first, then the five biggest by amount lost (upstream fix).
    # Drops that start inside the hook window are the hook leak, so they are not listed twice.
    # A drop that the next one or two points win back (a ±1.5 zig-zag on a jagged curve) is noise, not a cliff.
    def kept(i):  # drops[i] goes from ys[i] to ys[i+1]
        after = ys[i + 2:i + 4]
        return not after or ys[i] - max(after) > CLIFF_MIN
    big = sorted((t for i, t in enumerate(drops) if t[3] > CLIFF_MIN and t[1] >= cutoff and kept(i)),
                 key=lambda t: t[3], reverse=True)[:5]
    cliffs = [{"from": round(a1, 2), "to": round(b1, 2), "lost": round(d, 2),
               "at_seconds": round(at(a1), 1) if at(a1) is not None else None}
              for _, a1, b1, d in big]
    cliff_set = {(a1, b1) for _, a1, b1, _ in big}
    # SLIDE: net loss over the time it took, after the hook, leaving out the cliffs (span-weighted).
    # Every step counts, rises too: on a jagged curve the small rises cancel the small drops.
    # Only a big jump UP (>= BIG_CLIFF: a rewatch / loop spike, common at the end of a Short) is left out,
    # so a Short's loop does not hide the real slide. All jumps up are still listed as bumps.
    bumps = [{"from": round(x0, 2), "to": round(x1, 2), "gained": round(-d, 2),
              "at_seconds": round(at(x0), 1) if at(x0) is not None else None}
             for _, x0, x1, d in drops if -d > CLIFF_MIN]
    mid = [(d, x1 - x0) for _, x0, x1, d in drops if x0 >= cutoff and (x0, x1) not in cliff_set
           and -d < BIG_CLIFF]
    tot_span = sum(s for _, s in mid)
    slide = sum(d for d, _ in mid) / tot_span if tot_span > 0 else 0
    slide_total = max(0.0, sum(d for d, _ in mid))
    per_sec = None
    if not pct_axis:
        per_sec = slide
    elif dur:
        per_sec = slide * 100.0 / dur
    cliff_after = sum(c["lost"] for c in cliffs)
    # the three buckets together cannot be more than the curve really fell
    cap = max(0.0, start - min(ys))
    cliff_bucket = min(cliff_after, max(0.0, cap - max(0.0, hook_leak)))
    slide_total = min(slide_total, max(0.0, cap - max(0.0, hook_leak) - cliff_bucket))
    area = sum((x1 - x0) * (y0 + y1) / 2.0 for (x0, y0), (x1, y1) in zip(rows, rows[1:]))
    avg = area / (xs[-1] - xs[0]) if xs[-1] > xs[0] else ys[0]
    xmax = 100.0 if pct_axis else xs[-1]
    marks = {str(q): round(_interp(rows, xs[0] + (xmax - xs[0]) * q / 100.0), 2) for q in (25, 50, 75)}

    buckets = {"hook": round(hook_leak, 2), "cliff": round(cliff_bucket, 2), "slide": round(slide_total, 2)}
    main = max(buckets, key=lambda k: buckets[k])
    slide_flat = (per_sec is not None and per_sec * 60 <= FLAT_SLIDE_PER_MIN or
                  per_sec is None and slide <= FLAT_SLIDE_PER_MIN / 10.0)
    fine = (kind == "long" and hook_leak < HEALTHY_HOOK and
            not any(c["lost"] >= BIG_CLIFF for c in cliffs) and slide_flat)
    if all(v <= 0 for v in buckets.values()):
        main = None
    return {"file": name, "points": len(rows), "start": start, "end": ys[-1],
            "axis": "pct" if pct_axis else "seconds", "kind": kind,
            "duration": round(length, 1) if length is not None else None,
            "hook_window_s": hook_s, "hook_window_pct": round(cutoff, 2) if pct_axis else None,
            "hook_leak": round(hook_leak, 2), "cliffs": cliffs, "bumps": bumps[:5],
            "slide_per_unit": round(slide, 3),
            "slide_per_minute": round(per_sec * 60, 2) if per_sec is not None else None,
            "slide_flat": bool(slide_flat),
            "average": round(avg, 2), "at_pct": marks,
            "diagnosis": {"main": main, "lost": buckets, "fine": bool(fine)}, "said": {},
            "_rows": rows, "_cutoff": cutoff}


def attach_transcript(res, cues):
    """Put what was being said at each cliff into res['said'] and each cliff's 'line',
    and the words inside the hook window into res['opening']."""
    if res["duration"] or res["axis"] == "seconds":
        first = [q.text for q in cues if q.start < res["hook_window_s"]]
        if first:
            res["opening"] = _clip(" ".join(first), 140)
    for c in res["cliffs"]:
        t = c["at_seconds"]
        if t is None:
            continue
        near = [q.text for q in cues if q.start <= t + 4 and q.end >= t - 4]
        line = _clip(" ".join(near), 140)
        c["line"] = line
        res["said"][str(c["from"])] = line


def _clip(s, n):
    s = " ".join(s.split())
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0]
    return (cut or s[:n]) + "…"


# ---------------------------------------------------------------- Farsi report

LABEL = {"hook": "نشت هوک", "cliff": "پرتگاه", "slide": "سرازیری"}


def n(x, nd=1):
    return fa.to_fa_digits(("%." + str(nd) + "f") % x, separators=True).replace("-", "−")


def p(x, nd=1):
    return n(x, nd) + "٪"


def ts(sec):
    return fa.fmt_timestamp(sec, "yt", fa_digits=True)


def where(c):
    return ts(c["at_seconds"]) if c["at_seconds"] is not None else "نقطه‌ی " + p(c["from"], 0) + " ویدیو"


def hook_text(res):
    if res["axis"] == "pct" and not res["duration"]:
        return "۱۰٪ اول ویدیو"
    return "%s ثانیه‌ی اول" % n(res["hook_window_s"], 0)


def slide_text(res):
    if res["slide_per_unit"] < 0:
        return "منحنی در بخش میانی بالا رفته (بازپخش یا لوپ)؛ سرازیری‌ای نیست"
    if res["slide_per_minute"] is not None:
        return "%s واحد درصد در هر دقیقه" % n(res["slide_per_minute"], 2)
    return "%s واحد درصد در هر ۱٪ از طول ویدیو" % n(res["slide_per_unit"], 3)


def advice(res):
    """-> list of Farsi lines: the biggest leak and ONE change for it."""
    d = res["diagnosis"]; out = []
    if d["main"] is None:
        return ["ریزشی در منحنی دیده نمی‌شود؛ ویدیو بیننده را نگه داشته. اگر بازدید کم است، مشکل بسته‌بندی است → /yt-package"]
    if d["fine"]:
        return ["هوک سالم است، پرتگاه بزرگی نیست و سرازیری ناچیز است: خود ویدیو مشکلی ندارد.",
                "مشکل احتمالاً بسته‌بندی است (عنوان و تامبنیل) → /yt-package"]
    lost = d["lost"][d["main"]]
    out.append("بزرگ‌ترین نشت: %s (%s واحد درصد از دست رفت)" % (LABEL[d["main"]], n(lost)))
    if d["main"] == "hook":
        if res["kind"] == "short":
            out.append("یک تغییر: فریم صفر را عوض کن. در شورت و ریلز چند ثانیه‌ی اول تعیین‌کننده است: "
                       "متن روی صفحه + تصویر غیرمنتظره از همان فریم اول، بدون سلام و مقدمه → /yt-reel")
        else:
            out.append("یک تغییر: ۱۵ ثانیه‌ی اول اسکریپت را بازنویسی کن، نه تدوین را. همان قولی که عنوان داده "
                       "را تأیید کن، سؤالی باز کن که بیننده نتواند ببندد و نشان بده جواب در ویدیو هست → /yt-script")
        if res.get("opening"):
            out.append("ویدیو این‌طور شروع می‌شود: «%s»" % res["opening"])
    elif d["main"] == "cliff":
        c = max(res["cliffs"], key=lambda c: c["lost"])
        out.append("یک تغییر: برو سر %s (افت %s). معمولاً یکی از این‌هاست: عوض شدن موضوع بی‌خبر، "
                   "تبلیغ اسپانسر، یا مقدمه‌چینی طولانی. قبلش یک جمله‌ی راهنما بگذار یا آن تکه را کوتاه کن."
                   % (where(c), p(c["lost"])))
        if c.get("line"):
            out.append("آنجا داشتی می‌گفتی: «%s»" % c["line"])
    else:
        out.append("یک تغییر: بخش میانی را کوتاه کن، بازنویسی نکن. ریزش یکنواخت یعنی ریتم کند است، "
                   "نه محتوای بد → /yt-edit")
    return out


def print_report(res, notes_unused=None):
    print("\n  %s   %s نقطه   %s → %s   محور: %s%s" % (
        res["file"], n(res["points"], 0), p(res["start"]), p(res["end"]),
        "درصد طول ویدیو" if res["axis"] == "pct" else "ثانیه",
        ("   طول: " + ts(res["duration"])) if res["duration"] else ""))
    if res["kind"] == "short":
        print("  شورت/ریلز (تا ۳ دقیقه): چند ثانیه‌ی اول تعیین‌کننده است (بازه‌ی هوک این ابزار: ۳ ثانیه).")
    print()
    hl = res["hook_leak"]
    if res["kind"] == "short":
        verdict = ""
        rule = ("آستانه‌ی رسمی وجود ندارد؛ با شورت‌های قبلی خودت مقایسه کن (--compare) و در Studio "
                "عدد «Viewed vs. swiped away» را هم ببین.")
    else:
        verdict = "   [%s]" % ("سالم" if hl < HEALTHY_HOOK else "نشت دارد" if hl < 40 else "شدید")
        rule = "زیر ۲۵٪ برای ویدیوی بلند سالم است (قاعده‌ی سرانگشتی، نه عدد رسمی یوتیوب)."
        if hl >= HEALTHY_HOOK:
            rule += " اول این را درست کن."
    print("  نشت هوک   %s در %s رفتند%s" % (p(hl), hook_text(res), verdict))
    print("            " + rule + "\n")
    print("  پرتگاه‌ها   لحظه‌هایی که بیننده‌ها واقعاً رفتند")
    for c in res["cliffs"]:
        line = ("   «%s»" % c["line"]) if c.get("line") else ""
        print("    −%s  در %s%s" % (p(c["lost"]), where(c), line))
    if not res["cliffs"]:
        print("    بعد از هوک، هیچ افتی بیشتر از ۰٫۸ واحد درصد بین دو نقطه نیست: ریزش همه سرازیری است، نه لحظه.")
    if res["bumps"]:
        print("\n  برگشت‌ها   جاهایی که منحنی بالا رفت (بازپخش، عقب زدن یا لوپ شورت)")
        for b in res["bumps"]:
            print("    +%s  در %s" % (p(b["gained"]), where(b)))
    if res["slide_per_unit"] < 0:
        print("\n  سرازیری   " + slide_text(res))
    else:
        print("\n  سرازیری   %s در بخش میانی (بدون پرتگاه‌ها)" % slide_text(res))
        if res["slide_flat"]:
            print("            سرازیری ناچیز است.")
        else:
            print("            ریزش آرام و یکنواخت یعنی ریتم کند است، نه محتوای بد. وسط را کوتاه کن، بازنویسی نکن.")
    print("\n  میانگین تقریبی منحنی: %s   (از روی نمودار؛ عدد رسمی را از «Average percentage viewed» در Studio بردار)"
          % p(res["average"]))
    print("\n  تشخیص")
    for line in advice(res):
        print("    " + line)


def compare(a, b):
    """Two analyses -> dict of differences (a minus b) and the bucket that explains most of the gap."""
    diff = {k: round(a["diagnosis"]["lost"][k] - b["diagnosis"]["lost"][k], 2) for k in ("hook", "cliff", "slide")}
    worse = max(diff, key=lambda k: abs(diff[k]))
    return {"a": a["file"], "b": b["file"], "lost_diff": diff, "main_gap": worse,
            "average_diff": round(a["average"] - b["average"], 2),
            "end_diff": round(a["end"] - b["end"], 2),
            "at_pct_diff": {q: round(a["at_pct"][q] - b["at_pct"][q], 2) for q in a["at_pct"]},
            "same_kind": a["kind"] == b["kind"]}


def print_compare(a, b, cmp):
    print("\n  مقایسه‌ی دو ویدیو   الف = %s   ب = %s" % (a["file"], b["file"]))
    if not cmp["same_kind"]:
        print("  هشدار: یکی شورت است و دیگری بلند؛ این مقایسه معنای زیادی ندارد.")
    rows = [("نشت هوک", a["hook_leak"], b["hook_leak"]),
            ("افت در پرتگاه‌ها", a["diagnosis"]["lost"]["cliff"], b["diagnosis"]["lost"]["cliff"]),
            ("افت در سرازیری", a["diagnosis"]["lost"]["slide"], b["diagnosis"]["lost"]["slide"]),
            ("ماندگاری در ۲۵٪ ویدیو", a["at_pct"]["25"], b["at_pct"]["25"]),
            ("ماندگاری در ۵۰٪ ویدیو", a["at_pct"]["50"], b["at_pct"]["50"]),
            ("ماندگاری در ۷۵٪ ویدیو", a["at_pct"]["75"], b["at_pct"]["75"]),
            ("پایان", a["end"], b["end"]),
            ("میانگین تقریبی", a["average"], b["average"])]
    print("    %-24s %10s %10s %10s" % ("", "الف", "ب", "فرق"))
    for label, x, y in rows:
        sign = "+" if x - y > 0 else "−" if x - y < 0 else ""
        print("    %-24s %10s %10s %10s" % (label, p(x), p(y), sign + p(abs(x - y))))
    k = cmp["main_gap"]; d = cmp["lost_diff"][k]
    if d == 0:
        print("\n  هر دو ویدیو در هوک، پرتگاه و سرازیری به یک اندازه بیننده از دست دادند.")
    else:
        more, less = ("الف", "ب") if d > 0 else ("ب", "الف")
        print("\n  بیشترین فاصله در «%s» است: ویدیوی %s %s واحد درصد بیشتر از ویدیوی %s از دست داد."
              % (LABEL[k], more, n(abs(d)), less))
        print("  از ویدیوی %s یاد بگیر: همان بخش را در آن ببین و مقایسه کن." % less)


# ---------------------------------------------------------------- cli

USAGE = ("python3 -I retention.py retention.csv [--duration SECONDS] [--transcript FILE] "
         "[--compare OTHER.csv] [--compare-duration SECONDS] [--axis pct|seconds] "
         "[--kind short|long] [--hook-window SECONDS] [--json]")


def main():
    ap = argparse.ArgumentParser(usage=USAGE, description="خواندن خروجی ماندگاری مخاطب YouTube Studio و پیدا کردن نشت‌ها.")
    ap.add_argument("csv", nargs="?", help="فایل CSV خروجی Studio")
    ap.add_argument("--transcript", default=None, help="رونوشت SRT، VTT یا JSON ویسپر برای جمله‌ی هر پرتگاه")
    ap.add_argument("--duration", type=_duration, default=None, help="طول ویدیو به ثانیه (یا 10:00)؛ برای محور درصدی لازم است")
    ap.add_argument("--axis", choices=["pct", "seconds"], default=None, help="نوع محور را به زور تعیین کن")
    ap.add_argument("--kind", choices=["short", "long"], default=None, help="شورت/ریلز یا ویدیوی بلند (پیش‌فرض: از روی طول)")
    ap.add_argument("--hook-window", type=_seconds, default=None, help="طول بازه‌ی هوک به ثانیه (پیش‌فرض ۳۰، شورت ۳)")
    ap.add_argument("--compare", default=None, help="CSV ویدیوی دوم برای مقایسه")
    ap.add_argument("--compare-duration", type=_duration, default=None, help="طول ویدیوی دوم به ثانیه")
    ap.add_argument("--json", action="store_true", help="خروجی JSON")
    args = ap.parse_args()
    if not args.csv or not os.path.isfile(args.csv):
        if args.csv:
            print("فایل پیدا نشد: %s\n" % args.csv, file=sys.stderr)
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    notes = []
    try:
        res = analyze(args.csv, args.duration, args.axis, args.kind, args.hook_window, notes)
        other = None
        if args.compare:
            if not os.path.isfile(args.compare):
                raise DataError("فایل مقایسه پیدا نشد: %s" % args.compare)
            other = analyze(args.compare, args.compare_duration, args.axis, args.kind, args.hook_window, notes)
    except DataError as e:
        print(str(e), file=sys.stderr); sys.exit(1)
    except OSError as e:
        print("فایل خوانده نشد: %s" % e, file=sys.stderr); sys.exit(1)
    if args.transcript:
        try:
            cues = fa.load_cues(args.transcript)
        except OSError as e:
            print("رونوشت خوانده نشد: %s" % e, file=sys.stderr); sys.exit(1)
        if not cues:
            notes.append("در رونوشت هیچ خطی پیدا نشد.")
        if res["axis"] == "pct" and not args.duration:
            notes.append("محور درصدی است و --duration ندادی؛ بدون طول ویدیو نمی‌شود پرتگاه را به جمله‌ی رونوشت وصل کرد.")
        attach_transcript(res, cues)
    for line in notes:
        print("نکته: " + line, file=sys.stderr)
    cmp = compare(res, other) if other else None
    if args.json:
        out = {k: v for k, v in res.items() if not k.startswith("_")}
        if other:
            out["compare"] = dict(cmp, other={k: v for k, v in other.items() if not k.startswith("_")})
        print(json.dumps(out, indent=1, ensure_ascii=False, allow_nan=False))
        return
    print_report(res)
    if other:
        print_compare(res, other, cmp)
    print("\n  منتشرش کنیم یا تغییرش بدیم؟\n")


if __name__ == "__main__":
    main()
