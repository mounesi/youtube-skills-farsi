#!/usr/bin/env python3
"""swipe.py - ویدیوها و ریلزها را بر اساس اینکه چند برابرِ میانه‌ی خودِ کانال/اکانت دیده شده‌اند رتبه می‌دهد
و فرمول عنوان (یا خط اول کپشن) را نام می‌برد.

    python3 -I swipe.py a.json b.json c.json        (یک فایل برای هر کانال)
    python3 -I swipe.py a.json b.json --min 2 --json
    python3 -I swipe.py reels.csv --min ۳
    python3 -I swipe.py search.json --phrase "آموزش کلاد"

ورودی (JSON یا CSV) - هر ردیف یک ویدیو یا ریلز:

    [{"channel": "...", "title": "...", "views": 412000, "url": "..."}, ...]
    [{"account": "@...", "caption": "...", "plays": "۱۲ هزار"}, ...]        (اینستاگرام)

این‌ها هم همان‌طور که هستند خوانده می‌شوند: {"videos": [...]}، {"reels": [...]}، خروجی
`yt-dlp --flat-playlist -J` (entries و view_count)، خروجی `yt-dlp -j` (هر خط یک ویدیو)، و خروجی اسکرپرهای اینستاگرام
(ownerUsername، videoPlayCount، videoViewCount). ستون‌های CSV می‌توانند فارسی باشند:
کانال/اکانت، عنوان/کپشن، بازدید/پلی، لینک.

عدد بازدید به هر شکلی خوانده می‌شود: 412000، "12,400"، "۱۲ هزار بازدید"، "1.2K views"، "۱٫۲ میلیون".
ردیفی که عدد بازدید ندارد (لایو، هنوز پخش‌نشده، پریمیر) کنار گذاشته می‌شود و صفر حساب نمی‌شود.

عدد خامِ بازدید اندازه‌ی کانال را نشان می‌دهد، نه قدرت ایده را. هر ویدیو «چند برابرِ میانه‌ی
کانال خودش» سنجیده می‌شود و برای این کار دست‌کم ۴ ویدیو از هر کانال/اکانت لازم است؛ کمتر از آن
کنار گذاشته می‌شود و ابزار این را می‌گوید.

فرمول از ../yt-script/hooks.json خوانده می‌شود (اگر نبود، از hooks.json همین پوشه). این قضاوتی
درباره‌ی کلمات عنوان است، نه ادعایی درباره‌ی دلیل موفقیت ویدیو.

با --phrase، روی نتایج جست‌وجو (مثلاً yt-dlp -J "ytsearch20:عبارت") عرضه‌ی آن عبارت را می‌شمارد:
چند تا از ۱۰ عنوان اول عبارت را عیناً دارند، چند تا از کانال‌های کوچک‌تر از بازدیدشان آمده‌اند.
"""
import argparse, csv, datetime, io, json, math, os, re, statistics, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _fatext as fa  # noqa: E402

MIN_PER_CHANNEL = 4
HOOK_FILES = (os.path.join(HERE, "..", "yt-script", "hooks.json"), os.path.join(HERE, "hooks.json"))


def _load_formulas():
    """Prefer yt-script's hooks.json (same formulas as hookscore.py); else the bundled copy."""
    for path in HOOK_FILES:
        try:
            with open(path, encoding="utf-8-sig") as fh:
                hooks = json.load(fh).get("hooks") or []
        except (OSError, ValueError, AttributeError):
            continue
        out = []
        for f in hooks:
            if not isinstance(f, dict) or not f.get("name"):
                continue
            pats = []
            for key in ("match", "match_fa", "match_en"):
                for p in f.get(key) or []:
                    try:
                        pats.append(re.compile(p, re.I))
                    except (re.error, TypeError):
                        pass
            out.append({"name": f["name"], "fa": f.get("name_fa") or f.get("fa") or f["name"], "pats": pats})
        return out, path
    return [], None


FORMULAS, FORMULAS_FILE = _load_formulas()
UNCLASSIFIED = "Unclassified"
UNCLASSIFIED_FA = "بدون فرمول شناخته‌شده"


_MATCH_PUNCT = {ord("٬"): ",", ord("٫"): ".", ord("٪"): "%"}


def match_text(title):
    """The form hooks.json patterns run on (its "match_on"): fold() plus ٬ ٫ ٪ -> , . %"""
    return fa.fold(title or "").translate(_MATCH_PUNCT)


