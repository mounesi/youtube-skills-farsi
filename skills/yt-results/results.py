#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""results.py - دفترچه‌ی نتیجه‌ی ویدیوها (۲۴ ساعت و ۷ روز) و مقایسه با میانه‌ی خود کانال.

ثبت یک ردیف (اگر فایل نباشد با سرستون ساخته می‌شود):
    python3 -I results.py --log results.csv --add video_id=reel-07 platform=اینستاگرام format=ریلز \\
        checked_at=24h views=۱۲٫۴ هزار likes=۸۴۰ comments=۹۵ saves=۳۱۰ shares=۱۴۰ follows=۲۲۰ non_follower_pct=۸۷٪

گزارش (نرخ در هر ۱۰۰۰ بازدید + چند برابرِ میانه‌ی همان پلتفرم و فرمت و زمان بررسی):
    python3 -I results.py --log results.csv --report                  # آخرین ردیف ثبت‌شده
    python3 -I results.py --log results.csv --report --video reel-07 --checked 7d
    python3 -I results.py --log results.csv --report --all            # جدول همه‌ی ردیف‌ها
    python3 -I results.py --fields                                    # فهرست ستون‌ها و نام‌های فارسی

هیچ عددی ساخته نمی‌شود: هر خانه‌ای که ندادی خالی می‌ماند و در گزارش «—» نشان داده می‌شود.
"""
import csv
import datetime
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fatext as fa  # noqa: E402

# ---------------------------------------------------------------- schema

# (column, kind, Farsi label)
FIELDS = [
    ("video_id", "text", "شناسه‌ی ویدیو"),
    ("platform", "platform", "پلتفرم"),
    ("format", "format", "فرمت"),
    ("checked_at", "checked", "زمان بررسی"),
    ("published", "text", "تاریخ انتشار"),
    ("title", "text", "عنوان"),
    ("tested", "text", "چیزی که این بار امتحان کردی"),
    ("views", "count", "بازدید"),
    ("reach", "count", "ریچ (حساب‌های دیده‌شده)"),
    ("likes", "count", "لایک"),
    ("comments", "count", "کامنت"),
    ("saves", "count", "سیو"),
    ("shares", "count", "اشتراک‌گذاری"),
    ("follows", "count", "فالو / سابسکرایب جدید"),
    ("non_follower_pct", "pct", "درصد غیرفالوور"),
    ("avg_watch_s", "seconds", "میانگین زمان تماشا (ثانیه یا m:ss)"),
    ("notes", "text", "یادداشت"),
    ("logged_on", "auto", "تاریخ ثبت"),
]
COLUMNS = [f[0] for f in FIELDS]
KIND = {f[0]: f[1] for f in FIELDS}
LABEL = {f[0]: f[2] for f in FIELDS}
REQUIRED = ("video_id", "platform", "format", "checked_at")

ALIASES = {
    "video_id": ["video", "id", "vid", "ویدیو", "شناسه", "آیدی", "ایدی"],
    "platform": ["پلتفرم", "پلت‌فرم", "سکو"],
    "format": ["فرمت", "نوع", "قالب"],
    "checked_at": ["checked", "check", "at", "window", "زمان", "بررسی", "زمان_بررسی"],
    "published": ["date", "published_on", "انتشار", "تاریخ", "تاریخ_انتشار"],
    "title": ["عنوان", "تیتر"],
    "tested": ["test", "hypothesis", "idea", "تست", "آزمون", "فرضیه", "ایده"],
    "views": ["view", "plays", "بازدید", "ویو", "پلی"],
    "reach": ["accounts_reached", "ریچ", "دسترسی"],
    "likes": ["like", "لایک", "پسند"],
    "comments": ["comment", "کامنت", "نظر", "نظرها"],
    "saves": ["save", "سیو", "ذخیره"],
    "shares": ["share", "sends", "send", "شیر", "اشتراک‌گذاری", "هم‌رسانی", "ارسال"],
    "follows": ["follow", "followers", "new_followers", "subs", "subscribers", "subscribed",
                "فالو", "فالوور", "سابسکرایب", "سابسکرایبر", "دنبال‌کننده"],
    "non_follower_pct": ["non_followers", "nonfollower", "non_follower", "غیرفالوور", "غیر_فالوور",
                         "درصد_غیرفالوور"],
    "avg_watch_s": ["avg_watch", "watch", "watch_time", "زمان_تماشا", "میانگین_تماشا"],
    "notes": ["note", "یادداشت", "توضیح"],
}

PLATFORMS = {
    "instagram": ["instagram", "ig", "insta", "اینستاگرام", "اینستا"],
    "youtube": ["youtube", "yt", "یوتیوب", "یوتوب"],
    "tiktok": ["tiktok", "tt", "تیک‌تاک", "تیکتاک", "تیک تاک"],
    "facebook": ["facebook", "fb", "فیسبوک", "فیس‌بوک", "فیس بوک"],
    "telegram": ["telegram", "tg", "تلگرام"],
    "linkedin": ["linkedin", "لینکدین"],
    "x": ["x", "twitter", "توییتر", "ایکس"],
}
FORMATS = {
    "reel": ["reel", "reels", "ریلز", "ریل"],
    "short": ["short", "shorts", "شورت", "شورتس"],
    "long": ["long", "video", "longform", "long-form", "ویدیو", "بلند", "ویدیوی_بلند", "ویدیو_بلند",
             "ویدئو", "ویدئوی بلند", "ویدئو بلند"],
    "live": ["live", "لایو", "زنده"],
    "carousel": ["carousel", "کاروسل", "اسلاید"],
    "post": ["post", "image", "پست", "عکس"],
    "story": ["story", "استوری"],
}
FA_PLATFORM = {"instagram": "اینستاگرام", "youtube": "یوتیوب", "tiktok": "تیک‌تاک", "facebook": "فیسبوک",
               "telegram": "تلگرام", "linkedin": "لینکدین", "x": "ایکس"}
FA_FORMAT = {"reel": "ریلز", "short": "شورت", "long": "ویدیوی بلند", "live": "لایو", "carousel": "کاروسل",
             "post": "پست", "story": "استوری"}

RATE_FIELDS = ("follows", "saves", "shares", "comments", "likes")
COMPARE_FIELDS = ("follows_1k", "saves_1k", "shares_1k", "comments_1k", "likes_1k",
                  "non_follower_pct", "avg_watch_s", "views")
METRIC_LABEL = {
    "follows_1k": "فالو در هر ۱۰۰۰ بازدید",
    "saves_1k": "سیو در هر ۱۰۰۰ بازدید",
    "shares_1k": "اشتراک‌گذاری در هر ۱۰۰۰ بازدید",
    "comments_1k": "کامنت در هر ۱۰۰۰ بازدید",
    "likes_1k": "لایک در هر ۱۰۰۰ بازدید",
    "non_follower_pct": "درصد غیرفالوور",
    "avg_watch_s": "میانگین زمان تماشا (ثانیه)",
    "views": "بازدید خام (فقط برای زمینه)",
}
MIN_BASELINE = 3      # earlier rows needed before a median means anything (heuristic)
HIGH, LOW = 1.5, 0.7  # multiple thresholds, judged on the shown (1-decimal) value (heuristic)


def _key(s):
    return fa.fold(s).replace(" ", "_").replace("-", "_")


def _pkey(s):
    """Looser key for platform/format names only: «ویدئو» = «ویدیو», «تیک تاک» = «تیک‌تاک»."""
    return _key(s).replace("ئ", "ی").replace("_", "")


def vid_key(v):
    """Comparison key for video_id: «ریلز-۰۷» and «ریلز-07» are the same video. The stored id is untouched."""
    return fa.fold(v or "").strip()


# «اشتراک» / «مشترک» alone may mean shares or subscribers: never guess which
AMBIGUOUS_KEYS = {"اشتراک", "اشتراکها", "اشتراک_ها", "مشترک", "مشترکها", "مشترک_ها", "مشترکین"}


_ALIAS = {}
for _col in COLUMNS:
    _ALIAS[_key(_col)] = _col
for _col, _names in ALIASES.items():
    for _n in _names:
        _ALIAS[_key(_n)] = _col
_PLATFORM = {_pkey(n): k for k, names in PLATFORMS.items() for n in names}
_FORMAT = {_pkey(n): k for k, names in FORMATS.items() for n in names}
for _k in PLATFORMS:
    _PLATFORM[_pkey(_k)] = _k
for _k in FORMATS:
    _FORMAT[_pkey(_k)] = _k


class InputError(Exception):
    pass


# ---------------------------------------------------------------- values

def _num_str(v):
    if v is None:
        return ""
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return ("%.4f" % v).rstrip("0").rstrip(".")


def norm_checked(v):
    """'24h' / '۲۴ ساعت' / '1d' / '۷ روز' / '7d' / 'هفته' -> '24h' / '7d' / '<n>h' / '<n>d'."""
    t = fa.fold(v).replace(" ", "").replace("_", "")
    if t in ("هفته", "یکهفته", "week", "1w", "1week", "هفتگی", "یکهفتهای"):
        return "7d"
    if t in ("روز", "یکروز", "day", "1day", "یکشبانهروز", "یکروزه"):
        return "24h"
    # fold drops the ZWNJ, so «هفته‌ای» arrives as «هفتهای»; longer forms first
    m = re.match(r"^(\d+(?:\.\d+)?)(hours|hour|hrs|hr|h|ساعته|ساعت|days|day|d|روزه|روز"
                 r"|weeks|week|w|هفتهایی|هفتهای|هفته)?$", t)
    if not m:
        raise InputError("زمان بررسی «%s» را نفهمیدم؛ مثلاً 24h یا 7d یا «۷ روز» بنویس." % v)
    n = float(m.group(1))
    unit = m.group(2) or ("d" if n <= 30 and n != 24 and n != 48 else "h")
    if unit in ("w", "week", "weeks", "هفته", "هفتهای", "هفتهایی"):
        n, unit = n * 7, "d"
    if unit in ("h", "hr", "hrs", "hour", "hours", "ساعت", "ساعته"):
        if n != 24 and n > 0 and n % 24 == 0:
            n, unit = n / 24, "d"  # 48h = 2d, 168h = 7d: one name per window
        else:
            return _num_str(n) + "h"
    if n == 1:
        return "24h"
    return _num_str(n) + "d"


_SEC_UNITS = [
    (re.compile(r"(?:hours|hour|hrs|hr|ساعت)"), "h"),
    (re.compile(r"(?:minutes|minute|mins|min|دقیقه)"), "m"),
    (re.compile(r"(?:seconds|second|secs|sec|ثانیه)"), "s"),
]


def _parse_seconds(raw):
    """'83' / '1:23' / '۱:۲۳' / '1m 23s' / '۱ دقیقه و ۲۳ ثانیه' -> 83.0; None when unreadable.
    Count multipliers (K, M, هزار) never apply here: in '1m' the m is minutes."""
    t = fa.normalize(raw, digits="ascii").replace(fa.ZWNJ, " ").lower()
    for rx, u in _SEC_UNITS:
        t = rx.sub(u, t)
    t = re.sub(r"(?<=[hms])\s*و\s*(?=\d)", "", t)
    t = re.sub(r"\s+", "", t)
    if not re.search(r"\d", t):
        return None
    return fa.parse_timestamp(t)


_APPROX_RE = re.compile(
    r"[~≈+]|(?:^|\s)(?:حدود|حدودا|تقریبا|بیش|بیشتر|بالای|زیر|کمتر|نزدیک|کم\s*و\s*بیش"
    r"|over|about|approx|approximately|around|under|almost)(?=\s|\d|$)", re.I)
# a dash / «تا» BETWEEN two numbers is a range; '/' is left out because «۱/۵» is a decimal
_RANGE_RE = re.compile(r"\d\s*(?:[kmb]|هزار|میلیون|ملیون|میلیارد)?\s*(?:تا|-|–|—|to)\s*\d", re.I)
_SCALE_WORDS = (("میلیارد", 1e9), ("میلیون", 1e6), ("ملیون", 1e6), ("هزار", 1e3))
_NUM_WORDS = frozenset(fa._FA_WORD_NUM) | frozenset(fa._FA_WORD_SCALE) | {"نیم"}
_SPACED_GROUPS = re.compile(r"(?<![\d.,٫٬])\d{1,3}(?:[   ]\d{3})+(?![\d.,٫٬])")


def _strip_units(t):
    words = t.split()
    while words and fa.fold(words[-1]) in fa._UNIT_WORDS:
        words.pop()
    return " ".join(words)


def _compound(t):
    """«۱۲ هزار و ۴۰۰» -> 12400, «۱ میلیون و ۲۰۰ هزار» -> 1200000; None unless the whole text is that shape."""
    parts = [p.strip() for p in re.split(r"\s+و\s*|(?<=[^\d\s])و\s+", t)]
    if len(parts) < 2 or any(not p for p in parts):
        return None
    total, last_scale = 0.0, None
    for i, p in enumerate(parts):
        scale = None
        for w, mult in _SCALE_WORDS:
            if p.endswith(w):
                scale, body = mult, p[:-len(w)].strip()
                break
        if scale is None:
            if i != len(parts) - 1:
                return None
            body = p
        if re.fullmatch(r"\d+(?:[.٫/]\d+)?", body):
            v = fa.parse_number(body)
        elif body and not re.search(r"\d", body):
            v = fa._spelled_number(body)
        elif scale and not body:
            v = 1.0
        else:
            return None
        if v is None:
            return None
        step = scale or 1.0
        if last_scale is not None and (step >= last_scale or v * step >= last_scale):
            return None  # «۱ هزار و ۲ میلیون» or «۱ هزار و ۲۰۰۰» is not a compound number
        total += v * step
        last_scale = step
    return total


def _parse_count(col, raw, kind):
    """Parse a whole cell as ONE number, or None. Never keep the first number and drop the rest."""
    bad = InputError("«%s=%s»: این عدد را مطمئن نمی‌توانم بخوانم؛ آن را یکجا بنویس، مثلاً 12400 یا ۱۲٬۴۰۰."
                     % (col, raw))
    t = fa.normalize(raw, digits="ascii").replace(fa.ZWNJ, " ")
    t = _SPACED_GROUPS.sub(lambda m: re.sub(r"[   ]", "", m.group(0)), t)
    core = _strip_units(t)
    if kind == "count" and re.fullmatch(r"\d{1,3}\.000", core):
        raise InputError("«%s=%s»: معلوم نیست نقطه اینجا ممیز است یا جداکننده‌ی هزارگان؛ "
                         "بنویس %s یا %s." % (col, raw, core.replace(".", ""), core.split(".")[0]))
    if re.search(r"\d", core) and re.search(r"(?:^|\s|(?<=[^\d\s]))و(?:\s|$)", core):
        v = _compound(core)
        if v is None:
            raise bad
        return v
    v = fa.parse_number(t)
    if v is None:
        return None
    m = fa._NUM.search(t)
    if not m:
        return v  # spelled-out number: parse_number already insists on the whole text
    rest = t[m.end():].lstrip()
    low = rest.lower()
    for word, _mult in fa._MULT:
        if low.startswith(word):
            after = low[len(word):len(word) + 1]
            if after and after.isalpha() and (word.isascii() or len(word) < 3):
                continue
            rest = rest[len(word):]
            break
    left = t[:m.start()] + " " + rest
    if re.search(r"\d", left) or any(fa.fold(w) in _NUM_WORDS for w in re.split(r"[\s،,]+", left) if w):
        raise bad
    return v


def parse_value(col, raw):
    """Clean one cell. Empty stays empty; anything that is not clearly a number is an error."""
    raw = (raw or "").strip()
    kind = KIND[col]
    if raw == "" or raw in ("-", "—", "?"):
        if col in REQUIRED:
            raise InputError("«%s» (%s) نباید خالی باشد." % (col, LABEL[col]))
        return ""
    if kind == "text":
        return fa.normalize(raw).replace("\n", " ")
    if kind in ("platform", "format"):
        table, names, what = ((_PLATFORM, FA_PLATFORM, "پلتفرم") if kind == "platform"
                              else (_FORMAT, FA_FORMAT, "فرمت"))
        hit = table.get(_pkey(raw))
        if hit:
            return hit
        raise InputError("%s «%s» را نمی‌شناسم. یکی از این‌ها را بنویس: %s. "
                         "پلتفرم و فرمت را جدا بنویس (مثلاً platform=youtube format=short)."
                         % (what, raw, "، ".join("%s (%s)" % (k, names[k]) for k in names)))
    if kind == "checked":
        return norm_checked(raw)
    if kind == "auto":
        return fa.normalize(raw)
    t = fa.normalize(raw, diacritics=True, digits="ascii").replace(fa.ZWNJ, " ")
    if _APPROX_RE.search(t) or _RANGE_RE.search(t):
        raise InputError("«%s=%s»: عدد تقریبی یا بازه ثبت نمی‌شود؛ همان عدد دقیقی را که Insights "
                         "یا Studio نشان می‌دهد بنویس." % (col, raw))
    if kind == "seconds":
        v = _parse_seconds(raw)
        if v is None:
            raise InputError("«%s=%s»: زمان را به شکل ۸۳ یا 1:23 یا «۱ دقیقه و ۲۳ ثانیه» بنویس." % (col, raw))
        return _num_str(v)
    v = _parse_count(col, raw, kind)
    if v is None:
        raise InputError("«%s=%s»: عددی پیدا نکردم. عدد واقعی را بنویس یا خالی بگذار؛ حدس نمی‌زنیم."
                         % (col, raw))
    if v < 0:
        raise InputError("«%s=%s»: عدد منفی معنا ندارد." % (col, raw))
    if kind == "count" and abs(v - round(v)) > 1e-6:
        # 1.25K -> 1250 is fine, but 12.5 likes is not a count
        raise InputError("«%s=%s»: شمارش باید عدد صحیح باشد." % (col, raw))
    if kind == "pct" and v > 100:
        raise InputError("«%s=%s»: درصد باید بین ۰ تا ۱۰۰ باشد." % (col, raw))
    return _num_str(v)


def parse_pairs(pairs):
    row = {}
    for p in pairs:
        if "=" not in p:
            raise InputError("«%s» به شکل key=value نیست (مثلاً views=۱۲ هزار)." % p)
        k, v = p.split("=", 1)
        if _key(k.strip()) in AMBIGUOUS_KEYS:
            raise InputError("«%s» دوپهلوست: برای share بنویس «اشتراک‌گذاری» و برای سابسکرایب بنویس "
                             "«سابسکرایب»." % k.strip())
        col = _ALIAS.get(_key(k.strip()))
        if col is None or col == "logged_on":
            raise InputError("ستون «%s» را نمی‌شناسم. فهرست ستون‌ها: python3 -I results.py --fields" % k)
        if col in row:
            raise InputError("ستون «%s» دو بار آمده." % col)
        row[col] = parse_value(col, v)
    missing = [c for c in REQUIRED if not row.get(c)]
    if missing:
        raise InputError("این ستون‌ها لازم‌اند: %s" % "، ".join(missing))
    return row


def fnum(v):
    """Float from a stored cell, None when empty."""
    if v is None:
        return None
    v = str(v).strip()
    if not v:
        return None
    return fa.parse_number(v)


# ---------------------------------------------------------------- csv

def read_log(path):
    if not os.path.exists(path):
        return [], []
    if os.path.isdir(path):
        raise InputError("«%s» یک پوشه است، نه فایل CSV." % path)
    with io.open(path, "rb") as f:
        data = f.read()
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        raise InputError("«%s» با UTF-16 ذخیره شده؛ در Excel گزینه‌ی «CSV UTF-8» را انتخاب کن." % path)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InputError("«%s» با UTF-8 ذخیره نشده؛ در Excel آن را با «CSV UTF-8» ذخیره کن." % path)
    if not text.strip():
        return [], []
    rows = []
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""))
        header = [h.strip() for h in (reader.fieldnames or [])]
        unknown_req = [c for c in REQUIRED if c not in header]
        if unknown_req:
            raise InputError("سرستون فایل «%s» این ستون‌ها را ندارد: %s" % (path, "، ".join(unknown_req)))
        for r in reader:
            row = {(k or "").strip(): (v or "").strip() for k, v in r.items() if k is not None}
            # hand edits in Excel/Sheets ('Instagram', 'Reels', '24 h') must group with the tool's own rows
            for col in ("platform", "format", "checked_at", "video_id"):
                if row.get(col):
                    try:
                        row[col] = parse_value(col, row[col])
                    except InputError:
                        pass  # keep the cell as written; one odd cell must not stop the report
            rows.append(row)
    except csv.Error as e:
        raise InputError("فایل «%s» CSV سالم نیست (%s)." % (path, e))
    return header, rows


def _write_all(path, header, rows):
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({h: r.get(h, "") for h in header})
    os.replace(tmp, path)


def add_row(path, row, replace=False, today=None):
    header, rows = read_log(path)
    row = dict(row)
    row["logged_on"] = today or datetime.date.today().isoformat()
    same = [i for i, r in enumerate(rows)
            if vid_key(r.get("video_id")) == vid_key(row["video_id"]) and r.get("platform") == row["platform"]
            and r.get("checked_at") == row["checked_at"]]
    if same and not replace:
        raise InputError("برای «%s» (%s، %s) قبلاً ردیف ثبت شده. برای جایگزینی --replace بزن."
                         % (row["video_id"], row["platform"], row["checked_at"]))
    new_header = list(header) if header else list(COLUMNS)
    for c in COLUMNS:
        if c not in new_header:
            new_header.append(c)
    if same:
        rows[same[0]] = row
        rows = [r for i, r in enumerate(rows) if i not in same[1:]]
        _write_all(path, new_header, rows)
        return "replaced"
    # always rewrite (atomic): appending to a file whose last line has no newline merges two rows
    _write_all(path, new_header, rows + [row])
    return "created" if not header else "appended"


# ---------------------------------------------------------------- maths

def rates(r):
    """Per-1k rates and the comparable metrics of one row; None where a number is missing."""
    views = fnum(r.get("views"))
    out = {"views": views}
    for f in RATE_FIELDS:
        n = fnum(r.get(f))
        out[f + "_1k"] = (n * 1000.0 / views) if (n is not None and views) else None
    out["non_follower_pct"] = fnum(r.get("non_follower_pct"))
    out["avg_watch_s"] = fnum(r.get("avg_watch_s"))
    return out


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return None
    mid = n // 2
    return xs[mid] if n % 2 else (xs[mid - 1] + xs[mid]) / 2.0


def group_of(r):
    return (r.get("platform", ""), r.get("format", ""), r.get("checked_at", ""))


def baseline(rows, idx):
    """Earlier rows (file order) of the same platform+format+checked_at, other videos only."""
    target = rows[idx]
    g = group_of(target)
    tv = vid_key(target.get("video_id"))
    return [r for r in rows[:idx] if group_of(r) == g and vid_key(r.get("video_id")) != tv]


def verdict(mult):
    if mult is None:
        return None
    mult = round(mult, 1)  # same value the report prints, so «۱٫۵×» is never "normal"
    if mult >= HIGH:
        return "high"
    if mult <= LOW:
        return "low"
    return "normal"


def _inherit(rows, r):
    """A 7d row may leave title/tested empty: take them from the same video's other row."""
    r = dict(r)
    for c in ("title", "tested"):
        if not r.get(c):
            for o in rows:
                if vid_key(o.get("video_id")) == vid_key(r.get("video_id")) \
                        and o.get("platform") == r.get("platform") and o.get(c):
                    r[c] = o[c]
                    break
    return r


