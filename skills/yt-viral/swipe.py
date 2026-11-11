#!/usr/bin/env python3
"""swipe.py - ویدیوها و ریلزها را بر اساس اینکه چند برابرِ میانه‌ی خودِ کانال/اکانت دیده شده‌اند رتبه می‌دهد
و فرمول عنوان (یا خط اول کپشن) را نام می‌برد.

    python3 -I swipe.py collected.json
    python3 -I swipe.py collected.json --min 2 --json
    python3 -I swipe.py reels.csv --min ۳
    python3 -I swipe.py search.json --phrase "آموزش کلاد"

ورودی (JSON یا CSV) - هر ردیف یک ویدیو یا ریلز:

    [{"channel": "...", "title": "...", "views": 412000, "url": "..."}, ...]
    [{"account": "@...", "caption": "...", "plays": "۱۲ هزار"}, ...]        (اینستاگرام)

این‌ها هم همان‌طور که هستند خوانده می‌شوند: {"videos": [...]}، {"reels": [...]}، خروجی
`yt-dlp --flat-playlist -J` (entries و view_count)، و خروجی اسکرپرهای اینستاگرام
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
import argparse, csv, datetime, io, json, os, re, statistics, sys

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
CHANNEL_KEYS = _keys("channel", "uploader", "account", "username", "ownerUsername", "owner", "handle",
                     "کانال", "اکانت", "حساب", "پیج")
TITLE_KEYS = _keys("title", "caption", "text", "عنوان", "کپشن", "متن")
URL_KEYS = _keys("url", "webpage_url", "link", "permalink", "لینک", "آدرس")
SUBS_KEYS = _keys("subscribers", "channel_follower_count", "followers", "followersCount", "سابسکرایبر",
                  "مشترک", "فالوور", "دنبال‌کننده")
KID_KEYS = _keys("videos", "entries", "reels", "items", "posts", "ویدیوها", "ریلزها")
IG_HINTS = _keys("account", "caption", "plays", "play_count", "playCount", "videoPlayCount", "ownerUsername",
                 "shortCode", "ig_play_count", "اکانت", "کپشن", "پلی", "پیج")


def _get(d, keys):
    """First non-empty value whose (folded) key is in keys, in the order keys are listed."""
    idx = {}
    for key, val in d.items():
        idx.setdefault(_k(key), val)
    for key in keys:
        val = idx.get(key)
        if isinstance(val, dict):  # e.g. {"owner": {"username": "x"}}
            val = val.get("username") or val.get("name")
        if val is not None and str(val).strip() != "":
            return val
    return None


def _num(x):
    """A count as a float, or None when it is missing/unknown. Never guesses."""
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        n = float(x)
    else:
        n = fa.parse_number(str(x))
    if n is None or n != n or n < 0:
        return None
    return n


def _views(v):
    return _num(v.get("views"))


def _platform(node, url):
    p = str(node.get("platform") or node.get("پلتفرم") or "").strip().lower()
    if p in ("instagram", "ig", "insta", "اینستاگرام", "اینستا"):
        return "instagram"
    if p in ("youtube", "yt", "یوتیوب"):
        return "youtube"
    if "instagram.com" in (url or ""):
        return "instagram"
    keys = {_k(x) for x in node}
    return "instagram" if keys & set(IG_HINTS) else "youtube"


def _first_line(text):
    for line in str(text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def _flatten(node, parent_ch=None, parent_pf=None):
    """A plain list, {"videos"|"entries"|"reels": [...]}, nested yt-dlp channel tabs, or one row."""
    if isinstance(node, list):
        for x in node:
            yield from _flatten(x, parent_ch, parent_pf)
        return
    if not isinstance(node, dict):
        return
    ch = _get(node, CHANNEL_KEYS) or parent_ch
    kids = _get(node, KID_KEYS)
    if isinstance(kids, list):
        pf = parent_pf or (_platform(node, "") if node.get("platform") or node.get("پلتفرم") else None)
        yield from _flatten(kids, ch or node.get("title"), pf)
        return
    url = str(_get(node, URL_KEYS) or "")
    pf = _platform(node, url) if (node.get("platform") or node.get("پلتفرم")) else (parent_pf or _platform(node, url))
    title = _get(node, TITLE_KEYS)
    yield {"channel": str(ch) if ch is not None else "?", "title": _first_line(title) if title is not None else "",
           "views": _get(node, VIEW_KEYS), "url": url, "platform": pf,
           "subscribers": _get(node, SUBS_KEYS), "upload_date": node.get("upload_date") or node.get("timestamp")}


def _read(path):
    with open(path, encoding="utf-8-sig") as fh:
        raw = fh.read()
    s = raw.lstrip()
    if s[:1] in "[{":
        return list(_flatten(json.loads(raw)))
    if path.lower().endswith((".json", ".jsonl")):
        return list(_flatten([json.loads(l) for l in raw.splitlines() if l.strip()]))
    sample = raw[:4096]
    delim = "\t" if sample.count("\t") > sample.count(",") else ","
    return list(_flatten(list(csv.DictReader(io.StringIO(raw), delimiter=delim))))


# ---- supply check (--phrase) --------------------------------------------------------------------

def _words(text):
    return fa.norm_words(str(text or "").replace(fa.ZWNJ, " "))


def has_phrase(title, phrase):
    """Phrase appears as written (word for word, ZWNJ/space and ی/ي differences ignored)."""
    t, p = _words(title), _words(phrase)
    if not p:
        return False
    return any(t[i:i + len(p)] == p for i in range(len(t) - len(p) + 1))


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
    n = fa.parse_number(s)
    if n is None or n < 0:
        raise argparse.ArgumentTypeError("--min باید یک عدد مثبت باشد، مثلاً 2 یا ۲٫۵ (نه %r)" % s)
    return n


def F(x, nd=0):
    """Number for the Persian report: Persian digits, ٬ thousands, ٫ decimals."""
    s = ("{:,.%df}" % nd).format(x)
    return fa.to_fa_digits(s, separators=True)


def _label(r):
    return "اینستاگرام" if r == "instagram" else "یوتیوب"


def main():
    p = _Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", help="فایل JSON یا CSV")
    p.add_argument("--min", type=_threshold, default=1.5, help="حداقل چند برابرِ میانه (پیش‌فرض ۱٫۵)")
    p.add_argument("--json", action="store_true", help="خروجی JSON برای ابزارهای دیگر")
    p.add_argument("--phrase", help="عبارت جست‌وجو برای سنجش عرضه روی نتایج جست‌وجو")
    args = p.parse_args()
    lo = args.min
    if not os.path.isfile(args.file):
        print(__doc__)
        print("swipe.py: فایل «%s» پیدا نشد." % args.file, file=sys.stderr)
        sys.exit(1)
    try:
        rows = _read(args.file)
    except (ValueError, csv.Error, UnicodeDecodeError) as e:
        print("swipe.py: «%s» خوانده نشد (JSON یا CSV معتبر نیست): %s" % (args.file, e), file=sys.stderr)
        sys.exit(2)
    if not rows or not any(_views(v) is not None for v in rows):
        print("swipe.py: در «%s» هیچ ویدیو یا ریلزی با عدد بازدید پیدا نشد. "
              "انتظار می‌رفت فهرستی از {channel, title, views} یا {account, caption, plays}، "
              "{\"videos\": [...]} یا خروجی yt-dlp -J باشد." % args.file, file=sys.stderr)
        sys.exit(2)

    by, unknown = {}, 0
    for r in rows:
        n = _views(r)
        if n is None:
            unknown += 1
            continue
        by.setdefault((r["platform"], r["channel"] or "?"), []).append((r, n))
    out, thin = [], []
    for (pf, ch), vids in by.items():
        if len(vids) < MIN_PER_CHANNEL:
            thin.append((ch, len(vids)))
            continue
        med = statistics.median([n for _, n in vids])
        for v, n in vids:
            m = (n / med) if med else 0
            title = v.get("title") or ""
            out.append({"channel": ch, "platform": pf, "title": title, "views": int(n), "median": int(med),
                        "multiple": round(m, 2), "formula": classify(title), "formula_fa": classify_fa(title),
                        "url": v.get("url") or ""})
    out = [r for r in out if r["multiple"] >= lo]
    out.sort(key=lambda r: -r["multiple"])
    sup = supply(rows, args.phrase) if args.phrase else None

    if args.json:
        res = {"outliers": out, "skipped_thin_channels": thin, "skipped_unknown_views": unknown,
               "formulas_file": os.path.relpath(FORMULAS_FILE, HERE) if FORMULAS_FILE else None}
        if sup is not None:
            res["supply"] = sup
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return

    pfs = {pf for pf, _ in by}
    unit = "ویدیو/ریلز" if len(pfs) > 1 else ("ریلز" if pfs == {"instagram"} else "ویدیو")
    who = "کانال/اکانت" if len(pfs) > 1 else ("اکانت" if pfs == {"instagram"} else "کانال")
    print("\n  %s %s از %s %s - برجسته‌ها از %s برابرِ میانه به بالا\n"
          % (F(len(rows)), unit, F(len(by)), who, F(lo, 1)))
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
    for r in out[:25]:
        print("    %s×  %s بازدید  در برابر میانه‌ی %s   %s  %s"
              % (F(r["multiple"], 2), F(r["views"]), F(r["median"]), r["channel"][:22], r["title"][:60]))
        print("            فرمول: %s" % r["formula_fa"])
    if not out:
        print("    هیچ موردی به این آستانه نرسید - از هر %s %s بیشتری جمع کن یا --min را پایین بیاور."
              % (who, unit))
    if thin:
        print("\n  %s %s کنار گذاشته شد چون کمتر از %s %s داشت - میانه‌ی یکی دو ویدیو میانه نیست:"
              % (F(len(thin)), who, F(MIN_PER_CHANNEL), unit))
        print("  " + "، ".join("%s (%s)" % (c, F(n)) for c, n in thin[:6]) + (" …" if len(thin) > 6 else ""))
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