def _formula(title):
    # Same text and tie-break as yt-script/hookscore.py: most matching patterns wins; on a tie the
    # formula listed first in hooks.json wins.
    t = match_text(title)
    best, hits = None, 0
    for f in FORMULAS:
        n = sum(1 for p in f["pats"] if p.search(t))
        if n > hits:
            best, hits = f, n
    return best


def classify(title):
    f = _formula(title)
    return f["name"] if f else UNCLASSIFIED


def classify_fa(title):
    f = _formula(title)
    return f["fa"] if f else UNCLASSIFIED_FA


# ---- reading rows -------------------------------------------------------------------------------

def _k(key):
    return re.sub(r"[\s_\-]+", "", fa.fold(str(key)))


def _keys(*names):
    return tuple(_k(n) for n in names)


VIEW_KEYS = _keys("views", "view_count", "viewCount", "videoViewCount", "plays", "play_count", "playCount",
                  "videoPlayCount", "ig_play_count", "بازدید", "بازدیدها", "ویو", "پلی", "تعداد بازدید")
# Two different metrics: Instagram "views" and "plays" are not the same count, so one account is only
# ever measured on one of them (the one most of its rows have). Spellings inside a family are the same metric.
PLAY_KEYS = _keys("plays", "play_count", "playCount", "videoPlayCount", "ig_play_count", "پلی")
METRIC_FA = {"views": "بازدید", "plays": "پلی"}
CHANNEL_KEYS = _keys("channel", "uploader", "account", "username", "ownerUsername", "owner", "handle",
                     "کانال", "اکانت", "حساب", "پیج")
TITLE_KEYS = _keys("title", "caption", "text", "عنوان", "کپشن", "متن")
URL_KEYS = _keys("url", "webpage_url", "link", "permalink", "لینک", "آدرس")
SUBS_KEYS = _keys("subscribers", "channel_follower_count", "followers", "followersCount", "سابسکرایبر",
                  "مشترک", "فالوور", "دنبال‌کننده")
KID_KEYS = _keys("videos", "entries", "reels", "items", "posts", "ویدیوها", "ریلزها")
# Key names are only a weak hint of the platform (a YouTube sheet can have a "caption" column), so they
# are used only when a channel has no platform field and no youtube/instagram URL at all.
IG_ONLY_HINTS = set(_keys("plays", "play_count", "playCount", "videoPlayCount", "videoViewCount", "ownerUsername",
                          "shortCode", "ig_play_count", "پلی", "پیج"))
IG_SOFT_HINTS = set(_keys("account", "caption", "اکانت", "کپشن"))
YT_HINTS = set(_keys("channel", "uploader", "uploader_id", "channel_id", "title", "view_count",
                     "channel_follower_count", "کانال", "عنوان"))
FORMAT_FA = {"video": "ویدیو", "short": "شورتس", "live": "لایو"}


def _metric(key):
    return "plays" if key in PLAY_KEYS else "views"


def _index(d):
    idx = {}
    for key, val in d.items():
        idx.setdefault(_k(key), val)
    return idx


def _get(d, keys):
    """First non-empty value whose (folded) key is in keys, in the order keys are listed."""
    idx = _index(d)
    for key in keys:
        val = idx.get(key)
        if isinstance(val, dict):  # e.g. {"owner": {"username": "x"}}
            val = val.get("username") or val.get("name")
        if val is not None and str(val).strip() != "":
            return val
    return None


def _view_fields(d):
    """{metric family: first non-empty value of that family}, in VIEW_KEYS order."""
    idx, out = _index(d), {}
    for key in VIEW_KEYS:
        val = idx.get(key)
        if val is None or isinstance(val, (dict, list)) or str(val).strip() == "":
            continue
        out.setdefault(_metric(key), val)
    return out


_SCI = re.compile(r"[+]?\d+(?:\.\d+)?[eE][+-]?\d+")
_SPACE_GROUP = re.compile(r"\d[   ]\d{3}(?!\d)")
_SPACE_GROUPED = re.compile(r"\d{1,3}(?:[   ]\d{3})+")


def _num(x):
    """A count as a float, or None when it is missing/unknown/infinite. Never guesses."""
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        try:
            n = float(x)
        except OverflowError:  # a 400-digit JSON integer
            return None
    else:
        t = fa.normalize(str(x), digits="ascii").strip()
        if _SCI.fullmatch(t):
            n = float(t)                       # "1.2E+06" is 1200000, not 1.2
        elif re.search(r"\d[eE][+-]?\d", t):
            return None                        # "1.2e6 views": not read as 1.2
        elif _SPACE_GROUP.search(t):
            if not _SPACE_GROUPED.fullmatch(t):
                return None                    # "12 400 views": not read as 12
            n = float(re.sub(r"\s", "", t))    # "12 400" / "1 234 567"
        else:
            n = fa.parse_number(t)
    if n is None or not math.isfinite(n) or n < 0:
        return None
    return n