def analyse(rows, idx):
    rows = [_inherit(rows, x) for x in rows]
    r = rows[idx]
    mine = rates(r)
    base = baseline(rows, idx)
    base_rates = [rates(b) for b in base]
    metrics = []
    for m in COMPARE_FIELDS:
        vals = [b[m] for b in base_rates if b[m] is not None]
        med = median(vals) if len(vals) >= MIN_BASELINE else None
        mult = None
        zero_high = False
        if mine[m] is not None and med is not None:
            if med > 0:
                mult = mine[m] / med
            elif mine[m] > 0:
                zero_high = True  # earlier videos had none at all: clearly above, but no multiple
        v = "high" if zero_high else verdict(mult)
        if med == 0 and mine[m] == 0:
            v = "normal"
        metrics.append({"metric": m, "value": mine[m], "baseline_n": len(vals), "median": med,
                        "multiple": mult, "verdict": v, "zero_median": med == 0})
    # same tested idea strong on the same metric in another video -> confirmed
    confirm = {}
    tested = fa.fold(r.get("tested", "")).strip()
    if tested:
        for m in metrics:
            if m["verdict"] != "high":
                continue
            others = []
            for j, o in enumerate(rows):
                if j == idx or vid_key(o.get("video_id")) == vid_key(r.get("video_id")):
                    continue
                if group_of(o) != group_of(r) or fa.fold(o.get("tested", "")).strip() != tested:
                    continue
                ob = [rates(b)[m["metric"]] for b in baseline(rows, j)]
                ob = [x for x in ob if x is not None]
                ov = rates(o)[m["metric"]]
                mo = median(ob) if len(ob) >= MIN_BASELINE else None
                if ov is not None and mo is not None and (
                        (mo > 0 and verdict(ov / mo) == "high") or (mo == 0 and ov > 0)):
                    others.append(o.get("video_id"))
            confirm[m["metric"]] = others
    growth = None
    if r.get("checked_at") == "7d":
        for o in rows:
            if (vid_key(o.get("video_id")), o.get("platform"), o.get("checked_at")) == \
                    (vid_key(r.get("video_id")), r.get("platform"), "24h"):
                v24, v7 = fnum(o.get("views")), fnum(r.get("views"))
                if v24 and v7 is not None:
                    growth = v7 / v24
    missing = [c for c in ("views", "follows", "saves", "shares", "comments", "likes", "non_follower_pct")
               if fnum(r.get(c)) is None]
    return {"row": r, "rates": mine, "baseline_n": len(base), "metrics": metrics, "confirm": confirm,
            "growth_7d_vs_24h": growth, "missing": missing}


