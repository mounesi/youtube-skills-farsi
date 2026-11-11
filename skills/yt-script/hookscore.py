#!/usr/bin/env python3
"""hookscore.py - قبل از اینکه یه برداشت رو سر یه هوک هدر بدی، نمره‌ش رو ببین.

پنج ویژگی، هر کدوم از ۰ تا ۱۰۰، و یه حکم که ۶۰٪ میانگینه و ۴۰٪ ضعیف‌ترین ویژگی. این وزن‌دهیِ
«ضعیف‌ترین حلقه» عمدیه: هوکی که چهار ویژگی قوی و یکی مرده داره، دقیقاً از همون نقطه‌ی مرده بیننده رو
از دست می‌ده، و میانگین این رو قایم می‌کنه.

    python3 -I hookscore.py hooks.txt            # هر خط یه هوک، مرتب از قوی به ضعیف
    python3 -I hookscore.py --hook "یه خط"       # نمره‌ی یه هوک
    python3 -I hookscore.py --json hooks.txt     # خروجی ماشینی (JSON)

ویژگی‌ها: دقت (عدد، اسم، تاریخ، واحد)، خطاب (تو/شما و فعل‌ها و ضمیرهای خطاب)، ریسک (چی رو از دست
می‌ده)، کنجکاوی (سؤال باز)، کوتاهی (تعداد کلمه؛ فارسی ۸ تا ۲۲ کلمه، انگلیسی ۹ تا ۲۴).
حکم: قوی (۷۲ به بالا)، متوسط (۵۵ تا ۷۱)، ضعیف (زیر ۵۵). ورودی فارسی، انگلیسی یا ترکیبی؛ رقم فارسی
و عربی هم خونده می‌شه.

این ابزار چی می‌تونه بگه و چی نه: نسخه‌ی انگلیسیِ اصلی روی ۷۴ هوک واقعی سنجیده شده (پک
Jakeschincariol/youtube-agent-skill): هوک‌های عمداً بد رو خوب از هوک‌های واقعی جدا می‌کنه، ولی
موفق‌ها و ناموفق‌های خودِ یه سازنده رو تقریباً اصلاً از هم جدا نمی‌کنه. واژه‌نامه‌ی فارسی قاعده‌ی
سرانگشتیه و روی داده‌ی فارسی سنجیده نشده. نمره‌ی پایین یعنی «یه بار دیگه نگاه کن»، نمره‌ی بالا
هیچ قولی نیست.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _fatext as fa  # noqa: E402


def _load_formulas():
    try:
        with open(os.path.join(HERE, "hooks.json"), encoding="utf-8-sig") as fh:
            return json.load(fh).get("hooks") or []
    except (OSError, ValueError, AttributeError):
        return []


FORMULAS = _load_formulas()

# ---- English lexicon (upstream, unchanged) -----------------------------------------------------
FILLER = {"basically", "actually", "literally", "just", "really", "very", "so", "kind", "sort", "like",
          "guys", "hey", "welcome", "today", "video", "subscribe", "channel"}
VAGUE = {"amazing", "incredible", "insane", "crazy", "huge", "massive", "game", "changer", "secret",
         "powerful", "ultimate", "best", "revolutionary", "mind", "blowing", "unbelievable"}
CONCRETE = re.compile(r"\b(\d[\d,.]*\s?(%|k|m|x|s|m|h)?|\$\d|\d+\s?(second|minute|hour|day|week|month|year)s?)\b", re.I)
YOU = re.compile(r"\b(you|your|you're|youre|yourself)\b", re.I)
STAKE = re.compile(r"\b(lose|lost|wasting|waste|quit|fail|broke|cost|risk|before|stop|never|die|dying|dead)\b", re.I)
CURIOSITY = re.compile(r"\b(why|how|what|which|until|before|but|nobody|almost|except|reason|actually)\b", re.I)
CLOSED_EN = re.compile(r"\b(because|so that|which means)\b", re.I)


def _f(words):
    return frozenset(fa.fold(w) for w in words)


# ---- Persian lexicon (all folded: no ZWNJ, آ -> ا, no harakat) -----------------------------------
ADDRESS_FA = _f(["تو", "شما", "خودت", "خودتون", "خودتان", "بهت", "بهتون", "بهتان", "برات", "براتون", "ازت",
                 "ازتون", "باهات", "باهاتون", "واست", "واستون", "ات", "تون", "داری", "دارید", "هستی", "هستید",
                 "بودی", "داشتی", "کردی", "دیدی", "زدی", "خواستی", "کنی", "بکنی", "بدی", "بزنی", "بسازی",
                 "بگیری", "بخوای", "بتونی"])
IMPERATIVE_FA = _f(["ببین", "ببینید", "بزن", "بزنید", "نکن", "نکنید", "بدونید", "بخون", "بخونید",
                    "بنویس", "بپرس", "بساز", "بگو", "بذار", "نذار", "بکن", "برو", "بیا",
                    "نزن", "نخر", "بخر"])
ADDRESS_PHRASES_FA = ("صبر کن", "گوش کن", "امتحان کن", "دست نگه دار", "نگاه کن")
# nouns that take the 2nd-person suffix -ت / -تون («کانالت»، «وقتتون»)
OWN_NOUNS_FA = _f(["کانال", "ویدیو", "ویدئو", "پیج", "پول", "شغل", "مخاطب", "تایتل", "تامبنیل", "اسکریپت",
                   "هوک", "ذهن", "زندگی", "عمر", "وقت", "پست", "ریل", "اکانت", "بیزینس", "برند", "محتوا",
                   "سرمایه", "گوشی", "خونه", "ماشین", "مغز", "موضوع", "بیننده", "فالوور", "سابسکرایبر",
                   "کامنت", "ایده", "درامد", "رزومه", "تیم", "شرکت", "مشتری", "استارتاپ", "پروژه", "کد"])
STAKES_FA = _f(["ضرر", "هدر", "اشتباه", "پول", "وقت", "شغل", "اخراج", "جریمه", "خطر", "نابود", "باخت",
                "ریسک", "هزینه", "ورشکست", "مسدود", "دیمانتایز", "استرایک", "سوخت", "سوزوند", "بیکار"])
STAKES_PHRASES_FA = ("از دست", "قبل از اینکه", "قبل از این که", "دیگه نه", "هیچ وقت")
STAKES_TOKENS_FA = _f(["هیچوقت", "هرگز", "نکن", "نزن"])
STAKES_NOT_FA = _f(["وقتی", "وقتیکه"])  # «وقتی» = when, not «وقت» (time)
CURIOSITY_FA = _f(["چرا", "چطور", "چطوری", "چجوری", "چگونه", "چی", "چیه", "کدوم", "کدومش", "کدام", "ولی",
                   "اما", "هیچکس", "تقریبا", "جز", "راز", "رازش", "دلیلش", "مگه", "هیچکدوم"])
CURIOSITY_PHRASES_FA = ("تا وقتی", "هیچ کس", "به جز", "قبل از اینکه", "قبل از این که")
CLOSED_TOKENS_FA = _f(["چون", "یعنی", "چونکه"])
CLOSED_PHRASES_FA = ("به خاطر اینکه", "بخاطر اینکه", "برای اینکه", "به این دلیل که")
VAGUE_FA = _f(["فوق‌العاده", "باورنکردنی", "خفن", "دیوانه‌کننده", "عالی", "بهترین", "انقلابی", "معجزه",
               "شگفت‌انگیز", "بی‌نظیر", "محشر", "جادویی", "شاهکار", "باحال", "خیلی‌خوب", "بی‌رقیب"])
FILLER_FA = _f(["سلام", "دوستان", "امروز", "سابسکرایب", "کانال", "کانالم", "کانالمون", "ویدیو", "ویدیوی",
                "ویدئو", "ویدئوی", "خب", "یعنی", "واقعا", "دقیقا", "اصلا", "بچه‌ها", "رفقا", "عزیزان",
                "عزیزای", "خوش", "اومدید", "ببخشید", "لایک"])
# Persian-letter names of products and companies count as named things (like a capitalised word)
BRANDS_FA = _f(["یوتیوب", "اینستاگرام", "اینستا", "گوگل", "کلاد", "چت‌جی‌پی‌تی", "جی‌پی‌تی", "جمینای",
                "تلگرام", "تیک‌تاک", "اپل", "آیفون", "تسلا", "مایکروسافت", "انویدیا", "اوپن‌ای‌آی", "آنتروپیک",
                "متا", "واتساپ", "لینکدین", "نتفلیکس", "اسپاتیفای", "کپ‌کات", "داوینچی", "ادوبی", "فتوشاپ",
                "پریمیر", "میدجرنی", "کرسر", "ایکس", "توییتر", "آمازون", "سامسونگ", "دیپ‌سیک"])
UNITS_FA = _f(["ثانیه", "دقیقه", "ساعت", "روز", "هفته", "ماه", "سال", "تومان", "تومن", "دلار", "درصد",
               "ریال", "یورو", "برابر"])
NUMWORDS_FA = _f(["یک", "دو", "سه", "چهار", "پنج", "شش", "شیش", "هفت", "هشت", "نه", "ده", "یازده", "دوازده",
                  "سیزده", "چهارده", "پونزده", "پانزده", "شونزده", "شانزده", "هفده", "هجده", "هیجده",
                  "نوزده", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود", "صد", "دویست",
                  "سیصد", "چهارصد", "پانصد", "پونصد", "ششصد", "هفتصد", "هشتصد", "نهصد", "هزار", "میلیون",
                  "میلیارد", "نیم"])
NUM_AMBIGUOUS_FA = _f(["یک", "نه", "نیم"])  # «یک» = a, «نه» = no: a number only next to another number word
SUFFIXES_FA = frozenset(["", "ها", "های", "ی", "ه", "ت", "تون", "تان", "م", "مون", "ش", "شون", "ات", "هات",
                         "هاتون", "ای", "یه", "رو", "شو", "مو", "تو", "ست", "اش", "هاش", "هامون", "ن", "ید"])

FA_CH = "ء-غف-ٰٟپچژکگۀی۰-۹٠-٩٪-٬‌"
_WORD = re.compile("[a-z0-9'%$." + FA_CH + "]+")
_FA_LETTER = re.compile("[ء-يپچژکگی]")

PERSIAN_RATE = 2.4   # words per second; Persian speech runs about 2.3-2.6 (heuristic)
ENGLISH_RATE = 2.5   # 150 words per minute


def words(t):
    """کلمه‌های یک متن (فارسی و لاتین). نقطه‌ی آخر جمله جزو کلمه نیست؛ «1.5» و «۱٫۵» یه کلمه‌ان."""
    t = fa.normalize(t).lower()
    return [w for w in (x.strip("." + fa.ZWNJ) for x in _WORD.findall(t)) if w]


def _ftoks(t):
    return [fa.fold(w) for w in words(t) if _FA_LETTER.search(w) or w[:1] in "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩"]


def _stem(tok, stems):
    for s in stems:
        if tok.startswith(s) and tok[len(s):] in SUFFIXES_FA:
            return True
    return False


def _phrases(t, phrases):
    ft = " " + " ".join(fa.fold(w) for w in words(t)) + " "
    return sum(ft.count(" " + fa.fold(p) + " ") for p in phrases)


def is_fa(t):
    return fa.is_persian(t)


def _address_tok(tok):
    if tok in ADDRESS_FA or tok in IMPERATIVE_FA:
        return True
    if len(tok) >= 4 and (tok.startswith("می") or tok.startswith("نمی")) and (tok.endswith("ی") or tok.endswith("ید")):
        return True  # میدی، می‌کنی، نمی‌دونی، می‌خواید
    for suf in ("هاتون", "هات", "تون", "تان", "ت"):  # کانالت، وقتتون، ویدیوهات
        if tok.endswith(suf) and tok[:-len(suf)] in OWN_NOUNS_FA:
            return True
    return False


IN_NEXT_FA = _f(["این", "اون", "همین", "همون", "یه", "یک", "ویدیو", "ویدئو", "کانال", "دنیا", "ایران", "خونه",
                  "اینستاگرام", "یوتیوب", "کامنت", "کامنتها", "توضیحات", "بیو", "ذهن", "سرچ"])


def address_fa(t):
    toks = _ftoks(t)
    n = 0
    for i, x in enumerate(toks):
        # colloquial «تو/توی» = "in": «تو این ویدیو»، «توی یوتیوب»
        if x in ("تو", "توی") and i + 1 < len(toks) and toks[i + 1] in IN_NEXT_FA:
            continue
        if _address_tok(x):
            n += 1
    return n + _phrases(t, ADDRESS_PHRASES_FA)


def _concrete_text(t):
    return fa.normalize(t).replace("٬", ",").replace("٫", ".").replace("٪", "%")


def numbers_fa(t):
    """(spelled number runs, units that stand alone) in Persian text; digits are counted by CONCRETE."""
    toks = [fa.fold(w) for w in words(t)]
    runs, lone_units, i = 0, 0, 0
    prev_num = False
    while i < len(toks):
        x = toks[i]
        if x in NUMWORDS_FA:
            j = i
            while j < len(toks) and (toks[j] in NUMWORDS_FA or (toks[j] == "و" and j + 1 < len(toks) and toks[j + 1] in NUMWORDS_FA)):
                j += 1
            run = [w for w in toks[i:j] if w != "و"]
            if len(run) > 1 or run[0] not in NUM_AMBIGUOUS_FA:
                runs += 1
                prev_num = True
            i = j
            continue
        isdigit = bool(re.match(r"^[\d.,%]+$", x))
        if _stem(x, UNITS_FA) and not prev_num:
            lone_units += 1
        prev_num = isdigit
        i += 1
    return runs, lone_units


def _named_fa(t):
    n = len(fa.latin_tokens(t, phrases=True)) if is_fa(t) else 0
    n += sum(1 for x in _ftoks(t) if _stem(x, BRANDS_FA))
    return n


I_FORMS = {"I", "I'm", "I've", "I'll", "I'd"}


def _ends_sentence(tok):
    return tok.rstrip("\"')”’").endswith((".", "!", "?", "؟"))


def _named_things(t):
    if is_fa(t):
        return _named_fa(t)
    toks = t.split()
    n = 0
    for prev, x in zip(toks, toks[1:]):
        c = x.strip("\"'(“‘")
        if not c[:1].isupper():
            continue
        if c.rstrip(".,!?;:\"')") in I_FORMS:
            continue
        if _ends_sentence(prev):
            continue
        n += 1
    return n + _named_fa(t)


def _concrete_count(t):
    runs, lone = numbers_fa(t)
    return len(CONCRETE.findall(_concrete_text(t))) + runs, lone


def specificity(t):
    w = words(t)
    if not w:
        return 0
    nums, lone_units = _concrete_count(t)
    fw = [fa.fold(x) for x in w]
    vague = sum(1 for x in w if x in VAGUE) + sum(1 for x in fw if _stem(x, VAGUE_FA))
    filler = sum(1 for x in w if x in FILLER) + sum(1 for x in fw if x in FILLER_FA)
    s = 34 + nums * 22 + lone_units * 11 - vague * 16 - filler * 5
    # named things: proper nouns that are not sentence-initial (English), Latin brand names and
    # Persian-letter brand names inside Persian text
    s += min(18, 6 * _named_things(t))
    return max(0, min(100, s))


def address(t):
    n = len(YOU.findall(t)) + address_fa(t)
    first6 = " ".join(t.split()[:6])
    first = 30 if (YOU.search(first6) or address_fa(first6)) else 0
    return max(0, min(100, 26 + n * 20 + first))


def stakes(t):
    fw = _ftoks(t)
    n = len(STAKE.findall(t)) + sum(1 for x in fw if (_stem(x, STAKES_FA) and x not in STAKES_NOT_FA)
                                         or x in STAKES_TOKENS_FA)
    n += _phrases(t, STAKES_PHRASES_FA)
    nums, _ = _concrete_count(t)
    return max(0, min(100, 22 + n * 26 + (14 if nums else 0)))


def _closes_itself(t):
    return bool(CLOSED_EN.search(t) or any(x in CLOSED_TOKENS_FA for x in _ftoks(t))
                or _phrases(t, CLOSED_PHRASES_FA))


def curiosity(t):
    fw = _ftoks(t)
    n = len(CURIOSITY.findall(t)) + sum(1 for x in fw if x in CURIOSITY_FA) + _phrases(t, CURIOSITY_PHRASES_FA)
    q = 18 if fa.normalize(t).rstrip(" .!»\"").endswith(("?", "؟")) else 0
    # a hook that resolves itself has no gap left
    closed = -18 if _closes_itself(t) else 0
    return max(0, min(100, 24 + n * 17 + q + closed))


def band_words(t):
    return (8, 22) if is_fa(t) else (9, 24)


def brevity(t):
    n = len(words(t))
    if n == 0:
        return 0
    lo, hi = band_words(t)
    # a spoken hook lands inside ~10 seconds: Persian 8-22 words at ~2.4 words/s, English 9-24 at 150 wpm
    if lo <= n <= hi:
        return 100
    if n < lo:
        return max(30, 100 - (lo - n) * 11)
    return max(10, 100 - (n - hi) * 7)


def seconds(t):
    return len(words(t)) / (PERSIAN_RATE if is_fa(t) else ENGLISH_RATE)


PROPS = [("SPECIFICITY", specificity), ("ADDRESS", address), ("STAKES", stakes),
         ("CURIOSITY", curiosity), ("BREVITY", brevity)]
LABEL_FA = {"SPECIFICITY": "دقت", "ADDRESS": "خطاب", "STAKES": "ریسک", "CURIOSITY": "کنجکاوی", "BREVITY": "کوتاهی"}
BAND_FA = {"STRONG": "قوی", "WORKABLE": "متوسط", "WEAK": "ضعیف"}
UNCLASSIFIED = "Unclassified"
UNCLASSIFIED_FA = "بی‌فرمول"


def match_form(t):
    """The text the formula patterns run on (see "match_on" in hooks.json)."""
    return fa.fold(t).replace("٬", ",").replace("٫", ".").replace("٪", "%")


def formula_hits(f, t):
    m = match_form(t)
    n = 0
    for p in f.get("match") or []:
        try:
            if re.search(p, m, re.I):
                n += 1
        except re.error:
            pass
    return n


def classify_formula(t):
    """(formula dict or None, hits). Most matching patterns wins; a tie goes to the formula listed first."""
    best, hits = None, 0
    for f in FORMULAS:
        n = formula_hits(f, t)
        if n > hits:
            best, hits = f, n
    return best, hits


def classify(t):
    best, hits = classify_formula(t)
    return (best["name"] if best else UNCLASSIFIED), hits


def score(t):
    parts = {n: fn(t) for n, fn in PROPS}
    vals = list(parts.values())
    verdict = round(0.6 * (sum(vals) / len(vals)) + 0.4 * min(vals))
    name, hits = classify(t)
    return parts, verdict, name, hits


def band(v):
    return "STRONG" if v >= 72 else "WORKABLE" if v >= 55 else "WEAK"


def advice(prop, t):
    if prop == "CURIOSITY" and not _closes_itself(t):
        return "یه سؤال باز کن که هنوز جوابش رو ندادی («چرا…؟»، «کدوم…؟»، «ولی…»، «هیچ‌کس…»)"
    if prop == "BREVITY":
        lo, hi = band_words(t)
        return ("%s تا %s کلمه (حدود ۳ تا ۱۰ ثانیه). بلند بخونش و هر جا نفست تموم شد، همون‌جا تمومش کن"
                % (fa.to_fa_digits(lo), fa.to_fa_digits(hi)))
    return FIX[prop]


FIX = {
    "SPECIFICITY": "یه صفت («خفن»، «فوق‌العاده») رو با یه عدد، یه اسم یا یه تاریخ عوض کن",
    "ADDRESS": "تو شش کلمه‌ی اول بیننده رو مستقیم صدا بزن: «تو/شما»، «بهت»، «کانالت»، یا یه فعل مثل «می‌دی»، «ببین»",
    "STAKES": "بگو ادامه‌دادن به روش فعلی چه هزینه‌ای براش داره (وقت، پول، بازدید، اعتبار)",
    "CURIOSITY": "نیمه‌ای از جمله رو که خودش جواب خودشه («چون…»، «یعنی…») حذف کن و سؤال رو باز بذار",
}


def _fa_num(x):
    return fa.to_fa_digits(str(x), separators=True)


def formula_fa(name):
    for f in FORMULAS:
        if f.get("name") == name:
            return f.get("name_fa") or name
    return UNCLASSIFIED_FA


def result(t):
    t = fa.normalize(t).strip()
    parts, verdict, name, hits = score(t)
    best, _ = classify_formula(t)
    low = min(parts, key=parts.get)
    return {"hook": t, "properties": parts,
            "properties_fa": {LABEL_FA[k]: v for k, v in parts.items()},
            "verdict": verdict, "band": band(verdict), "band_fa": BAND_FA[band(verdict)],
            "formula": name, "formula_fa": best.get("name_fa", name) if best else UNCLASSIFIED_FA,
            "formula_id": best.get("id") if best else None, "matched": hits,
            "lang": "fa" if is_fa(t) else "en", "words": len(words(t)), "seconds": round(seconds(t), 1),
            "weakest": low, "weakest_fa": LABEL_FA[low], "advice": advice(low, t)}


def report(r):
    t = r["hook"]
    print("\n  " + t)
    print("  " + "-" * min(72, max(20, len(t))))
    for k, v in r["properties"].items():
        print("    %-9s %4s  %s" % (LABEL_FA[k], _fa_num(v), "#" * (v // 5)))
    print("    %-9s %4s  %s" % ("حکم", _fa_num(r["verdict"]), r["band_fa"]))
    if r["matched"]:
        print("    فرمول     %s (%s) - %s الگو جور شد" % (r["formula_fa"], r["formula"], _fa_num(r["matched"])))
    else:
        print("    فرمول     هیچ فرمولی جور نشد؛ این معمولاً خلاصه است، نه هوک")
    print("    ضعیف‌ترین  %s - %s" % (r["weakest_fa"], r["advice"]))
    rate = PERSIAN_RATE if r["lang"] == "fa" else ENGLISH_RATE
    print("    طول       %s کلمه ≈ %s ثانیه (با %s کلمه در ثانیه)"
          % (_fa_num(r["words"]), _fa_num(r["seconds"]), _fa_num(rate)))


def main():
    a = sys.argv[1:]
    as_json = "--json" in a
    a = [x for x in a if x != "--json"]
    if a and a[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    if "--hook" in a:
        i = a.index("--hook")
        if i + 1 >= len(a) or not a[i + 1].strip():
            print("hookscore: بعد از --hook یه خط متن لازمه", file=sys.stderr)
            print(__doc__, file=sys.stderr)
            sys.exit(2)
        lines = [a[i + 1]]
    elif a:
        if not os.path.isfile(a[0]):
            print("hookscore: فایل پیدا نشد: %s" % a[0], file=sys.stderr)
            sys.exit(2)
        try:
            with open(a[0], encoding="utf-8-sig") as f:
                lines = f.read().splitlines()
        except (OSError, UnicodeDecodeError) as e:
            print("hookscore: فایل خونده نشد: %s (%s)" % (a[0], e), file=sys.stderr)
            sys.exit(2)
    else:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    lines = [fa.normalize(x).strip() for x in lines]
    lines = [x for x in lines if x]
    if not lines:
        print("hookscore: هیچ هوکی پیدا نشد (هر خط یه هوک)", file=sys.stderr)
        sys.exit(2)
    if not FORMULAS:
        print("hookscore: hooks.json پیدا یا خونده نشد؛ ستون فرمول خالی می‌مونه", file=sys.stderr)
    out = sorted((result(t) for t in lines), key=lambda r: -r["verdict"])
    if as_json:
        print(json.dumps([{k: v for k, v in r.items() if k != "matched"} for r in out],
                         ensure_ascii=False, indent=1))
        return
    for r in out:
        report(r)
    if len(out) > 1:
        print("\n  برنده: %s  (%s، %s)\n" % (out[0]["hook"], _fa_num(out[0]["verdict"]), out[0]["band_fa"]))


if __name__ == "__main__":
    main()