def _views(v):
    return _num(v.get("views"))


def _platform_word(p):
    p = str(p or "").strip().lower()
    if p in ("instagram", "ig", "insta", "اینستاگرام", "اینستا"):
        return "instagram"
    if p in ("youtube", "yt", "یوتیوب"):
        return "youtube"
    return None


def _url_platform(url):
    u = (url or "").lower()
    if "instagram.com" in u:
        return "instagram"
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    return None


def _guess_platform(node):
    """Weak guess from key names only (for a channel with no platform field and no URL)."""
    keys = {_k(x) for x in node}
    ig = 2 * len(keys & IG_ONLY_HINTS) + len(keys & IG_SOFT_HINTS)
    return "instagram" if ig > len(keys & YT_HINTS) else "youtube"


def _first_line(text):
    for line in str(text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def _tab_format(node):
    """yt-dlp channel tab ("X - Shorts", .../shorts) -> its format, else None."""
    title = str(node.get("title") or "").strip().lower()
    url = str(node.get("webpage_url") or node.get("url") or "").strip().lower().rstrip("/")
    for fmt, word, path in (("short", "shorts", "/shorts"), ("live", "live", "/streams"),
                            ("video", "videos", "/videos")):
        if re.search(r"(^|-\s*)%s$" % word, title) or url.endswith(path):
            return fmt
    return None


def _flatten(node, parent_ch=None, parent_pf=None, parent_fmt=None):
    """A plain list, {"videos"|"entries"|"reels": [...]}, nested yt-dlp channel tabs, or one row."""
    if isinstance(node, list):
        for x in node:
            yield from _flatten(x, parent_ch, parent_pf, parent_fmt)
        return
    if not isinstance(node, dict):
        return
    ch = _get(node, CHANNEL_KEYS) or parent_ch
    own_pf = _platform_word(node.get("platform") or node.get("پلتفرم"))
    kids = _get(node, KID_KEYS)
    if isinstance(kids, list):
        yield from _flatten(kids, ch or node.get("title"), own_pf or parent_pf, _tab_format(node) or parent_fmt)
        return
    url = str(_get(node, URL_KEYS) or "")
    title = _get(node, TITLE_KEYS)
    fields = _view_fields(node)
    fmt = "short" if "/shorts/" in url.lower() else (parent_fmt or "video")
    yield {"channel": str(ch) if ch is not None else "?", "title": _first_line(title) if title is not None else "",
           "views": next(iter(fields.values()), None), "view_fields": fields, "url": url,
           "platform": own_pf or parent_pf or _url_platform(url), "platform_guess": _guess_platform(node),
           "format": fmt, "subscribers": _get(node, SUBS_KEYS),
           "upload_date": node.get("upload_date") or node.get("timestamp")}


def _chkey(name):
    """Grouping form of a channel/account name: «@Ali »، «ali» و «علي» are one account."""
    return fa.fold(str(name if name is not None else "?")).strip().lstrip("@").strip() or "?"


def _resolve_platforms(rows):
    """One platform per channel where the data says so (platform field or URL, majority of its rows);
    a channel with no such signal falls back to a per-row guess from its key names."""
    votes = {}
    for r in rows:
        if r.get("platform"):
            c = votes.setdefault(_chkey(r["channel"]), {})
            c[r["platform"]] = c.get(r["platform"], 0) + 1
    for r in rows:
        c = votes.get(_chkey(r["channel"]))
        if c:
            r["platform"] = max(sorted(c), key=lambda p: c[p])
        elif not r.get("platform"):
            r["platform"] = r.get("platform_guess") or "youtube"
    return rows


def _pick_metrics(rows):
    """Per account, keep only the metric (views or plays) most of its rows have. Returns the notes
    [(platform, channel name, rows dropped, chosen metric, other metric)]."""
    groups = {}
    for r in rows:
        if "view_fields" in r:
            groups.setdefault((r["platform"], _chkey(r["channel"])), []).append(r)
    notes = []
    for (pf, _), rs in groups.items():
        count = {}
        for r in rs:
            for m, val in r["view_fields"].items():
                if _num(val) is not None:
                    count[m] = count.get(m, 0) + 1
        if not count:
            continue
        chosen = max(("views", "plays"), key=lambda m: count.get(m, 0))  # tie -> views (first in VIEW_KEYS)
        dropped = 0
        for r in rs:
            had = r["view_fields"]
            r["views"] = had.get(chosen)
            if _num(r["views"]) is None and any(_num(v) is not None for m, v in had.items() if m != chosen):
                dropped += 1
        if dropped:
            other = "plays" if chosen == "views" else "views"
            notes.append((pf, str(rs[0]["channel"]).strip() or "?", dropped, chosen, other))
    return notes


def _read(path):
    with open(path, encoding="utf-8-sig") as fh:
        raw = fh.read()
    s = raw.lstrip()
    if s[:1] in "[{":
        try:
            data = json.loads(raw)
        except ValueError as whole:
            # JSON Lines (yt-dlp -j: one object per line) or several JSON documents appended to one
            # file (yt-dlp -J >> all.json), whatever the file extension
            dec, i, data = json.JSONDecoder(), 0, []
            while True:
                while i < len(raw) and raw[i].isspace():
                    i += 1
                if i >= len(raw):
                    break
                try:
                    obj, i = dec.raw_decode(raw, i)
                except ValueError as e:
                    raise (whole if not data else e)
                data.append(obj)
        return list(_flatten(data))
    sample = raw[:4096]
    delim = "\t" if sample.count("\t") > sample.count(",") else ","
    return list(_flatten(list(csv.DictReader(io.StringIO(raw), delimiter=delim))))


# ---- supply check (--phrase) --------------------------------------------------------------------

def _words(text):
    return fa.norm_words(str(text or "").replace(fa.ZWNJ, " "))


def has_phrase(title, phrase):
    """Phrase appears as written (whole words, in order; ZWNJ, space or no gap and ی/ي differences
    ignored: «می‌خوام»، «میخوام» و «می خوام» یکی‌اند، ولی «خوام» با «میخوام» نمی‌خواند)."""
    t, p = _words(title), "".join(_words(phrase))
    if not p:
        return False
    for i in range(len(t)):
        acc = ""
        for j in range(i, len(t)):
            acc += t[j]
            if acc == p:
                return True
            if len(acc) >= len(p) or not p.startswith(acc):
                break
    return False


def _recent(d, today):
    s = fa.to_ascii_digits(str(d or ""))
    try:
        if re.fullmatch(r"\d{8}", s):
            day = datetime.date(int(s[:4]), int(s[4:6]), int(s[6:]))
        elif re.fullmatch(r"\d{9,11}(\.\d+)?", s):
            day = datetime.date.fromtimestamp(float(s))
        else:
            return None
    except (ValueError, OverflowError, OSError):
        return None
    return (today - day).days <= 365


def supply(rows, phrase, top=10, today=None):
    today = today or datetime.date.today()
    top_rows = [r for r in rows if r.get("title")][:top]
    exact = [r for r in top_rows if has_phrase(r["title"], phrase)]
    with_subs, beat, recent_beat = 0, 0, 0
    for r in top_rows:
        n, s = _num(r.get("views")), _num(r.get("subscribers"))
        if n is None or not s:
            continue
        with_subs += 1
        if n > s:
            beat += 1
            if _recent(r.get("upload_date"), today):
                recent_beat += 1
    return {"phrase": phrase, "top": len(top_rows), "exact_phrase": len(exact),
            "with_subscribers": with_subs, "views_beat_subscribers": beat,
            "recent_views_beat_subscribers": recent_beat, "exact_titles": [r["title"] for r in exact]}


# ---- CLI ----------------------------------------------------------------------------------------

class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("swipe.py: خطا در آرگومان‌ها: %s\n" % message)
        sys.exit(2)


def _threshold(s):
    bad = argparse.ArgumentTypeError("--min باید یک عدد مثبت باشد، مثلاً 2 یا ۲٫۵ (نه %r)" % s)
    t = fa.normalize(str(s), digits="ascii").strip()
    try:
        n = float(t)                   # "2", "2.5", "1e3"
    except ValueError:
        if re.search(r"\d[eE]", t) or _SPACE_GROUP.search(t):
            raise bad                  # "1e3x", "1 500": never read as 1 or 1.0
        n = fa.parse_number(t)         # "۲٫۵", "۳"
    if n is None or not math.isfinite(n) or n < 0:
        raise bad
    return n


def F(x, nd=0):
    """Number for the Persian report: Persian digits, ٬ thousands, ٫ decimals."""
    s = ("{:,.%df}" % nd).format(x)
    return fa.to_fa_digits(s, separators=True)


def _label(r):
    return "اینستاگرام" if r == "instagram" else "یوتیوب"


def main():
    p = _Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", nargs="+", help="یک یا چند فایل JSON یا CSV (مثلاً یک فایل برای هر کانال)")
    p.add_argument("--min", type=_threshold, default=1.5, help="حداقل چند برابرِ میانه (پیش‌فرض ۱٫۵)")
    p.add_argument("--json", action="store_true", help="خروجی JSON برای ابزارهای دیگر")
    p.add_argument("--phrase", help="عبارت جست‌وجو برای سنجش عرضه روی نتایج جست‌وجو")
    args = p.parse_args()
    lo = args.min
    for f in args.file:
        if not os.path.isfile(f):
            print(__doc__)
            print("swipe.py: فایل «%s» پیدا نشد." % f, file=sys.stderr)
            sys.exit(1)
    rows = []
    for f in args.file:
        try:
            rows.extend(_read(f))
        except OSError as e:
            print("swipe.py: «%s» خوانده نشد: %s" % (f, e), file=sys.stderr)
            sys.exit(2)
        except (ValueError, csv.Error, UnicodeDecodeError, RecursionError) as e:
            print("swipe.py: «%s» خوانده نشد (JSON یا CSV معتبر نیست): %s" % (f, e), file=sys.stderr)
            sys.exit(2)
    if not rows or not any(_views(v) is not None for v in rows):
        print("swipe.py: در «%s» هیچ ویدیو یا ریلزی با عدد بازدید پیدا نشد. "
              "انتظار می‌رفت فهرستی از {channel, title, views} یا {account, caption, plays}، "
              "{\"videos\": [...]} یا خروجی yt-dlp -J باشد." % "»، «".join(args.file), file=sys.stderr)
        sys.exit(2)

    _resolve_platforms(rows)
    metric_notes = _pick_metrics(rows)

    # group by platform + normalised channel name + format (Shorts / live / long videos: one median each)
    by, names, fmts, unknown = {}, {}, {}, 0
    for r in rows:
        n = _views(r)
        if n is None:
            unknown += 1
            continue
        ck = (r["platform"], _chkey(r["channel"]))
        names.setdefault(ck, str(r["channel"]).strip() or "?")
        fmt = r.get("format") or "video"
        fmts.setdefault(ck, set()).add(fmt)
        by.setdefault(ck + (fmt,), []).append((r, n))
    out, thin, zero_med = [], [], []

    def skipped(ck, fmt, count):
        return [names[ck], count] + ([fmt] if len(fmts[ck]) > 1 else [])

    for (pf, key, fmt), vids in by.items():
        ck = (pf, key)
        if len(vids) < MIN_PER_CHANNEL:
            thin.append(skipped(ck, fmt, len(vids)))
            continue
        med = statistics.median([n for _, n in vids])
        if med <= 0:  # most uploads have no views yet: a multiple of zero means nothing
            zero_med.append(skipped(ck, fmt, len(vids)))
            continue
        for v, n in vids:
            title = v.get("title") or ""
            out.append({"channel": names[ck], "platform": pf, "format": fmt, "multi_format": len(fmts[ck]) > 1,
                        "title": title, "views": int(n), "median": int(med),
                        "multiple": round(n / med, 2), "formula": classify(title), "formula_fa": classify_fa(title),
                        "url": v.get("url") or ""})
    measured = len(by) - len(thin) - len(zero_med)
    out = [r for r in out if r["multiple"] >= lo]
    out.sort(key=lambda r: -r["multiple"])
    sup = supply(rows, args.phrase) if args.phrase else None

    if args.json:
        for r in out:
            r.pop("multi_format")
        res = {"outliers": out, "skipped_thin_channels": thin, "skipped_zero_median_channels": zero_med,
               "skipped_unknown_views": unknown,
               "skipped_other_metric": [{"platform": pf, "channel": ch, "count": n, "metric": m, "other": o}
                                        for pf, ch, n, m, o in metric_notes],
               "formulas_file": os.path.relpath(FORMULAS_FILE, HERE) if FORMULAS_FILE else None}
        if sup is not None:
            res["supply"] = sup
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return

    pfs = {k[0] for k in by}
    unit = "ویدیو/ریلز" if len(pfs) > 1 else ("ریلز" if pfs == {"instagram"} else "ویدیو")
    who = "کانال/اکانت" if len(pfs) > 1 else ("اکانت" if pfs == {"instagram"} else "کانال")
    print("\n  %s %s از %s %s - برجسته‌ها از %s برابرِ میانه به بالا\n"
          % (F(len(rows)), unit, F(len({k[:2] for k in by})), who, F(lo, 1)))
    if sup is not None:
        print("  عرضه برای «%s» (در %s نتیجه‌ی اول، به همان ترتیبی که در فایل آمده)" % (sup["phrase"], F(sup["top"])))
        print("    عبارت عیناً در عنوان: %s از %s   (۰ تا ۲ یعنی جا هست)" % (F(sup["exact_phrase"]), F(sup["top"])))
        if sup["with_subscribers"]:
            print("    بازدیدِ بیشتر از تعداد سابسکرایبر: %s از %s ویدیو (%s تا از ۱۲ ماه اخیر)"
                  % (F(sup["views_beat_subscribers"]), F(sup["with_subscribers"]), F(sup["recent_views_beat_subscribers"])))
        else:
            print("    تعداد سابسکرایبرها در فایل نیست؛ برای این بخش yt-dlp را بدون --flat-playlist اجرا کن.")
        print("    حکم (شکاف / رقابتی / شلوغ / تقاضای کم) را خودت از روی SKILL.md بده؛ تقاضا را این ابزار نمی‌بیند.\n")

    if sup is not None and not out and len(thin) == len(by):
        print("  (برای رتبه‌بندی برجسته‌ها از هر %s دست‌کم %s %s لازم است؛ نتایج جست‌وجو معمولاً این را ندارند.)\n"
              % (who, F(MIN_PER_CHANNEL), unit))
        return
    def label(ch, fmt=None):
        return "%s (%s)" % (ch, FORMAT_FA.get(fmt, fmt)) if fmt else ch

    for r in out[:25]:
        ch = label(r["channel"][:22], r["format"] if r["multi_format"] else None)
        print("    %s×  %s بازدید  در برابر میانه‌ی %s   %s  %s"
              % (F(r["multiple"], 2), F(r["views"]), F(r["median"]), ch, r["title"][:60]))
        print("            فرمول: %s" % r["formula_fa"])
    if not out and measured:
        print("    هیچ موردی به این آستانه نرسید - از هر %s %s بیشتری جمع کن یا --min را پایین بیاور."
              % (who, unit))

    def listing(items):
        return "  " + "، ".join("%s (%s، %s)" % (it[0], FORMAT_FA.get(it[2], it[2]), F(it[1])) if len(it) > 2
                                else "%s (%s)" % (it[0], F(it[1])) for it in items[:6]) + (" …" if len(items) > 6 else "")

    if thin:
        print("\n  %s %s کنار گذاشته شد چون کمتر از %s %s داشت - میانه‌ی یکی دو ویدیو میانه نیست:"
              % (F(len(thin)), who, F(MIN_PER_CHANNEL), unit))
        print(listing(thin))
    if zero_med:
        print("\n  %s %s کنار گذاشته شد چون میانه‌ی بازدیدش صفر است (بیشتر ویدیوها هنوز بازدید ندارند) "
              "- چندبرابرِ صفر معنا ندارد:" % (F(len(zero_med)), who))
        print(listing(zero_med))
    for pf, ch, n, m, o in metric_notes:
        ig = pf == "instagram"
        print("\n  برای %s %s، %s %s فقط «%s» داشت نه «%s» و کنار گذاشته شد تا این دو قاطی نشوند."
              % ("اکانت" if ig else "کانال", ch, F(n), "ریلز" if ig else "ویدیو", METRIC_FA[o], METRIC_FA[m]))
    if unknown:
        print("\n  %s مورد بدون عدد بازدید کنار گذاشته شد (لایو، پریمیر یا هنوز پخش‌نشده) - صفر حساب نشد."
              % F(unknown))
    if not FORMULAS:
        print("\n  فایل فرمول‌ها (hooks.json) پیدا نشد؛ ستون فرمول خالی است.")
    counts = {}
    for r in out:
        counts[r["formula_fa"]] = counts.get(r["formula_fa"], 0) + 1
    if counts:
        print("\n  فرمول‌ها در میان برجسته‌ها")
        for f, n in sorted(counts.items(), key=lambda x: -x[1]):
            print("    %s بار  %s" % (F(n), f))
    print()


if __name__ == "__main__":
    main()