# ---------------------------------------------------------------- output

def fanum(v, digits=1):
    if v is None:
        return "—"
    if abs(v) >= 100 or abs(v - round(v)) < 1e-9:
        s = "{:,}".format(int(round(v)))
    else:
        d = digits
        if abs(v) < 1:
            d = 2
            while d < 4 and round(abs(v), d) == 0:  # never print a small rate as ۰٫۰۰: 0.05, 0.004
                d += 1
        s = ("%." + str(d) + "f") % v
    return fa.to_fa_digits(s, separators=True)


def fmult(m):
    return "—" if m is None else fa.to_fa_digits("%.1f" % m, separators=True) + "×"


def _desc(r):
    p = FA_PLATFORM.get(r.get("platform"), r.get("platform"))
    f = FA_FORMAT.get(r.get("format"), r.get("format"))
    c = r.get("checked_at", "")
    mc = re.fullmatch(r"(\d+(?:\.\d+)?)([hd])", c)
    if mc:
        c = "%s %s" % (fa.to_fa_digits(mc.group(1), separators=True), "ساعت" if mc.group(2) == "h" else "روز")
    else:
        c = fa.to_fa_digits(c)
    return p, f, c


def report_text(a):
    r = a["row"]
    p, f, c = _desc(r)
    out = []
    title = (" - " + r["title"]) if r.get("title") else ""
    out.append("نتیجه‌ی «%s»%s" % (r.get("video_id"), title))
    out.append("%s · %s · بعد از %s" % (p, f, c))
    if r.get("tested"):
        out.append("این بار امتحان کردی: %s" % r["tested"])
    out.append("")
    if a["rates"]["views"] is None:
        out.append("بازدید خالی است، پس نرخ در هر ۱۰۰۰ بازدید حساب نمی‌شود. عدد بازدید را از Insights / Studio بردار.")
    elif a["rates"]["views"] == 0:
        out.append("بازدید صفر است، پس نرخی حساب نمی‌شود.")
    enough = a["baseline_n"] >= MIN_BASELINE
    if not enough:
        have = ("هنوز هیچ ردیف قبلی از ویدیوهای دیگر نداری" if a["baseline_n"] == 0 else
                "فقط %s ردیف قبلی از ویدیوهای دیگر داری" % fanum(a["baseline_n"]))
        out.append("مقایسه هنوز ممکن نیست: برای %s، %s، %s %s و دست‌کم %s تا لازم است."
                   % (p, f, c, have, fanum(MIN_BASELINE)))
        out.append("فعلاً فقط نرخ‌ها را ثبت کن؛ با چند ویدیوی دیگر میانه معنا پیدا می‌کند.")
        out.append("")
    for m in a["metrics"]:
        if not enough:
            out.append("- %s: %s" % (METRIC_LABEL[m["metric"]], fanum(m["value"])))
            continue
        if m["median"] is not None:
            med = "میانه %s" % fanum(m["median"])
        else:
            med = "میانه: کمتر از %s ردیف قبلی با این عدد" % fanum(MIN_BASELINE)
        tag = {"high": " ▲ بالاتر از معمول", "low": " ▼ پایین‌تر از معمول", "normal": " در حد معمول"}.get(
            m["verdict"], "")
        if m["multiple"] is not None:
            mult = " · " + fmult(m["multiple"]) + tag
        elif m.get("zero_median") and m["verdict"] == "high":
            mult = " ·" + tag + " (میانه‌ی قبلی صفر بود، ضریب حساب نمی‌شود)"
        elif m.get("zero_median") and m["verdict"] == "normal":
            mult = " ·" + tag
        else:
            mult = ""
        out.append("- %s: %s · %s%s" % (METRIC_LABEL[m["metric"]], fanum(m["value"]), med, mult))
    extra = []
    if a["growth_7d_vs_24h"] is not None:
        extra.append("رشد بازدید از ۲۴ ساعت تا ۷ روز: %s" % fmult(a["growth_7d_vs_24h"]))
    if a["missing"]:
        extra.append("خالی مانده (حدس نزدیم؛ اگر عددش را داری اضافه کن): %s"
                     % "، ".join(LABEL[m] for m in a["missing"]))
    if extra:
        out.append("")
        out.extend(extra)
    highs = [m for m in a["metrics"] if m["verdict"] == "high" and m["metric"] != "views"]
    lows = [m for m in a["metrics"] if m["verdict"] == "low" and m["metric"] != "views"]
    names = lambda ms: "، ".join("%s (%s)" % (
        METRIC_LABEL[m["metric"]], "میانه ۰" if m["multiple"] is None and m.get("zero_median")
        else fmult(m["multiple"])) for m in ms)
    out.append("")
    out.append("چه چیزی را تکرار کنیم؟")
    if not enough:
        out.append("- هنوز زود است. یک ویدیو چیزی را ثابت نمی‌کند؛ اول مبنا را بساز.")
    elif not highs:
        out.append("- هیچ نرخی به‌وضوح بالاتر از معمول نیست؛ چیزی برای تکرار ثابت نشده.")
    else:
        confirmed = [m for m in highs if a["confirm"].get(m["metric"])]
        open_ = [m for m in highs if not a["confirm"].get(m["metric"])]
        if confirmed:
            others = sorted({v for m in confirmed for v in a["confirm"][m["metric"]]})
            out.append("- تأییدشده: همین الگو با «%s» در %s هم دیده شد: %s. ارزش تکرار دارد."
                       % (r["tested"], "، ".join(others), names(confirmed)))
        if open_:
            out.append("- بالاتر از معمول: %s." % names(open_))
            if r.get("tested"):
                out.append("- فرضیه: «%s» باعثش شده. یک ویدیو چیزی را ثابت نمی‌کند؛ "
                           "در ویدیوی بعدی همین را تکرار کن و اگر دوباره بالا بود، تأییدش کن." % r["tested"])
            else:
                out.append("- فرضیه هنوز نداری: بنویس این بار چه چیزی فرق داشت (tested=\"...\") "
                           "تا در ویدیوی بعدی آزمایشش کنی.")
    if enough and lows:
        out.append("- پایین‌تر از معمول: %s. ببین این بار چه چیزی کم بود." % names(lows))
    return "\n".join(out)


