#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fatext.py - کتابخانه‌ی مشترک متن فارسی برای ابزارهای این پک.

نسخه‌ی اصلی این فایل در lib/fatext.py است. هر مهارت (skill) که ابزار پایتونی دارد یک کپی
یکسان از آن را با نام _fatext.py کنار خودش نگه می‌دارد تا بشود هر پوشه را تنها کپی کرد.
این کپی‌ها را دستی ویرایش نکنید؛ lib/fatext.py را عوض کنید و بعد اجرا کنید:

    python3 -I scripts/sync_lib.py

استفاده در یک ابزار (با python3 -I پوشه‌ی خود اسکریپت در sys.path نیست، پس دستی اضافه‌اش کنید):

    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _fatext as fa

فقط کتابخانه‌ی استاندارد پایتون ۳.۹. منطق خواندن زیرنویس (load_cues) از deadair.py در
youtube-agent-skill اثر Jake Schincariol (مجوز MIT) گرفته شده، همراه با اصلاح باگ‌هایش.
"""
import html
import json
import math
import re
import unicodedata
from collections import namedtuple

__version__ = "1.0.0"

__all__ = [
    "normalize", "fold", "to_ascii_digits", "to_fa_digits", "parse_number",
    "tokenize", "word_count", "norm_words", "script_counts", "script_ratio", "is_persian",
    "latin_tokens", "parse_timestamp", "fmt_timestamp", "Cue", "clean_cue_text", "parse_cues",
    "load_cues", "decode_bytes", "duration", "is_filler", "is_filler_only", "strip_fillers",
    "FILLERS_FA", "HESITATIONS_FA", "DISCOURSE_FILLERS_FA", "FILLER_PHRASES_FA", "FILLERS_EN",
    "FILLER_PHRASES_EN", "STOPWORDS_FA", "STOPWORDS_EN", "ZWNJ",
]

ZWNJ = "‌"

# ---------------------------------------------------------------- characters

_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_TO_ASCII = {ord(c): str(i) for i, c in enumerate(_FA_DIGITS)}
_TO_ASCII.update({ord(c): str(i) for i, c in enumerate(_AR_DIGITS)})
_TO_FA = {ord(str(i)): c for i, c in enumerate(_FA_DIGITS)}
_TO_FA.update({ord(c): _FA_DIGITS[i] for i, c in enumerate(_AR_DIGITS)})

# Arabic letter forms -> Persian
_LETTERS = {ord("ي"): "ی",  # ي -> ی
            ord("ى"): "ی",  # ى -> ی
            ord("ك"): "ک"}  # ك -> ک
_TATWEEL = "ـ"
# bidi controls and BOM: LRM RLM ALM, LRE RLE PDF LRO RLO, LRI RLI FSI PDI, BOM/ZWNBSP
_BIDI = re.compile("[‎‏؜‪-‮⁦-⁩﻿]")
# characters people paste where a ZWNJ was meant: zero-width space, soft hyphen
_ZW_LIKE = re.compile("[​­]")
# harakat and other Arabic marks (fatha, kasra, tanvin, shadda, sukun, superscript alef, hamza marks)
_DIACRITICS = re.compile("[ً-ٰٟۖ-ۜ۟-۪ۨ-ۭ]")
_HSPACE = re.compile("[ \t  -   　]+")
_PRESENTATION = re.compile("[ﭐ-﷿ﹰ-﻾]+")
_MARK_RANGES = "̀-ًͯ-ٰٟۖ-ۭ"


def _is_wordch(ch):
    return bool(ch) and (ch.isalnum() or unicodedata.category(ch).startswith("M"))


def _fix_zwnj(text):
    out = []
    n = len(text)
    for i, ch in enumerate(text):
        if ch != ZWNJ:
            out.append(ch)
            continue
        if out and out[-1] == ZWNJ:
            continue  # doubled
        prev = out[-1] if out else ""
        j = i + 1
        while j < n and text[j] == ZWNJ:
            j += 1
        nxt = text[j] if j < n else ""
        if _is_wordch(prev) and _is_wordch(nxt):
            out.append(ch)
    return "".join(out)


def normalize(text, taa_marbuta=False, diacritics=False, digits=None):
    """متن را یکدست می‌کند: ي/ى ← ی، ك ← ک، حذف کشیده (ـ)، حذف نویسه‌های کنترل جهت (RLM/LRM/BOM و…)،
    یکی کردن نیم‌فاصله‌ها و حذف نیم‌فاصله یا فاصله‌ی تکراری. حروف «فرم نمایشی» عربی (متن کپی‌شده از PDF)
    به حرف معمولی برمی‌گردند. خط‌های جدید حفظ می‌شوند.

    taa_marbuta=True: ة ← ه.  diacritics=True: اعراب (ـَ ـِ ـُ ـً ـّ ـْ ـٰ ـٔ) حذف می‌شود.
    digits='ascii' یا 'fa': رقم‌ها هم یکدست می‌شوند؛ None (پیش‌فرض) یعنی دست نزن.
    """
    if not text:
        return "" if text is None else text
    text = str(text)
    text = _PRESENTATION.sub(lambda m: unicodedata.normalize("NFKC", m.group(0)), text)
    text = _BIDI.sub("", text)
    text = text.translate(_LETTERS).replace(_TATWEEL, "")
    if taa_marbuta:
        text = text.replace("ة", "ه")
    if diacritics:
        text = _DIACRITICS.sub("", text)
    # ZWSP / soft hyphen between two letters -> ZWNJ, anywhere else -> nothing
    text = _ZW_LIKE.sub(ZWNJ, text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for line in text.split("\n"):
        line = _HSPACE.sub(" ", line)
        line = _fix_zwnj(line)
        line = _HSPACE.sub(" ", line).strip()
        lines.append(line)
    text = "\n".join(lines)
    if digits == "ascii":
        text = to_ascii_digits(text)
    elif digits == "fa":
        text = to_fa_digits(text)
    return text.strip("\n ")


def fold(text):
    """شکل «مقایسه‌ای» یک متن: یکدست‌شده، بدون اعراب، رقم انگلیسی، حروف کوچک لاتین، بدون نیم‌فاصله
    و آ ← ا. برای اینکه «می‌خوام» و «میخوام» یا «آرتیفکت» و «ارتیفکت» یکی حساب شوند. برای نمایش نیست."""
    t = normalize(text, taa_marbuta=True, diacritics=True, digits="ascii")
    t = t.replace(ZWNJ, "").replace("آ", "ا").replace("أ", "ا").replace("إ", "ا")
    t = t.replace("ۀ", "ه").replace("ؤ", "و")
    return t.lower()


def to_ascii_digits(text):
    """رقم‌های فارسی (۰-۹) و عربی (٠-٩) را به رقم انگلیسی (0-9) تبدیل می‌کند. بقیه‌ی متن دست نمی‌خورد."""
    return str(text).translate(_TO_ASCII)


def to_fa_digits(text, separators=False):
    """رقم‌های انگلیسی و عربی را به رقم فارسی تبدیل می‌کند.
    separators=True: نقطه‌ی اعشار بین دو رقم ← ٫ و ویرگول هزارگان بین دو رقم ← ٬ (مثل ۱۲٬۴۰۰ و ۱٫۵)."""
    text = str(text).translate(_TO_FA)
    if separators:
        text = re.sub(r"(?<=[۰-۹])\.(?=[۰-۹])", "٫", text)
        text = re.sub(r"(?<=[۰-۹]),(?=[۰-۹]{3})", "٬", text)
    return text


# ---------------------------------------------------------------- numbers

_MULT = [  # longest first
    ("میلیارد", 1e9), ("بیلیون", 1e9), ("billion", 1e9), ("bn", 1e9), ("b", 1e9),
    ("میلیون", 1e6), ("ملیون", 1e6), ("million", 1e6), ("mln", 1e6), ("mn", 1e6), ("m", 1e6),
    ("هزار", 1e3), ("thousand", 1e3), ("کا", 1e3), ("k", 1e3),
    ("تریلیون", 1e12), ("trillion", 1e12),
]
_MULT.sort(key=lambda p: -len(p[0]))
# a leading separator counts only when it is not glued to a word or another number: «٫۵» = 0.5, «.5k» = 500
_NUM = re.compile(r"(?P<sign>(?<![\w.,])[-−+])?"
                  r"(?P<num>(?:(?<![\w.,٫٬])[.٫](?=\d))?\d+(?:[.,/'٫٬،]\d+)*)")
# single ASCII letters that are a multiplier only when they touch the digits ("4.5M" yes, "5 m" no:
# "m" is also minutes / metres)
_TOUCH_ONLY = frozenset(["m", "b"])

_FA_WORD_NUM = {
    "صفر": 0, "یک": 1, "یه": 1, "دو": 2, "سه": 3, "چهار": 4, "چار": 4, "پنج": 5, "شش": 6, "شیش": 6,
    "هفت": 7, "هشت": 8, "نه": 9, "ده": 10, "یازده": 11, "دوازده": 12, "سیزده": 13, "چهارده": 14,
    "پانزده": 15, "پونزده": 15, "شانزده": 16, "شونزده": 16, "هفده": 17, "هیفده": 17, "هجده": 18,
    "هیجده": 18, "نوزده": 19, "بیست": 20, "سی": 30, "چهل": 40, "پنجاه": 50, "شصت": 60, "هفتاد": 70,
    "هشتاد": 80, "نود": 90, "صد": 100, "یکصد": 100, "دویست": 200, "سیصد": 300, "چهارصد": 400,
    "پانصد": 500, "پونصد": 500, "ششصد": 600, "هفتصد": 700, "هشتصد": 800, "نهصد": 900,
}
_FA_WORD_SCALE = {"هزار": 1e3, "میلیون": 1e6, "ملیون": 1e6, "میلیارد": 1e9, "بیلیون": 1e9}


def _num_core(s):
    """'12,400' / '1.5' / '1,5' / '1.234.567' / '۱/۵' (ASCII digits already) -> float."""
    s = s.replace("٫", ".").replace("٬", ",").replace("،", ",").replace("'", ",")
    if "/" in s:
        parts = s.split("/")
        if len(parts) != 2 or "," in s or "." in s:
            return None
        s = parts[0] + "." + parts[1]  # Persian handwriting decimal: ۱/۵ = 1.5
    dots, commas = s.count("."), s.count(",")
    if dots and commas:
        # the later separator is the decimal one: 1,234.5 or 1.234,5
        if s.rfind(".") > s.rfind(","):
            s = s.replace(",", "")
        else:
            s = s.replace(".", "").replace(",", ".")
    elif commas:
        groups = s.split(",")
        if commas == 1 and len(groups[1]) != 3:
            s = s.replace(",", ".")  # 1,5 = 1.5
        elif all(len(g) == 3 for g in groups[1:]) and 1 <= len(groups[0]) <= 3:
            s = s.replace(",", "")
        else:
            return None
    elif dots > 1:
        groups = s.split(".")
        if all(len(g) == 3 for g in groups[1:]) and 1 <= len(groups[0]) <= 3:
            s = s.replace(".", "")
        else:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def _combine(items, strict=False):
    """Add up number parts in order: ('v', value, is_digits), ('s', scale), ('and',), ('half',).
    «یک و نیم میلیون» = 1.5e6، «نیم میلیون» = 5e5، «دو میلیون و نیم» = 2.5e6، «۱۲ هزار و ۵۰۰» = 12500.
    strict=True: None for anything that is not one well-formed number (two numbers with no «و» between
    them, a later scale that is not smaller than the one before, «و» at the start or end, …)."""
    total, cur, last, used, half = 0.0, 0.0, 0.0, False, False
    prev = None          # kind of the previous item
    grp = []             # values added in the current group: (value, is_digits)
    for it in items:
        k = it[0]
        if k == "and":
            if strict and prev in (None, "and"):
                return None
            prev = k
            continue
        if k == "half":
            if strict and (half or prev not in (None, "and") or (prev is None and grp)):
                return None
            half = used = True
        elif k == "v":
            val, digits = it[1], it[2]
            if strict:
                if half or (prev is not None and prev != "and"):
                    return None
                if grp:
                    pv, pdig = grp[-1]
                    place = 10 ** int(math.floor(math.log10(pv))) if pv >= 10 else 0
                    if digits or pdig or not place or pv % place or val >= place:
                        return None
            cur += val
            grp.append((val, digits))
            used = True
        else:  # scale
            scale = it[1]
            if strict and (prev == "and" or (last and scale >= last)):
                return None
            base = ((cur + 0.5) if cur else 0.5) if half else (cur or 1)
            if strict and last and base * scale >= last:
                return None
            total += base * scale
            last = scale
            cur, half, used, grp = 0.0, False, True, []
        prev = k
    if not used or (strict and prev == "and"):
        return None
    if half:
        rest = (cur + 0.5) if cur else 0.5 * (last or 1)
    else:
        rest = cur
    if strict and last and rest >= last:
        return None
    return total + rest


def _words_number(words):
    """Persian spelled-out number from a token list: ['یک', 'و', 'نیم', 'میلیون'] -> 1.5e6."""
    items = []
    for w in words:
        if w == "و":
            items.append(("and",))
        elif w in ("نیم", "نیمه"):
            items.append(("half",))
        elif w in _FA_WORD_NUM:
            items.append(("v", float(_FA_WORD_NUM[w]), False))
        elif w in _FA_WORD_SCALE:
            items.append(("s", _FA_WORD_SCALE[w]))
        else:
            break
    return _combine(items)


_APPROX = ("حدود", "تقریبا", "نزدیک", "بیش", "بیشتر", "بالای", "کمتر", "زیر", "از", "به")
_UNIT_WORDS = frozenset(fold(w) for w in (
    "بازدید", "ویو", "ویوز", "سابسکرایبر", "سابسکرایب", "مشترک", "دنبال‌کننده", "دنبال‌کننده‌ها", "فالوور",
    "فالوئر", "لایک", "کامنت", "نظر", "تومان", "تومن", "دلار", "ریال", "نفر", "تا", "بار", "views", "view",
    "subscribers", "followers", "likes"))


def _spelled_number(t):
    """Only a whole spelled-out number (optionally after «حدود» and before a unit word); never a guess."""
    words = [w for w in re.split(r"[\s،,]+", fold(t)) if w]
    while words and words[0] in _APPROX:
        words = words[1:]
    while words and words[-1] in _UNIT_WORDS:
        words = words[:-1]
    if not words:
        return None
    known = set(_FA_WORD_NUM) | set(_FA_WORD_SCALE) | {"و", "نیم"}
    if any(w not in known for w in words) or words[0] == "و" or words[-1] == "و":
        return None
    has_scale = any(w in _FA_WORD_SCALE for w in words)
    if not has_scale and len(words) == 1 and words[0] in ("نه", "یه", "سی", "صد", "ده", "نیم"):
        # «نه» = no, «یه» = a, «سی/صد/ده» are also ordinary words: too ambiguous alone
        return None
    return _words_number(words)


_MULT_D = dict(_MULT)
_FOLD_APPROX = frozenset(fold(w) for w in _APPROX)
_SCALE_SUFFIX = ("تا", "ی", "ای")
_STRICT_TOK = re.compile(r"(?P<sp>\s+)|(?P<num>(?:[.٫](?=\d))?\d+(?:[.,/'٫٬،]\d+)*)|(?P<word>[^\W\d_]+)"
                         r"|(?P<pct>[%٪])|(?P<sign>[-−+](?=[.٫]?\d))")
_AMBIGUOUS_ALONE = frozenset(["نه", "یه", "سی", "صد", "ده"])


def _strict_word(w, attached):
    """One letter run of a strict number: an item tuple, ('approx',), ('unit',) or None (unknown)."""
    f = fold(w)
    if f == "و":
        return ("and",)
    if f in ("نیم", "نیمه"):
        return ("half",)
    if f in _FA_WORD_NUM:
        return ("v", float(_FA_WORD_NUM[f]), False)
    if f in _FA_WORD_SCALE:
        return ("s", _FA_WORD_SCALE[f])
    if f in _MULT_D:
        if f in _TOUCH_ONLY and not attached:
            return None
        return ("s", _MULT_D[f])
    for sw, sc in _FA_WORD_SCALE.items():  # «هزارتا»، «میلیونی»
        if f.startswith(sw) and f[len(sw):] in _SCALE_SUFFIX:
            return ("s", sc)
    if f in _FOLD_APPROX:
        return ("approx",)
    if f in _UNIT_WORDS:
        return ("unit",)
    return None


def _parse_strict(t):
    """The whole text must be one number (see parse_number strict=True); t is normalized, ASCII digits."""
    t = normalize(t, diacritics=True).replace(ZWNJ, " ").lower()
    items, pos, neg, attached = [], 0, False, False
    while pos < len(t):
        m = _STRICT_TOK.match(t, pos)
        if not m:
            return None
        pos = m.end()
        kind = m.lastgroup
        if kind == "sp":
            attached = False
            continue
        if kind == "sign":
            if items:
                return None
            neg = m.group(0) in ("-", "−")
            attached = False
            continue
        if kind == "num":
            if items and items[-1][0] == "v":
                return None
            v = _num_core(m.group("num"))
            if v is None:
                return None
            items.append(("v", v, True))
            attached = True
            continue
        if kind == "pct":
            items.append(("pct",))
            attached = False
            continue
        it = _strict_word(m.group(0), attached and items and items[-1][0] == "v" and items[-1][2])
        if it is None:
            return None
        items.append(it)
        attached = False
    while items and items[0][0] in ("approx", "pct"):
        items.pop(0)
    while items and items[-1][0] in ("unit", "pct"):
        items.pop()
    if not items or any(it[0] in ("approx", "unit", "pct") for it in items):
        return None
    if neg and not (items[0][0] == "v" and items[0][2]):
        return None
    if len(items) == 1 and items[0][0] == "half":
        return None
    if len(items) == 1 and items[0][0] == "v" and not items[0][2] \
            and any(fold(w) in _AMBIGUOUS_ALONE for w in t.split()):
        return None  # «نه» = no, «یه» = a, «سی/صد/ده» are also ordinary words: too ambiguous alone
    val = _combine(items, strict=True)
    if val is None:
        return None
    return -val if neg else val


def parse_number(s, strict=False):
    """یک عدد را از متن برمی‌گرداند (float) یا None اگر عددی نبود. هیچ عددی حدس زده نمی‌شود.

    می‌فهمد: «۱٫۲ هزار»، «1.2K»، «۳ میلیون»، «12,400»، «۱۲٬۴۰۰»، «4.5M views»، «۱۲ هزار بازدید»، «1.2B»،
    «۱/۵ میلیون» (اسلش به‌جای ممیز)، «45%»، «−۳»، «٫۵»، و عدد حروفی: «یک و نیم میلیون»، «نیم میلیون»،
    «دو میلیون و نیم»، «سیصد هزار»، «هزار». پسوند تک‌حرفی m و b فقط وقتی چسبیده به عدد است ضرب می‌شود
    («4.5M» بله، «5 m» نه: m می‌تواند دقیقه یا متر باشد).

    strict=False (پیش‌فرض): اولین عدد متن، و بقیه‌ی متن نادیده گرفته می‌شود (برای متن آزاد).
    strict=True (برای عددی که کاربر وارد کرده): کل متن باید یک عدد باشد، وگرنه None. واژه‌ی تقریب در اول
    («حدود»، «بیش از») و واحد در آخر («بازدید»، «تا»، «٪») مجاز است، و عدد رقمی و حروفی با «و» جمع
    می‌شوند: «۱۲ هزار و ۵۰۰» = 12500، «۲ میلیون و ۳۰۰ هزار» = 2300000. بازه («بین ۵ تا ۸ هزار»، «12K-15K»)،
    دو عدد بی «و»، زمان («8:30»)، تاریخ و هر واژه‌ی ناشناخته («زیاد ۵») = None.
    """
    if s is None:
        return None
    if isinstance(s, (int, float)) and not isinstance(s, bool):
        f = float(s)
        return f if math.isfinite(f) else None
    t = normalize(str(s), digits="ascii")
    if strict:
        return _parse_strict(t)
    t = t.replace(ZWNJ, " ")
    m = _NUM.search(t)
    if not m:
        return _spelled_number(t)
    val = _num_core(m.group("num"))
    if val is None:
        return None
    tail = t[m.end():].lower()
    rest = tail.lstrip()
    for word, mult in _MULT:
        if word in _TOUCH_ONLY:
            if not tail.startswith(word):
                continue
        elif not rest.startswith(word):
            continue
        after = rest[len(word):len(word) + 1]
        # a short suffix must end there ("4.5M views" yes, "5 minutes" / «۵ کانال» no);
        # long Persian words may take a suffix («هزارتا»، «میلیونی»)
        if after and after.isalpha() and (word.isascii() or len(word) < 3):
            continue
        val *= mult
        break
    if m.group("sign") in ("-", "−"):
        val = -val
    return val


# ---------------------------------------------------------------- words

_W = r"(?:[^\W_]|[" + _MARK_RANGES + r"])"
_WORD = re.compile(
    _W + r"+(?:(?:‌|(?<=[^\W\d_])['’\-](?=[^\W\d_])|(?<=\d)[.,/:٫٬](?=\d))" + _W + r"+)*")


def tokenize(text, normalized=True):
    """متن را به کلمه‌ها می‌شکند (فارسی و لاتین). نیم‌فاصله داخل کلمه می‌ماند («می‌خوام» یک کلمه است)،
    عدد اعشاری و هزارگان یک کلمه‌اند («۱٫۵»، «12,400»)، «don't» و «mind-blowing» یک کلمه‌اند؛
    نشانه‌ها (، ؛ ؟ « » … ! . , ? # _ و…) حذف می‌شوند. normalized=False: متن را قبلش یکدست نکن."""
    if not text:
        return []
    if normalized:
        text = normalize(text)
    return _WORD.findall(text)


def word_count(text):
    """تعداد کلمه‌های یک متن فارسی/انگلیسی/مخلوط (همان tokenize)."""
    return len(tokenize(text))


def norm_words(text):
    """کلمه‌ها به شکل مقایسه‌ای (fold): برای پیدا کردن تکرار و شروع دوباره‌ی جمله. رقم‌ها می‌مانند."""
    return [w for w in (fold(t) for t in tokenize(text)) if w]


def _script_of(ch):
    o = ord(ch)
    if 0x0600 <= o <= 0x06FF or 0x0750 <= o <= 0x077F or 0x08A0 <= o <= 0x08FF \
            or 0xFB50 <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF:
        return "fa"
    if o < 0x0250 or 0x1E00 <= o <= 0x1EFF:
        return "latin"
    return "other"


def script_counts(text):
    """تعداد حرف‌ها به تفکیک خط: {'fa': …, 'latin': …, 'other': …}. رقم و نشانه شمرده نمی‌شوند."""
    out = {"fa": 0, "latin": 0, "other": 0}
    for ch in text or "":
        if ch.isalpha():
            out[_script_of(ch)] += 1
    return out


def script_ratio(text):
    """سهم حرف‌های فارسی/عربی از همه‌ی حرف‌ها (۰ تا ۱). متن بی‌حرف = 0.0."""
    c = script_counts(text)
    total = c["fa"] + c["latin"] + c["other"]
    return c["fa"] / total if total else 0.0


def is_persian(text, threshold=0.5):
    """آیا متن بیشتر فارسی است؟ (سهم حرف فارسی ≥ threshold)."""
    return script_ratio(text) >= threshold


def latin_tokens(text, phrases=False):
    """کلمه‌های با خط لاتین داخل متن (معمولاً اسم‌ها: Claude، ChatGPT، YouTube Studio) با همان حروف اصلی.
    phrases=True: کلمه‌های لاتینِ پشت‌سرهم که فقط با فاصله جدا شده‌اند یک عبارت می‌شوند («YouTube Studio»)."""
    toks = [t for t in tokenize(text) if any(c.isalpha() and _script_of(c) == "latin" for c in t)]
    if not phrases:
        return toks
    out = []
    norm = normalize(text or "")
    for m in re.finditer(r"[A-Za-zÀ-ɏ0-9][A-Za-zÀ-ɏ0-9'’.\-+]*"
                         r"(?: [A-Za-zÀ-ɏ0-9][A-Za-zÀ-ɏ0-9'’.\-+]*)*", norm):
        p = m.group(0).strip(".-'’")
        if any(c.isalpha() for c in p):
            out.append(p)
    return out


# ---------------------------------------------------------------- timestamps

_UNITS = re.compile(r"^(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?$")


def parse_timestamp(s):
    """زمان را به ثانیه (float) تبدیل می‌کند، یا None اگر خوانا نبود.
    شکل‌ها: «1:02:03»، «02:03»، «00:00:01,000» (SRT)، «00:01.000» (VTT)، «75» یا «75.5» ثانیه، «1h2m3s»،
    با رقم فارسی («۱:۲۳») و ممیز , . یا ٫ برای میلی‌ثانیه."""
    if s is None:
        return None
    if isinstance(s, (int, float)) and not isinstance(s, bool):
        return float(s) if math.isfinite(s) and s >= 0 else None
    t = normalize(str(s), digits="ascii").replace("٫", ".").replace(",", ".").strip().lower()
    if not t:
        return None
    m = _UNITS.match(t)
    if m and any(m.groups()) and not re.fullmatch(r"[\d.]+", t):
        h, mi, se = (float(g) if g else 0.0 for g in m.groups())
        return h * 3600 + mi * 60 + se
    parts = t.split(":")
    if not 1 <= len(parts) <= 3:
        return None
    try:
        sec = float(parts[-1]) if re.fullmatch(r"\d+(?:\.\d+)?", parts[-1]) else None
        if sec is None:
            return None
        nums = []
        for p in parts[:-1]:
            if not p.isdigit():
                return None
            nums.append(int(p))
    except ValueError:
        return None
    if len(parts) > 1 and sec >= 60:
        return None
    if len(parts) == 3 and nums[1] >= 60:
        return None
    total = sec
    for i, n in enumerate(reversed(nums)):
        total += n * (60 ** (i + 1))
    return total


def fmt_timestamp(seconds, style="yt", fa_digits=False):
    """ثانیه را به متن زمان تبدیل می‌کند.
    style='yt': «4:05» یا «1:04:05» (برای فصل‌ها و توضیحات یوتیوب، ثانیه رو به پایین گرد می‌شود)؛
    'srt': «00:04:05,250»؛ 'vtt': «00:04:05.250»؛ 'clock': «00:04:05». fa_digits=True: با رقم فارسی."""
    seconds = float(seconds or 0)
    if not math.isfinite(seconds):
        raise ValueError("time is not finite")
    seconds = max(0.0, seconds)
    if style in ("srt", "vtt"):
        ms = int(round(seconds * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        out = "%02d:%02d:%02d%s%03d" % (h, m, s, "," if style == "srt" else ".", ms)
    else:
        t = int(seconds)
        h, m, s = t // 3600, (t % 3600) // 60, t % 60
        if style == "clock":
            out = "%02d:%02d:%02d" % (h, m, s)
        elif style == "yt":
            out = "%d:%02d:%02d" % (h, m, s) if h else "%d:%02d" % (m, s)
        else:
            raise ValueError("style must be yt, srt, vtt or clock")
    return to_fa_digits(out) if fa_digits else out


# ---------------------------------------------------------------- transcripts

Cue = namedtuple("Cue", "start end text")

# Known subtitle markup only: VTT/SRT tags (<i>, <b>, <u>, <s>, <c.class>, <v Name>, <lang fa>, <ruby>,
# <rt>, <font color=…>, <br>), karaoke timestamps (<00:00:01.000>) and SSA override blocks ({\an8}).
# Anchored to the tag names so real text survives: «x < 10 و y > 3»، «{name}»، «List<int>».
_TAGS = re.compile(r"</?(?:i|b|u|s|c|ruby|rt|br)(?:\.[\w.-]*)?\s*/?>"   # <i> </b> <c.colorE5E5E5> <br/>
                   r"|</(?:v|lang|font)>"
                   r"|<(?:v|lang)(?:\.[\w.-]*)?\s[^<>]*>"              # <v Al> <lang fa>
                   r"|<font\s+[a-z-]+\s*=[^<>]*>"                        # <font color="#ff0">
                   r"|<\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3}>|\{\\[^}]*\}", re.I)
# YouTube auto (rolling) captions carry karaoke timestamps or <c> tags; only those get line dedupe.
_AUTO_VTT = re.compile(r"<\d{2}:\d{2}:\d{2}\.\d{3}>|<c[.>]")
_TIMING = re.compile(r"^\s*(\d[\d:.,٫]*)\s*-->\s*(\d[\d:.,٫]*)")
# Rolling-caption snapshot cues (YouTube auto VTT) are ~10 ms long and only repeat the line above.
_MIN_VTT_CUE = 0.05


def clean_cue_text(text, normalized=True, strip_tags=True):
    """متن یک خط زیرنویس را تمیز می‌کند: برچسب‌های شناخته‌شده‌ی زیرنویس (<i>، <b>، <c>، <v …>، <font …>،
    <00:00:01.000>، {\\an8}) و &nbsp; و… حذف و (پیش‌فرض) با normalize یکدست می‌شود. متن واقعی مثل
    «x < 10»، «{name}» یا «List<int>» دست نمی‌خورد. strip_tags=False: برچسبی حذف نشود (متن JSON ویسپر)."""
    text = text or ""
    if strip_tags:
        text = _TAGS.sub("", text)
    text = html.unescape(text)
    return normalize(text) if normalized else text.strip()


def _num(v):
    if isinstance(v, bool) or v is None:
        raise ValueError("no time")
    if isinstance(v, (int, float)):
        f = float(v)
        if not math.isfinite(f) or f < 0:
            raise ValueError("bad time %r" % (v,))
        return f
    t = parse_timestamp(v)
    if t is None:
        raise ValueError("bad time %r" % (v,))
    return t


def _seg_times(s):
    if "start" in s or "end" in s:
        a = _num(s.get("start"))
        b = s.get("end")
        return a, (_num(b) if b is not None else a)
    if "start_time" in s:
        a = _num(s["start_time"])
        return a, _num(s.get("end_time", a))
    ts = s.get("timestamp")
    if isinstance(ts, (list, tuple)) and ts:
        a = _num(ts[0])
        return a, (_num(ts[1]) if len(ts) > 1 and ts[1] is not None else a)
    off = s.get("offsets")
    if isinstance(off, dict) and "from" in off:  # whisper.cpp: milliseconds
        return _num(off["from"]) / 1000.0, _num(off.get("to", off["from"])) / 1000.0
    tss = s.get("timestamps")
    if isinstance(tss, dict) and "from" in tss:
        return _num(tss["from"]), _num(tss.get("to", tss["from"]))
    raise ValueError("no time")


def _word_text(w):
    return w.get("word") if w.get("word") is not None else (w.get("text") or "")


def _join_words(words):
    texts = [str(_word_text(w)) for w in words if isinstance(w, dict)]
    if any(t[:1].isspace() for t in texts):
        return "".join(texts)
    return " ".join(texts)


def _word_cues(words, normalized):
    out = []
    for w in words:
        if not isinstance(w, dict):
            continue
        try:
            a, b = _seg_times(w)
        except (ValueError, TypeError):
            continue
        t = clean_cue_text(str(_word_text(w)), normalized, strip_tags=False)
        if t:
            out.append(Cue(a, max(a, b), t))
    return out


def _group_words(wcues, gap=0.5, max_words=15):
    out, cur = [], []
    for c in sorted(wcues, key=lambda c: (c.start, c.end)):
        if cur and (c.start - cur[-1].end > gap or len(cur) >= max_words
                    or cur[-1].text[-1:] in ".?!؟…"):
            out.append(Cue(cur[0].start, max(x.end for x in cur), " ".join(x.text for x in cur)))
            cur = []
        cur.append(c)
    if cur:
        out.append(Cue(cur[0].start, max(x.end for x in cur), " ".join(x.text for x in cur)))
    return out


def _load_json(d, words, normalized):
    segs = None
    if isinstance(d, list):
        segs = d
    elif isinstance(d, dict):
        for k in ("segments", "chunks", "transcription", "cues", "results"):
            if isinstance(d.get(k), list):
                segs = d[k]
                break
        if segs is None and isinstance(d.get("words"), list):
            wc = _word_cues(d["words"], normalized)
            return wc if words else _group_words(wc)
    segs = [s for s in (segs or []) if isinstance(s, dict)]
    # a bare word list (each item one word, no sentence text)
    if segs and all(("word" in s and "text" not in s) for s in segs):
        wc = _word_cues(segs, normalized)
        return wc if words else _group_words(wc)
    out = []
    for s in segs:
        ws = s.get("words") if isinstance(s.get("words"), list) else None
        if words and ws:
            out.extend(_word_cues(ws, normalized))
            continue
        try:
            a, b = _seg_times(s)
        except (ValueError, TypeError):
            continue
        text = s.get("text")
        if text is None and ws:
            text = _join_words(ws)
        t = clean_cue_text(str(text or ""), normalized, strip_tags=False)
        if t:
            out.append(Cue(a, max(a, b), t))
    return out


def parse_cues(raw, kind=None, words=False, normalized=True):
    """متن کامل یک فایل زیرنویس/رونوشت را به فهرست Cue(start, end, text) مرتب‌شده تبدیل می‌کند.
    kind: 'srt'، 'vtt'، 'json' یا None (خودش تشخیص می‌دهد). words=True: اگر JSON سطح کلمه داشت،
    هر کلمه یک Cue. normalized=False: متن را یکدست نکن (مثلاً برای بازبینی خود زیرنویس)."""
    raw = (raw or "").lstrip("﻿")
    if kind == "json" or (kind is None and raw.lstrip().startswith(("{", "["))):
        try:
            cues = _load_json(json.loads(raw), words, normalized)
            return sorted(cues, key=lambda c: (c.start, c.end))
        except (ValueError, RecursionError):
            if kind == "json":
                return []
            # not JSON after all - try it as srt / vtt
    is_vtt = kind == "vtt" or (kind is None and raw.lstrip().startswith("WEBVTT"))
    auto = is_vtt and bool(_AUTO_VTT.search(raw))
    lines = raw.splitlines()
    cues, cur = [], None
    for i, line in enumerate(lines):
        m = _TIMING.match(line)
        if m:
            a, b = parse_timestamp(m.group(1)), parse_timestamp(m.group(2))
            if a is None or b is None:
                cur = None
                continue
            cur = [a, max(a, b), []]
            cues.append(cur)
        elif not line.strip():
            # A blank line ends the cue, so cue ids, SRT index lines and NOTE / STYLE / REGION
            # blocks that follow are never glued onto it. A whitespace-only line straight after
            # the timing line (YouTube auto VTT puts one there) does not end it.
            if cur is not None and (cur[2] or line == ""):
                cur = None
        elif cur is not None:
            # malformed SRT without blank lines: an index line right before the next timing line
            if line.strip().isdigit() and i + 1 < len(lines) and _TIMING.match(lines[i + 1]):
                cur = None
                continue
            t = clean_cue_text(line, normalized)
            if t:
                cur[2].append(t)
    if is_vtt:
        kept, last = [], None
        for a, b, t in cues:
            if b - a < _MIN_VTT_CUE:
                continue
            # a rolling carry-over cue holds the carried line plus a new one; a single line equal to the
            # previous one in a hand-made VTT is real repeated speech («آره»، «[موسیقی]») and stays
            if auto or len(t) > 1:
                while t and last is not None and t[0] == last:
                    t = t[1:]
            if t:
                kept.append((a, b, t))
                last = t[-1]
        cues = kept
    out = [Cue(a, b, " ".join(t)) for a, b, t in cues if t]
    return sorted(out, key=lambda c: (c.start, c.end))


def decode_bytes(data):
    """بایت‌های یک فایل متنی را به متن تبدیل می‌کند و رمزگذاری را خودش تشخیص می‌دهد: BOM (UTF-8 یا UTF-16)،
    UTF-16 بی BOM (از روی بایت‌های صفر)، UTF-8، و بعد ویندوز فارسی (cp1256، زیرنویس‌ها و CSVهای قدیمی).
    در cp1256 «ي» و «ك» عربی به «ی» و «ک» فارسی برمی‌گردند. اگر هیچ‌کدام نشد، UTF-8 با جایگزینی نویسه‌ی خراب."""
    if isinstance(data, str):
        return data
    data = bytes(data or b"")
    if data[:3] == b"\xef\xbb\xbf":
        return data[3:].decode("utf-8", errors="replace")
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            pass
    sample = data[:4000]
    if len(sample) >= 4:
        half = len(sample) // 2
        nul_odd = sample[1::2].count(0)   # ASCII in UTF-16-LE: "a\0"
        nul_even = sample[0::2].count(0)  # ASCII in UTF-16-BE: "\0a"
        for enc, hit, miss in (("utf-16-le", nul_odd, nul_even), ("utf-16-be", nul_even, nul_odd)):
            if hit >= 0.2 * half and hit > 4 * miss:
                try:
                    return data[:len(data) - len(data) % 2].decode(enc)
                except UnicodeDecodeError:
                    pass
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp1256").translate(_LETTERS)
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


def load_cues(path, words=False, normalized=True):
    """فایل SRT، VTT (همراه با زیرنویس خودکار یوتیوب، NOTE و شناسه‌ی cue) یا JSON ویسپر (dict با
    segments، فهرست ساده، سطح کلمه، whisper.cpp، chunks) را می‌خواند و فهرست مرتب Cue(start, end, text)
    برمی‌گرداند. رمزگذاری با decode_bytes تشخیص داده می‌شود (UTF-8، UTF-16، ویندوز فارسی cp1256)؛ BOM مشکلی ندارد؛ cue خالی حذف می‌شود و عدد تنها متن حساب می‌شود.
    خطای نبودن فایل یا پوشه بودن مسیر (OSError) را خود ابزار باید بگیرد."""
    with open(path, "rb") as fh:
        raw = decode_bytes(fh.read())
    kind = "json" if str(path).lower().endswith(".json") else None
    cues = parse_cues(raw, kind=kind, words=words, normalized=normalized)
    if not cues and kind == "json":
        cues = parse_cues(raw, kind=None, words=words, normalized=normalized)
    return cues


def duration(cues):
    """طول رونوشت = بیشترین زمان پایان (نه پایان آخرین cue). فهرست خالی = 0.0."""
    return max((c[1] for c in cues), default=0.0)


# ---------------------------------------------------------------- lexicon

# Hesitation sounds (stored folded: no harakat, ا not آ). «اِ» is folded to «ا».
HESITATIONS_FA = frozenset(["ا", "اه", "ام", "اوم", "اهم", "اوهوم", "هوم", "مم", "ممم", "ااا", "اممم"])
# Discourse words that are fillers only when they stand alone («دیگه» in «دیگه نمی‌خوام» is not).
DISCOURSE_FILLERS_FA = frozenset(["خب", "خُب", "یعنی", "چیزه", "ببین", "ببینید", "حالا", "مثلا", "مثلاً",
                                  "اوکی", "اوکِی", "آره", "دیگه", "بله", "باشه"])
FILLER_PHRASES_FA = ("به هر حال", "بهرحال", "به هرحال", "چی بگم", "چیز ه")
FILLERS_FA = frozenset(set(HESITATIONS_FA) | set(DISCOURSE_FILLERS_FA) | {"به هر حال"})

FILLERS_EN = frozenset(["um", "umm", "uh", "uhh", "er", "erm", "ah", "hmm", "mm", "so", "okay", "ok",
                        "right", "yeah", "like", "anyway", "basically", "actually"])
FILLER_PHRASES_EN = ("you know", "i mean", "let me see", "hold on", "sort of", "kind of")

_FOLD_HES = frozenset(fold(w) for w in HESITATIONS_FA)
_FOLD_DIS = frozenset(fold(w) for w in DISCOURSE_FILLERS_FA)
_FOLD_PHR = tuple(sorted({tuple(fold(p).split()) for p in FILLER_PHRASES_FA + FILLER_PHRASES_EN},
                         key=lambda p: -len(p)))
# elongated hesitations: اااا، اممم، ممم، اوووم، ااام، ههه‌م، umm, uhhh, hmmm
_ELONG = re.compile(r"^(?:ا+|ا+م+|ا*و+م+|ه+م{2,}|ه{2,}م+|م{2,}|ا+ه+|u+m+|u+h+|h+m+|e+r+m*|a+h+)$")
# hesitations that are never a real word, so they go wherever they stand (also in cautious mode)
_HES_SURE = frozenset(["um", "umm", "uh", "uhh", "erm", "hmm", "mm", "ممم", "اممم", "ااا", "اوم", "اوهوم"])


def _sure_hesitation(tok):
    f = fold(tok)
    if not f:
        return False
    if f in _HES_SURE or ("ِ" in tok and f in _FOLD_HES):  # «اِ»، «اِم» written with kasra
        return True
    return bool(_ELONG.match(f)) and len(f) >= 3 and len(set(f)) <= 2


def is_filler(word):
    """آیا این یک کلمه (فارسی یا انگلیسی) پرکننده است؟ مثل «اِ»، «اممم»، «خب»، «یعنی»، «um»، «basically»."""
    w = fold(word)
    if not w:
        return False
    return w in _FOLD_HES or w in _FOLD_DIS or w in FILLERS_EN or bool(_ELONG.match(w))


def _filler_spans(ws):
    """Return True if the folded word list is fillers only."""
    i = 0
    while i < len(ws):
        for ph in _FOLD_PHR:
            if tuple(ws[i:i + len(ph)]) == ph:
                i += len(ph)
                break
        else:
            if not is_filler(ws[i]):
                return False
            i += 1
    return True


def is_filler_only(text):
    """آیا کل این متن (مثلاً یک cue) فقط پرکننده است؟ «خب، یعنی…» یا «Um? you know» = بله. عدد تنها = نه."""
    ws = norm_words(text)
    return bool(ws) and _filler_spans(ws)


_CHUNK_SEP = re.compile(r"([،,.;؛:!?؟…\n«»\"“”()\[\]–—]+|\s-\s)")


def strip_fillers(text, aggressive=False):
    """پرکننده‌ها را از متن برمی‌دارد و بقیه را دست نمی‌زند.
    پیش‌فرض (محتاط): صداهای کشیده‌ی تردید («اممم»، «ااا»، «اِ») هر جا باشند حذف می‌شوند، و بقیه‌ی
    پرکننده‌ها («خب»، «یعنی»، «دیگه»، «به هر حال»، «so»، «you know») فقط وقتی تنها و جدا با نشانه آمده‌اند
    («خب، امروز…»). aggressive=True: هر کلمه‌ی پرکننده هر جا باشد حذف می‌شود (برای شمارش، نه برای زیرنویس)."""
    if not text:
        return ""
    text = normalize(text)
    parts = _CHUNK_SEP.split(text)
    out = []
    skip_sep = False
    for idx, part in enumerate(parts):
        if idx % 2 == 1:  # separator
            if skip_sep and re.fullmatch(r"[،,;؛:\s]+", part):
                skip_sep = False
                continue
            skip_sep = False
            out.append(part)
            continue
        if not part.strip():
            out.append(part)
            continue
        if is_filler_only(part):
            skip_sep = True
            continue
        kept = []
        for tok in part.split(" "):
            if tok and (_sure_hesitation(tok) or (aggressive and is_filler(tok))):
                continue
            kept.append(tok)
        if aggressive:
            joined = " ".join(kept)
            for ph in _FOLD_PHR:
                pat = r"(?<!\S)" + r"\s+".join(re.escape(x) for x in ph) + r"(?!\S)"
                joined = re.sub(pat, " ", joined, flags=re.I)
            kept = joined.split(" ")
        part2 = " ".join(k for k in kept if k)
        if part.strip() and not part2.strip():
            skip_sep = True
            continue
        if part[:1] == " " and part2:
            part2 = " " + part2
        if part[-1:] == " " and part2:
            part2 += " "
        out.append(part2)
    res = "".join(out)
    res = re.sub(r"\s+([،,.;؛:!?؟…])", r"\1", res)
    res = re.sub(r"([،,;؛])(?:\s*[،,;؛])+", r"\1", res)
    res = re.sub(r"^[\s،,;؛:]+", "", res)
    res = re.sub(r"[ \t]{2,}", " ", res)
    if not tokenize(res, normalized=False):
        return ""  # only punctuation left
    return "\n".join(line.strip() for line in res.split("\n")).strip()


STOPWORDS_FA = frozenset(normalize(w) for w in """
و در به از که این آن را با برای تا یا هم اما ولی اگر پس چون نه بر بی هر همه یک یه دو چند
است هست هستش بود شد شده شود می‌شه میشه کرد کرده کردن کنه کنید کنیم کنم می‌کنه میکنه داره دارم داریم دارید
باید نباید شاید خیلی خیلیا چی چیه چه چطور چرا کجا کی کدوم اون این‌ها اینا اونا ما من تو شما او ایشون
رو روی توی تو زیر کنار بین بعد قبل الان امروز دیگه حالا خب یعنی مثلاً آره بله
خود خودم خودت خودش هیچ همین همون اینجا اونجا اینکه اونکه وقتی چیزی کسی جا کار
""".split())

STOPWORDS_EN = frozenset("the a an of for to in on and or is are was were be been with this that it as at by from "
                         "you your i my we our they them he she but so if then than there here what which who how "
                         "when where why not no yes do does did just really very like about into over out up down "
                         "can could will would should have has had get got make made go going went one two".split())
