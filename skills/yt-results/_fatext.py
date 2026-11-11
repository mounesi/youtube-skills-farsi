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
import re
import unicodedata
from collections import namedtuple

__version__ = "1.0.0"

__all__ = [
    "normalize", "fold", "to_ascii_digits", "to_fa_digits", "parse_number",
    "tokenize", "word_count", "norm_words", "script_counts", "script_ratio", "is_persian",
    "latin_tokens", "parse_timestamp", "fmt_timestamp", "Cue", "clean_cue_text", "parse_cues",
    "load_cues", "duration", "is_filler", "is_filler_only", "strip_fillers",
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
_NUM = re.compile(r"(?P<sign>(?<![\w.,])[-−+])?(?P<num>\d+(?:[.,/'٫٬،]\d+)*)")

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


def _words_number(words):
    """Persian spelled-out number from a token list: ['یک', 'و', 'نیم', 'میلیون'] -> 1.5e6."""
    total, cur, used, half = 0.0, 0.0, False, False
    for w in words:
        if w == "و":
            continue
        if w in ("نیم", "نیمه"):
            half = True
            used = True
            continue
        if w in _FA_WORD_NUM:
            cur += _FA_WORD_NUM[w]
            used = True
        elif w in _FA_WORD_SCALE:
            base = (cur or 1) + (0.5 if half else 0)
            total += base * _FA_WORD_SCALE[w]
            cur, half, used = 0.0, False, True
        else:
            break
    if not used:
        return None
    return total + cur + (0.5 if half else 0)


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


def parse_number(s):
    """اولین عدد یک متن را برمی‌گرداند (float) یا None اگر عددی نبود. هیچ عددی حدس زده نمی‌شود.

    می‌فهمد: «۱٫۲ هزار»، «1.2K»، «۳ میلیون»، «12,400»، «۱۲٬۴۰۰»، «4.5M views»، «۱۲ هزار بازدید»، «1.2B»،
    «۱/۵ میلیون» (اسلش به‌جای ممیز)، «45%»، «−۳»، و عدد حروفی ساده: «یک و نیم میلیون»، «سیصد هزار»، «هزار».
    """
    if s is None:
        return None
    if isinstance(s, (int, float)) and not isinstance(s, bool):
        return float(s)
    t = normalize(str(s), digits="ascii")
    t = t.replace(ZWNJ, " ")
    m = _NUM.search(t)
    if not m:
        return _spelled_number(t)
    val = _num_core(m.group("num"))
    if val is None:
        return None
    rest = t[m.end():].lstrip().lower()
    for word, mult in _MULT:
        if rest.startswith(word):
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
        return float(s) if s >= 0 else None
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
    seconds = max(0.0, float(seconds or 0))
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

# Markup inside cue text: HTML-ish tags (<i>, <c>, <00:00:01.000>) and SSA override blocks ({\an8}).
_TAGS = re.compile(r"<[^>]*>|\{[^}]*\}")
_TIMING = re.compile(r"^\s*(\d[\d:.,٫]*)\s*-->\s*(\d[\d:.,٫]*)")
# Rolling-caption snapshot cues (YouTube auto VTT) are ~10 ms long and only repeat the line above.
_MIN_VTT_CUE = 0.05


def clean_cue_text(text, normalized=True):
    """متن یک خط زیرنویس را تمیز می‌کند: برچسب‌ها (<i>، <c>، <00:00:01.000>، {\\an8}) و &nbsp; و… حذف
    و (پیش‌فرض) با normalize یکدست می‌شود."""
    text = html.unescape(_TAGS.sub("", text or ""))
    return normalize(text) if normalized else text.strip()


def _num(v):
    if isinstance(v, bool) or v is None:
        raise ValueError("no time")
    if isinstance(v, (int, float)):
        return float(v)
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
        t = clean_cue_text(str(_word_text(w)), normalized)
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
        t = clean_cue_text(str(text or ""), normalized)
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
        except ValueError:
            if kind == "json":
                return []
            # not JSON after all - try it as srt / vtt
    is_vtt = kind == "vtt" or (kind is None and raw.lstrip().startswith("WEBVTT"))
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
            while t and last is not None and t[0] == last:
                t = t[1:]
            if t:
                kept.append((a, b, t))
                last = t[-1]
        cues = kept
    out = [Cue(a, b, " ".join(t)) for a, b, t in cues if t]
    return sorted(out, key=lambda c: (c.start, c.end))


def load_cues(path, words=False, normalized=True):
    """فایل SRT، VTT (همراه با زیرنویس خودکار یوتیوب، NOTE و شناسه‌ی cue) یا JSON ویسپر (dict با
    segments، فهرست ساده، سطح کلمه، whisper.cpp، chunks) را می‌خواند و فهرست مرتب Cue(start, end, text)
    برمی‌گرداند. BOM مشکلی ندارد؛ cue خالی حذف می‌شود و عدد تنها متن حساب می‌شود.
    خطای نبودن فایل یا پوشه بودن مسیر (OSError) را خود ابزار باید بگیرد."""
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        raw = fh.read()
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