def table_text(rows):
    out = ["%-14s %-10s %-8s %-6s %10s %8s %8s %8s %8s" % (
        "ویدیو", "پلتفرم", "فرمت", "زمان", "بازدید", "فالو/هزار", "سیو/هزار", "اشتراک‌گذاری/هزار", "کامنت/هزار")]
    for r in rows:
        k = rates(r)
        p, f, c = _desc(r)
        out.append("%-14s %-10s %-8s %-6s %10s %8s %8s %8s %8s" % (
            r.get("video_id", ""), p, f, c, fanum(k["views"]), fanum(k["follows_1k"]), fanum(k["saves_1k"]),
            fanum(k["shares_1k"]), fanum(k["comments_1k"])))
    return "\n".join(out)


def fields_text():
    out = ["ستون‌ها (نام انگلیسی = نام‌های فارسی که هم قبول می‌شود):"]
    for col, kind, label in FIELDS:
        if col == "logged_on":
            out.append("  %-17s %s (خودکار)" % (col, label))
            continue
        names = "، ".join(n for n in ALIASES.get(col, []) if not n.isascii())
        req = " - لازم" if col in REQUIRED else ""
        out.append("  %-17s %s%s%s" % (col, label, ("   [" + names + "]") if names else "", req))
    out.append("")
    out.append("پلتفرم: " + "، ".join("%s (%s)" % (k, FA_PLATFORM[k]) for k in PLATFORMS))
    out.append("فرمت:   " + "، ".join("%s (%s)" % (k, FA_FORMAT[k]) for k in FORMATS))
    out.append("زمان بررسی: 24h یا 7d (یا «۲۴ ساعت»، «۲۴ ساعته»، «۷ روز»، «۷ روزه»، «هفته»)")
    out.append("عددها: ۱۲٬۴۰۰، 12,400، ۱۲ ۴۰۰، ۱۲٫۴ هزار، ۱۲ هزار و ۴۰۰، 12.4K، ۱/۵ میلیون، «سیصد هزار»، "
               "۸۷٪ - همه قبول است. عدد تقریبی یا بازه («حدود ۲۰۰»، «۲۲۰ تا ۲۵۰») قبول نیست.")
    out.append("میانگین زمان تماشا: ۸۳، 1:23، ۱:۲۳، 1m 23s یا «۱ دقیقه و ۲۳ ثانیه».")
    return "\n".join(out)


