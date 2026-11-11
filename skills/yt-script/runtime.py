#!/usr/bin/env python3
"""runtime.py - زمان یه اسکریپت رو از تعداد کلمه‌ها حساب کن، نه با حدس.

    python3 -I runtime.py script.md                 # زمان کل، زمان هر بیت، ۱۵ ثانیه‌ی اول
    python3 -I runtime.py script.md --speed 1.2     # ویدیو رو ۱٫۲ برابر تند می‌کنی
    python3 -I runtime.py script.md --tts           # برای صدای کلون/TTS: عددها، اسم‌های لاتین، «ه» ساکن
    python3 -I runtime.py script.md --rate 2.6      # سرعت حرف‌زدن خودت (کلمه در ثانیه)
    python3 -I runtime.py --text "متن اسکریپت"      # بدون فایل
    python3 -I runtime.py script.md --json          # خروجی ماشینی

اسکریپت: هر بیت با یه تیتر مارک‌داون (# یا ##) یا یه خط **پررنگ** شروع می‌شه؛ اگه تیتر نداشت، هر
پاراگراف یه بیته. هر چی داخل [کروشه] باشه ([روی صفحه: ...]، [ON SCREEN: ...]، [مکث]) خونده
نمی‌شه و تو زمان حساب نمی‌شه.

سرعت پیش‌فرض: فارسی ۲٫۴ کلمه در ثانیه (حرف‌زدن فارسی معمولاً ۲٫۳ تا ۲٫۶ است؛ قاعده‌ی سرانگشتی)،
انگلیسی ۲٫۵ (۱۵۰ کلمه در دقیقه). عددها با شکل حروفی‌شون شمرده می‌شن («۲۰۰» = «دویست»).
اگه سرعت واقعیِ خودت رو می‌دونی (کلمه‌های یه برداشت ÷ ثانیه‌هاش)، با --rate بدش.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _fatext as fa  # noqa: E402

PERSIAN_RATE = 2.4
PERSIAN_RANGE = (2.3, 2.6)
ENGLISH_RATE = 2.5
HOOK_SECONDS = 15

# ---- numbers as Persian words (fatext has no helper for this) ----------------------------------
_ONES = ["", "یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه"]
_TEENS = ["ده", "یازده", "دوازده", "سیزده", "چهارده", "پانزده", "شانزده", "هفده", "هجده", "نوزده"]
_TENS = ["", "", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود"]
_HUNDREDS = ["", "صد", "دویست", "سیصد", "چهارصد", "پانصد", "ششصد", "هفتصد", "هشتصد", "نهصد"]
_SCALES = ["", "هزار", "میلیون", "میلیارد", "تریلیون"]


def _below_1000(n):
    parts = []
    h, r = divmod(n, 100)
    if h:
        parts.append(_HUNDREDS[h])
    if 10 <= r < 20:
        parts.append(_TEENS[r - 10])
    else:
        t, o = divmod(r, 10)
        if t:
            parts.append(_TENS[t])
        if o:
            parts.append(_ONES[o])
    return " و ".join(parts)


def int_to_words_fa(n):
    """عدد صحیح ← حروف فارسی: 1403 ← «هزار و چهارصد و سه»، 200000 ← «دویست هزار»."""
    n = int(n)
    if n < 0:
        return "منفی " + int_to_words_fa(-n)
    if n == 0:
        return "صفر"
    groups, i = [], 0
    while n:
        n, g = divmod(n, 1000)
        if g:
            if i >= len(_SCALES):
                return None
            w = _below_1000(g)
            if i == 1 and g == 1:
                w = "هزار"
            elif i:
                w = w + " " + _SCALES[i]
            groups.append(w)
        i += 1
    return " و ".join(reversed(groups))


def number_to_words_fa(s):
    """«۱۲٬۴۰۰» ← «دوازده هزار و چهارصد»، «۱٫۵» ← «یک و نیم»، «2.25» ← «دو ممیز بیست و پنج».
    None اگه عدد ساده نبود (تاریخ مثل ۱۴۰۳/۰۸/۲۰، ساعت مثل ۱۲:۳۰)."""
    t = fa.to_ascii_digits(str(s)).replace("−", "-").replace("٬", ",").replace("٫", ".")
    neg = t.startswith("-")
    t = t.lstrip("-+")
    if re.match(r"^\d{1,3}(,\d{3})+$", t):
        t = t.replace(",", "")
    if not re.match(r"^\d+(\.\d+)?$", t):
        return None
    whole, _, frac = t.partition(".")
    w = int_to_words_fa(int(whole))
    if w is None:
        return None
    if frac:
        frac = frac.rstrip("0")
    if frac == "5":
        w = w + " و نیم"
    elif frac:
        fw = int_to_words_fa(int(frac))
        w = w + " ممیز " + ("صفر " * (len(frac) - len(frac.lstrip("0")))) + fw
    return ("منفی " + w) if neg else w


# ---- reading the script -----------------------------------------------------------------------
_BRACKETS = re.compile(r"\[[^\]]*\]")
_SCREEN = re.compile(r"\[\s*(روی صفحه|رو صفحه|روی اسکرین|on screen|b-roll|بی‌رول)\s*[:：]", re.I)
_HEADING = re.compile(r"^\s*(#{1,6}\s+(.*)|\*\*(.+?)\*\*\s*:?\s*)$")
# a leading hyphen is a minus sign only when no letter or digit comes right before it
# (GPT-5 and ۲۰-۳۰ are a name and a range, not «منفی پنج» / «منفی سی»; «-3 درجه» is still negative)
_NUMTOK = re.compile(r"(?:(?<![\w۰-۹٠-٩])[-−])?[0-9۰-۹٠-٩]+(?:[.,٫٬/:][0-9۰-۹٠-٩]+)*")
_D = "0-9۰-۹٠-٩"
# a range like ۲۰-۳۰ or 2–3 (not part of a date like ۱۴۰۳-۰۸-۲۰): read as «بیست تا سی»
_RANGE = re.compile(r"(?<![%s.,٫٬/:\-–−])([%s]+(?:[.,٫٬][%s]+)?)\s*[-–]\s*([%s]+(?:[.,٫٬][%s]+)?)"
                    r"(?![%s]|[.,٫٬/:][%s]|\s*[-–]\s*[%s])" % ((_D,) * 8))


def parse_beats(raw):
    """[(title, spoken_text, has_screen_note)]"""
    beats = []
    cur = {"title": "", "lines": [], "screen": False}

    def flush():
        if any(l.strip() for l in cur["lines"]) or cur["title"]:
            beats.append((cur["title"], "\n".join(cur["lines"]).strip(), cur["screen"]))

    has_headings = any(_HEADING.match(l) for l in raw.splitlines())
    for line in raw.splitlines():
        if line.strip().startswith("```"):
            continue
        m = _HEADING.match(line)
        if m:
            flush()
            cur = {"title": (m.group(2) or m.group(3) or "").strip(), "lines": [], "screen": False}
            continue
        if not has_headings and not line.strip():
            flush()
            cur = {"title": "", "lines": [], "screen": False}
            continue
        if _SCREEN.search(line):
            cur["screen"] = True
        cur["lines"].append(line)
    flush()
    out = []
    for title, text, screen in beats:
        spoken = _BRACKETS.sub(" ", text)
        spoken = re.sub(r"^\s*([-*•]|\d+[.)])\s+", "", spoken, flags=re.M)
        spoken = re.sub(r"^\s*>\s?", "", spoken, flags=re.M)
        spoken = spoken.replace("**", "").replace("__", "")
        spoken = fa.normalize(re.sub(r"\s+", " ", spoken))
        if title or spoken:
            out.append((title, spoken, screen))
    return [b for b in out if b[1]]


def spoken_words(text):
    """Words as they are said: a number counts as the words it is read as."""
    n = 0
    for tok in fa.tokenize(text):
        if _NUMTOK.fullmatch(tok):
            w = number_to_words_fa(tok)
            n += len(w.split()) if w else 1
        else:
            n += 1
    return n


# ---- one close: count the asks ------------------------------------------------------------------
CTA = [
    ("سابسکرایب", re.compile(r"سابسکرایب\s*(کن|کنید|یادت|رو بزن)|ساب\s*کن|مشترک\s*(شو|بشید|شید)|\bsubscribe\b", re.I)),
    ("لایک", re.compile(r"لایک\s*(کن|کنید|یادت)|like\s+(this|the)", re.I)),
    ("کامنت", re.compile(r"کامنت\s*(کن|کنید|بذار|بزار|بنویس)|تو\s*کامنت|زیر\s*(این\s*)?(ویدیو|پست)\s*بنویس|comment", re.I)),
    ("فالو", re.compile(r"فالو\s*(کن|کنید)|دنبال\s*(کن|کنید)|follow", re.I)),
    ("اشتراک‌گذاری", re.compile(r"\bshare\b|شیر\s*(کن|کنید)|بفرستش\s*(برای|واسه)|برای\s*\S+\s*بفرست", re.I)),
    ("سیو", re.compile(r"سیو\s*(کن|کنید)|ذخیره\s*(کن|کنید)|save\s+this", re.I)),
    ("لینک", re.compile(r"لینک\s*(تو|توی|در)\s*(بیو|توضیحات|کپشن)|link\s+in", re.I)),
]


def asks(text):
    return [name for name, rx in CTA if rx.search(text)]


# ---- TTS / voice clone lint -------------------------------------------------------------------
_HARAKAT = "ًٌٍَُِّْ"
_LATIN = re.compile(r"[A-Za-z][A-Za-z0-9'’.\-]*")


TRANSLIT = {"claude": "کلاد", "youtube": "یوتیوب", "instagram": "اینستاگرام", "google": "گوگل",
            "chatgpt": "چت‌جی‌پی‌تی", "gpt": "جی‌پی‌تی", "gemini": "جمینای", "telegram": "تلگرام",
            "ai": "ای‌آی (یا «هوش مصنوعی»)", "openai": "اوپن‌ای‌آی", "anthropic": "آنتروپیک", "apple": "اپل",
            "iphone": "آیفون", "tesla": "تسلا", "nvidia": "انویدیا", "prompt": "پرامپت", "studio": "استودیو",
            "shorts": "شورتس", "reels": "ریلز", "tiktok": "تیک‌تاک", "davinci": "داوینچی"}


def tts_issues(text):
    """Lines a clone/TTS voice is likely to misread. Each: (kind, found, suggestion)."""
    out = []
    t = fa.normalize(text)  # harakat are kept on purpose
    # Latin names (GPT-4o, GPT-5) get their own line below that says to spell the whole name in
    # Persian, so the digits inside them need no separate «عدد» line.
    latin_spans = [m.span() for m in _LATIN.finditer(t)]
    covered = []
    for m in _RANGE.finditer(t):
        if any(a <= m.start() < b for a, b in latin_spans):
            continue
        lo, hi = number_to_words_fa(m.group(1)), number_to_words_fa(m.group(2))
        if lo and hi:
            out.append(("بازه", m.group(0), "%s تا %s" % (lo, hi)))
            covered.append(m.span())
    for m in _NUMTOK.finditer(t):
        if any(a <= m.start() < b for a, b in latin_spans + covered):
            continue
        tok = m.group(0)
        w = number_to_words_fa(tok)
        if w:
            out.append(("عدد", tok, w))
        else:
            out.append(("عدد", tok, "تاریخ یا ساعت رو با حروف بنویس (مثلاً «بیستم آبان»، «دوازده و نیم»)"))
    if re.search(r"[%٪]", t):
        out.append(("درصد", "%", "«درصد» رو با حروف بنویس"))
    seen = set()
    for m in _LATIN.finditer(t):
        w = m.group(0).strip(".-")
        if w and w.lower() not in seen:
            seen.add(w.lower())
            known = TRANSLIT.get(w.lower())
            out.append(("لاتین", w, ("بنویس «%s»" % known) if known else
                        "با حروف فارسی بنویس، همون‌جوری که تلفظش می‌کنی"))
    for tok in re.findall(r"\S+", t):
        core = tok.strip("«»\"'()،,.!?؟؛:…")
        if len(core) >= 2 and core.endswith("ه") and core[-2] in _HARAKAT:
            out.append(("ه ساکن", core, "علامت قبل از «ه» آخر رو بردار (%s)؛ وگرنه صدا «ه» رو تلفظ می‌کنه"
                        % re.sub("[" + _HARAKAT + "]", "", core)))
        elif core.endswith(("ۀ", "هٔ", "هِ")) and len(core) >= 2:
            base = re.sub("[" + _HARAKAT + "ٔ]", "", core).replace("ۀ", "ه")
            out.append(("اضافه", core, "اضافه رو با «‌ی» بنویس: %s‌ی" % base))
    return out


# ---- report -----------------------------------------------------------------------------------
def _fa(x):
    return fa.to_fa_digits(str(x), separators=True)


def _ts(sec):
    return fa.fmt_timestamp(sec, "yt", fa_digits=True)


def analyse(raw, rate=None, speed=1.0, tts=False):
    beats = parse_beats(raw)
    spoken_all = " ".join(b[1] for b in beats)
    lang = "fa" if fa.is_persian(spoken_all) else "en"
    custom = rate is not None
    if rate is None:
        rate = PERSIAN_RATE if lang == "fa" else ENGLISH_RATE
    eff = rate * speed
    rows, t = [], 0.0
    for i, (title, text, screen) in enumerate(beats):
        n = spoken_words(text)
        sec = n / eff
        rows.append({"beat": i + 1, "title": title, "start": round(t, 1), "words": n,
                     "seconds": round(sec, 1), "on_screen": screen})
        t += sec
    total_words = sum(r["words"] for r in rows)
    res = {"lang": lang, "rate": rate, "speed": speed, "words": total_words,
           "seconds": round(total_words / eff, 1) if eff else 0.0, "beats": rows}
    if lang == "fa" and not custom:
        lo, hi = PERSIAN_RANGE
        res["seconds_range"] = [round(total_words / (hi * speed), 1), round(total_words / (lo * speed), 1)]
    # what is said inside the first 15 seconds
    toks = fa.tokenize(spoken_all)
    budget, acc, hook = HOOK_SECONDS * eff, 0, []
    for tok in toks:
        w = spoken_words(tok) or 1
        if acc + w > budget:
            break
        acc += w
        hook.append(tok)
    res["first_15s"] = " ".join(hook)
    close = beats[-2:] if len(beats) > 3 else beats[-1:]
    res["asks"] = asks(" ".join(b[1] for b in close))
    res["asks_total"] = asks(spoken_all)
    res["missing_on_screen"] = [r["beat"] for r in rows if not r["on_screen"]]
    if tts:
        res["tts"] = [{"kind": k, "found": f, "fix": s} for k, f, s in tts_issues(spoken_all)]
    return res


def report(r):
    rate_line = "%s کلمه در ثانیه" % _fa(r["rate"])
    if r["speed"] != 1.0:
        rate_line += " × سرعت %s" % _fa(r["speed"])
    print("\n  زمان اسکریپت")
    print("  " + "-" * 40)
    line = "    کل: %s کلمه ≈ %s (%s)" % (_fa(r["words"]), _ts(r["seconds"]), rate_line)
    print(line)
    if "seconds_range" in r:
        lo, hi = r["seconds_range"]
        print("    بازه: %s تا %s (با سرعت ۲٫۳ تا ۲٫۶ کلمه در ثانیه)" % (_ts(lo), _ts(hi)))
    print("\n    بیت‌ها:")
    for b in r["beats"]:
        title = b["title"] or "بیت %s" % _fa(b["beat"])
        mark = "" if b["on_screen"] else "   ← [روی صفحه: ...] نداره"
        print("    %s  %s  (%s کلمه، %s ثانیه)%s" % (_ts(b["start"]), title, _fa(b["words"]), _fa(b["seconds"]), mark))
    print("\n    ۱۵ ثانیه‌ی اول اینه:")
    print("    «%s»" % r["first_15s"])
    print("    کار هوک: کلیکِ تایتل رو تأیید کنه، یه سؤال باز کنه، ثابت کنه جواب هست. هر سه اینجا هست؟")
    if len(set(r["asks"])) > 1:
        print("\n    پایان بیشتر از یه درخواست داره (%s). فقط یکی نگه دار." % "، ".join(r["asks"]))
    elif not r["asks"]:
        print("\n    پایان هیچ درخواستی نداره. یه درخواست بذار (برای ریلز: کلمه‌ی کامنت).")
    if "tts" in r:
        print("\n    بررسی برای صدای کلون / TTS:")
        if not r["tts"]:
            print("    چیزی پیدا نشد.")
        for x in r["tts"]:
            print("    [%s] %s ← %s" % (x["kind"], x["found"], x["fix"]))
        print("    یادت باشه: ویدیو با صدای ساختگی رو به‌عنوان «هوش مصنوعی» برچسب بزن.")
    print()


def _value(a, flag):
    i = a.index(flag)
    if i + 1 >= len(a):
        raise ValueError("بعد از %s یه مقدار لازمه" % flag)
    v = a[i + 1]
    del a[i:i + 2]
    return v


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__, file=sys.stdout if a else sys.stderr)
        sys.exit(0 if a else 1)
    as_json = "--json" in a
    tts = "--tts" in a
    a = [x for x in a if x not in ("--json", "--tts")]
    try:
        rate = float(fa.to_ascii_digits(_value(a, "--rate")).replace("٫", ".")) if "--rate" in a else None
        speed = float(fa.to_ascii_digits(_value(a, "--speed")).replace("٫", ".")) if "--speed" in a else 1.0
        text = _value(a, "--text") if "--text" in a else None
    except ValueError as e:
        msg = str(e) if "لازمه" in str(e) else "عدد --rate یا --speed درست نیست"
        print("runtime: " + msg, file=sys.stderr)
        sys.exit(2)
    if (rate is not None and rate <= 0) or speed <= 0:
        print("runtime: --rate و --speed باید بزرگ‌تر از صفر باشن", file=sys.stderr)
        sys.exit(2)
    if text is None:
        if not a:
            print("runtime: فایل اسکریپت یا --text لازمه", file=sys.stderr)
            sys.exit(2)
        try:
            with open(a[0], encoding="utf-8-sig") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            print("runtime: فایل پیدا یا خونده نشد: %s" % a[0], file=sys.stderr)
            sys.exit(2)
    r = analyse(text, rate=rate, speed=speed, tts=tts)
    if not r["beats"]:
        print("runtime: متنی برای خوندن پیدا نشد", file=sys.stderr)
        sys.exit(2)
    if as_json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        report(r)


if __name__ == "__main__":
    main()