USAGE = """استفاده:
  python3 -I results.py --log results.csv --add video_id=ID platform=instagram format=reel checked_at=24h views=12.4K ...
  python3 -I results.py --log results.csv --add ... --replace      (ردیف همان ویدیو/پلتفرم/زمان را عوض کن)
  python3 -I results.py --log results.csv --report [--video ID] [--checked 24h|7d] [--json]
  python3 -I results.py --log results.csv --report --all [--json]
  python3 -I results.py --fields
عددی که نداری را ننویس؛ خالی می‌ماند. هیچ عددی حدس زده نمی‌شود."""


def parse_args(argv):
    opts = {"log": None, "add": None, "report": False, "video": None, "checked": None, "json": False,
            "all": False, "replace": False, "fields": False, "today": None}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            opts["help"] = True
            i += 1
        elif a == "--add":
            opts["add"] = opts["add"] or []
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                opts["add"].append(argv[i])
                i += 1
        elif a.startswith("--") and "=" in a and a.split("=", 1)[0] in ("--log", "--video", "--checked", "--today"):
            k, v = a[2:].split("=", 1)
            opts[k] = v
            i += 1
        elif a in ("--log", "--video", "--checked", "--today"):
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                raise InputError("«%s» مقدار می‌خواهد." % a)
            opts[a[2:]] = argv[i + 1]
            i += 2
        elif a in ("--report", "--json", "--all", "--replace", "--fields"):
            opts[a[2:]] = True
            i += 1
        else:
            raise InputError("«%s» را نمی‌شناسم." % a)
    return opts


def _join_spaced_values(pairs):
    """`views=۱۲ هزار` arrives as two argv items ('views=۱۲', 'هزار'): glue words without '=' back on."""
    out = []
    for p in pairs:
        if "=" not in p and out:
            out[-1] += " " + p
        else:
            out.append(p)
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        opts = parse_args(argv)
        if opts.get("help") or not argv:
            print(USAGE)
            return 0 if opts.get("help") else 2
        if opts["fields"]:
            print(fields_text())
            return 0
        if not opts["log"]:
            raise InputError("--log results.csv را بده.")
        if opts["add"] is not None:
            if not opts["add"]:
                raise InputError("بعد از --add دست‌کم video_id، platform، format و checked_at را بده.")
            row = parse_pairs(_join_spaced_values(opts["add"]))
            status = add_row(opts["log"], row, replace=opts["replace"], today=opts["today"])
            msg = {"created": "فایل ساخته شد و ردیف اول ثبت شد", "appended": "ردیف ثبت شد",
                   "replaced": "ردیف قبلی جایگزین شد"}[status]
            filled = [c for c in COLUMNS if row.get(c) and c not in REQUIRED and c != "logged_on"]
            print("%s: %s · %s · %s · %s" % (msg, row["video_id"], row["platform"], row["format"],
                                            row["checked_at"]))
            print("ستون‌های پرشده: %s" % ("، ".join(LABEL[c] for c in filled) if filled else "هیچ (فقط شناسه)"))
            if not opts["report"]:
                return 0
        if not opts["report"]:
            raise InputError("بگو چه کنم: --add یا --report")
        header, rows = read_log(opts["log"])
        if not rows:
            raise InputError("در «%s» هنوز ردیفی نیست. اول با --add ثبت کن." % opts["log"])
        if opts["all"]:
            if opts["json"]:
                print(json.dumps([dict(r, **{k: v for k, v in rates(r).items()}) for r in rows],
                                 ensure_ascii=False, indent=2))
            else:
                print(table_text(rows))
            return 0
        idx = len(rows) - 1
        if opts["video"] or opts["checked"]:
            want_c = norm_checked(opts["checked"]) if opts["checked"] else None
            want_v = vid_key(opts["video"]) if opts["video"] else None
            hits = [i for i, r in enumerate(rows)
                    if (want_v is None or vid_key(r.get("video_id")) == want_v)
                    and (want_c is None or r.get("checked_at") == want_c)]
            if not hits:
                raise InputError("ردیفی با این شناسه/زمان پیدا نشد.")
            idx = hits[-1]
        a = analyse(rows, idx)
        if opts["json"]:
            print(json.dumps(a, ensure_ascii=False, indent=2))
        else:
            print(report_text(a))
        return 0
    except InputError as e:
        print("خطا: %s" % e, file=sys.stderr)
        return 2
    except OSError as e:
        print("خطا: فایل خوانده یا نوشته نشد (%s)." % e.strerror, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
