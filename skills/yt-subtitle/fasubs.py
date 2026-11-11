# -*- coding: utf-8 -*-
"""fasubs.py - بازبینی زیرنویس فارسی (SRT / VTT / JSON ویسپر) قبل از آپلود.

  python3 -I fasubs.py subs.srt                 گزارش ایرادها (خطا / هشدار)
  python3 -I fasubs.py subs.srt --fix           فایل اصلاح‌شده‌ی subs.fixed.srt (فقط اصلاح‌های بی‌خطر)
  python3 -I fasubs.py subs.srt --fix --out final.srt
  python3 -I fasubs.py subs.srt --unsure        جدول «شنیده ← نوشته» برای تأیید سازنده
  python3 -I fasubs.py subs.srt --json          خروجی JSON

گزینه‌ها:
  --fps 25          نرخ فریم برای بررسی فاصله‌ی کمتر از ۲ فریم (پیش‌فرض ۲۵)
  --max-chars 42    بیشترین نویسه در هر خط
  --max-lines 2     بیشترین تعداد خط در هر زیرنویس
  --max-cps 17      بیشترین سرعت خواندن (نویسه در ثانیه)
  --min-dur 0.7     کوتاه‌ترین زمان نمایش (ثانیه)
  --max-dur 7       بلندترین زمان نمایش (ثانیه)
  --digits fa|ascii همراه --fix: همه‌ی رقم‌های متن (جز داخل اسم‌های لاتین مثل GPT-5) یکدست شوند
  --rlm             همراه --fix: اول خط فارسی‌ای که با کلمه‌ی لاتین یا رقم شروع می‌شود نشانه‌ی RLM بگذار
  --force           همراه --fix: فایل خروجی‌ای را که از قبل هست (شاید دستی اصلاحش کرده‌ای) بازنویسی کن

--fix هیچ کلمه‌ای را عوض نمی‌کند. فقط این‌ها را درست می‌کند: حرف عربی (ي ى ك ← ی ک)، رقم عربی (٤ ← ۴)،
نیم‌فاصله در الگوهای شناخته‌شده (می / نمی / ها / های / ترین / ‌ی و ‌ام و ‌ای بعد از «ه»)، نشانه‌ی لاتین
کنار متن فارسی (? , ; ← ؟ ، ؛) و رقم فارسی در خط زمان‌بندی (← رقم انگلیسی). مواردی که مطمئن نیست را
فقط هشدار می‌دهد. خروجی همیشه UTF-8 است (فایل Windows-1256 هم خوانده می‌شود).

خروج: ۰ = بدون خطا، ۱ = خطا پیدا شد (همراه --fix: هنوز در فایل اصلاح‌شده خطا مانده)،
۲ = ورودی یا گزینه‌ی نادرست.
"""
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fatext as fa  # noqa: E402

ZWNJ = fa.ZWNJ
RLM = "‏"

DEFAULTS = {"fps": 25.0, "max_chars": 42, "max_lines": 2, "max_cps": 17.0,
            "min_dur": 0.7, "max_dur": 7.0}

# Persian/Arabic letters (after the Arabic-letter fix only ی and ک appear, but match both)
_FA_LETTERS = "ءآأؤإئابةتثجحخدذرزسشصضطظعغفقكلمنهوىيپچژکگیۀ"
L = "[" + _FA_LETTERS + "]"
# one character of a "word" (anything but space and punctuation)
WCH = r"[^\s،,.!?؟؛;:«»\"“”()\[\]<>{}…\-–—]"

# letters that never join the next one: a suffix after them needs no ZWNJ («ویدیوها»، «دورتر»)
NON_JOINING = frozenset("اآأإدذرزژوؤة")
ARABIC_LETTERS = {"ي": "ی", "ى": "ی", "ك": "ک"}
# Arabic presentation forms (text pasted from a PDF or an old editor, e.g. «ﻻ», «ﻳ»): they look right
# on screen but search and YouTube treat them as different letters; NFKC turns them back into letters
_PRESENTATION = re.compile("[\uFB50-\uFDFF\uFE70-\uFEFE]+")


def _unpresent(seg):
    return _PRESENTATION.sub(lambda m: unicodedata.normalize("NFKC", m.group(0)), seg)


ARABIC_DIGITS = {c: "۰۱۲۳۴۵۶۷۸۹"[i] for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
LATIN_PUNCT = {"?": "؟", ",": "،", ";": "؛"}

_HA_SUFFIXES = sorted(["ها", "های", "هایی", "هایم", "هایت", "هایش", "هایمان", "هایتان", "هایشان",
                       "هام", "هات", "هاش", "هامون", "هاتون", "هاشون", "هامان", "هاتان", "هاشان"],
                      key=len, reverse=True)
# «می» after «ماه» or a number is the month May («ماه می سال گذشته»، «۱۵ می امسال»), not the verb prefix
MI_RE = re.compile(r"(?<!" + L + r")(نمی|(?<!ماه )(?<![0-9۰-۹] )می) (" + L + WCH + r"*)")
MONTH_MI_RE = re.compile(r"(?<!" + L + r")(?:(?<=ماه )|(?<=[0-9۰-۹] ))(می) (" + L + WCH + r"*)")
HA_RE = re.compile(r"(" + WCH + r"*" + L + r") (" + "|".join(_HA_SUFFIXES) + r")(?!" + L + "|" + ZWNJ + ")")
TAR_RE = re.compile(r"(" + WCH + r"*" + L + r") (ترین|تری|تر)(?!" + L + "|" + ZWNJ + ")")
AM_RE = re.compile(r"(" + WCH + r"*" + L + L + r"ه) (ام|ای|ایم|اید|اند|ی)(?!" + L + "|" + ZWNJ + ")")

# «ها»-forms that are also whole words: hash (هاش، هاش ریت)، hot (هات داگ)، Hamoun (هامون)، ham (هام)
HA_AMBIGUOUS = frozenset(["هام", "هات", "هاش", "هامون", "هامان"])
# imperatives / verbs: a «ها» after them is the emphasis «ها» («مواظب باش ها اینجا»), never a plural
HA_VERB = frozenset("باش بیا برو بکن کن نکن ببین بگو نگو بشین وایسا بخور بزن نزن بدو بیار ببر بخون".split())
_PLURAL_IMPERATIVE = re.compile("[بن]" + L + "+(?:ید|ین)")
# «ترین» after these, or before a light verb, is the loanword "train" («مدل رو ترین کردیم»)
TRAIN_BEFORE = frozenset(["رو", "را", "این", "اون", "یه"])
_LIGHT_VERB = re.compile(r" (?:ب|ن|می" + ZWNJ + "|نمی" + ZWNJ + r"|می|نمی)?"
                         r"(?:کردیم|کردن|کرده|کرد|کنیم|کنید|کنه|کنن|کن|شده|شد|شو|شه|بشه|میشه|ش|دادیم|دادن|داد|بدیم|بده|بدن)"
                         r"(?:یم|ید|ین|ن|ه|ی|م)?(?!" + L + ")")
# «ای» in «ای کاش»، «ای وای»، «ای خدا» is the vocative, not a suffix
_VOCATIVE_NEXT = re.compile(r" (?:کاش|وای|خدا|بابا|داد|دل)(?!" + L + ")")
# words whose final «ه» is spoken (not the silent «ه»): «گروه ای» is «گروهی»، not «گروه‌ای»
PRONOUNCED_HE = ("گروه", "ماه", "راه", "اشتباه", "دانشگاه", "نگاه", "کوه", "شاه", "سپاه", "پگاه", "آگاه",
                 "گناه", "تباه", "جایگاه", "پایگاه", "باشگاه", "کارگاه", "فروشگاه", "درگاه", "گاه", "سیاه", "چاه")
_AM_SUFFIXES = frozenset(["ام", "ای", "ایم", "اید", "اند", "ی"])

# adjectives/adverbs that take -تر in everyday subtitles; «تر» alone also means "wet", so only these
# (or «… تر از») are fixed for sure, the rest is a warning
TAR_SURE = frozenset("""بزرگ کوچک بیش کم بد خوب سریع راحت ساده مهم سخت آسان ارزان ارزون گران گرون قوی ضعیف
جدید قدیمی دقیق کوتاه بلند زیاد باهوش بالا پایین پیش عمیق سنگین سبک تمیز واضح جذاب آروم آرام تند دور نزدیک
بهتر جوان جوون پیر سالم امن خطرناک مفید کامل حرفه‌ای طولانی عجیب جالب ساکت شلوغ گرم سرد داغ زشت قشنگ
زیبا خوشگل شیک گنده ریز چاق لاغر پر خالی تازه کهنه محکم نرم سفت مشکل ارزشمند معروف مشهور ثروتمند فقیر""".split())
# «ها» after these is an interjection («آ ها»)
HA_SKIP = frozenset(["آ", "ا", "اه", "آه", "اوه"])

# kashida / tatweel (U+0640) inside a word, e.g. «مهـــم»: fine burned into a reel, but in an uploaded
# SRT the word no longer matches a search for «مهم». Only a warning: --fix leaves it (it can be a style)
TATWEEL = "\u0640"
_KASHIDA_WORD = re.compile(WCH + "*" + TATWEEL + WCH + "*")

TIMING_RE = re.compile(r"^\s*(\d[\d:.,٫]*)\s*-->\s*(\d[\d:.,٫]*)")
# a line meant as timing but broken («00:00:03,500 -> 00:00:05,000»، end time missing)
LOOSE_TIME_RE = re.compile(r"^\s*\d[\d:.,٫]*\s*(?:-{1,3}>|[–—]>|→)")
# markup inside a cue line: tags (<i>, <00:00:01.500>, <font color="#00FF00">), SSA overrides ({\pos(1,2)}),
# HTML entities (&rlm; &nbsp; &#8207;) - text fixes never touch them
_MARKUP = re.compile(r"<[^>]*>|\{[^}]*\}|&(?:#\d+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]*);")
_LATIN_WORD = re.compile(r"[A-Za-zÀ-ɏ][A-Za-zÀ-ɏ0-9'’.+\-]*")
_DIGIT = re.compile(r"\d")
# a number not glued to a Latin name (GPT-5, 4o), with an optional unit or scale word
_NUM_RUN = re.compile(r"(?<![A-Za-z\-.\d])[-−+]?\d+(?:[.,/٫٬،:]\d+)*"
                      r"(?:\s*(?:%|٪|درصد|هزار|میلیون|میلیارد)|[KMBk])?(?![A-Za-z\d])")
_NUM_WORDS = ("یک یه دو سه چهار پنج شش هفت هشت نه ده یازده دوازده سیزده چهارده پانزده پونزده شانزده "
              "هفده هجده نوزده بیست سی چهل پنجاه شصت هفتاد هشتاد نود صد یکصد دویست سیصد چهارصد پانصد "
              "پونصد ششصد هفتصد هشتصد نهصد نیم").split()
_SPELLED = re.compile(r"(?<!" + L + r")((?:(?:" + "|".join(sorted(_NUM_WORDS, key=len, reverse=True)) +
                      r")(?: و)? ){1,4}(?:هزار|میلیون|میلیارد|درصد)(?:" + L + r")*)")

LEVEL_FA = {"error": "خطا", "warn": "هشدار"}
CODE_FA = {
    "bad-time": "زمان‌بندی نادرست",
    "timing-digits": "رقم فارسی در زمان‌بندی",
    "empty": "زیرنویس خالی",
    "overlap": "هم‌پوشانی با زیرنویس قبلی",
    "order": "ترتیب زمانی به هم ریخته",
    "arabic-letter": "حرف عربی (ي/ى/ك یا شکل نمایشی مثل ﻻ)",
    "arabic-digit": "رقم عربی (٠-٩)",
    "zwnj": "نیم‌فاصله‌ی جاافتاده",
    "zwnj-maybe": "شاید نیم‌فاصله لازم باشد",
    "punct": "نشانه‌ی لاتین کنار متن فارسی",
    "line-long": "خط طولانی",
    "capacity": "متن بیشتر از جای زیرنویس",
    "lines": "خط زیاد",
    "cps": "سرعت خواندن بالا",
    "short": "زمان نمایش کوتاه",
    "long": "زمان نمایش بلند",
    "gap": "فاصله‌ی کمتر از ۲ فریم",
    "digit-mix": "رقم فارسی و انگلیسی با هم",
    "rtl-start": "خط فارسی که با لاتین یا رقم شروع می‌شود",
    "fix-unsafe": "اصلاح خودکار امن نبود",
    "kashida": "کشیده (ـ) در متن",
}
LEVEL_OF = {"bad-time": "error", "timing-digits": "error", "empty": "error", "overlap": "error",
            "order": "error", "arabic-letter": "error", "arabic-digit": "warn", "zwnj": "warn",
            "zwnj-maybe": "warn", "punct": "warn", "line-long": "warn", "capacity": "warn", "lines": "warn",
            "cps": "warn", "short": "warn", "long": "warn", "gap": "warn", "digit-mix": "warn",
            "rtl-start": "warn", "fix-unsafe": "warn",
            "kashida": "warn"}
FIXABLE = frozenset(["arabic-letter", "arabic-digit", "zwnj", "punct", "timing-digits"])


class UsageError(Exception):
    pass


# ---------------------------------------------------------------- small helpers

def fan(n):
    """عدد با رقم فارسی برای گزارش."""
    if isinstance(n, float) and n.is_integer():
        n = int(n)
    return fa.to_fa_digits(str(n), separators=True)


def ftime(sec):
    """زمان کوتاه برای گزارش: «۱:۰۴٫۲»."""
    if sec is None:
        return "؟"
    t = max(0.0, float(sec))
    whole = int(t)
    tenth = int(round((t - whole) * 10))
    if tenth == 10:
        whole, tenth = whole + 1, 0
    return fa.to_fa_digits(fa.fmt_timestamp(whole, "yt") + "." + str(tenth), separators=True)


def visible_len(text):
    """طول دیدنی یک خط: نیم‌فاصله، اعراب و نشانه‌های کنترل جهت شمرده نمی‌شوند."""
    return sum(1 for ch in text if ch != "\n" and unicodedata.category(ch) not in ("Mn", "Cf"))


def display_line(line):
    """متن دیدنی یک خط زیرنویس (بدون برچسب <i> و {\\an8} و نشانه‌ی جهت)، بدون یکدست‌سازی."""
    t = fa.clean_cue_text(line, normalized=False)
    return re.sub(_BIDI_MARKS, "", t).strip()


# bidi / format marks: display_line hides them and _fix_zwnj may turn one inside a word into a ZWNJ
_BIDI_MARKS = "[‎‏؜‪-‮⁦-⁩﻿]"


def skeleton(text):
    """«اسکلت» متن برای اطمینان از اینکه --fix کلمه‌ای را عوض نکرده: بدون فاصله و نیم‌فاصله و نشانه‌های
    جهت (RLM، LRM و…)، حرف و رقم و نشانه یکدست."""
    t = _unpresent(text)
    for a, b in ARABIC_LETTERS.items():
        t = t.replace(a, b)
    for a, b in LATIN_PUNCT.items():
        t = t.replace(a, b)
    t = fa.to_ascii_digits(t)
    return re.sub(r"[\s" + ZWNJ + "‎‏؜‪-‮⁦-⁩﻿]", "", t)


def _rtl_marked(raw_line):
    """خط از قبل با RLM (یا ALM یا &rlm;) شروع شده، حتی بعد از برچسبی مثل <i>."""
    t = fa.clean_cue_text(raw_line, normalized=False).lstrip()
    return t.startswith((RLM, "؜")) or raw_line.lstrip().lower().startswith(("&rlm;", RLM, "؜"))


def _text_only(line, fn):
    """fn را فقط روی متن بیرون از برچسب‌ها، {\\...} و موجودیت‌های HTML اجرا می‌کند."""
    out, pos = [], 0
    for m in _MARKUP.finditer(line):
        out.append(fn(line[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(fn(line[pos:]))
    return "".join(out)


def _markup_spans(line):
    """جای هر نویسه‌ای که داخل برچسب، {\\...} یا موجودیت HTML است."""
    spans = set()
    for m in _MARKUP.finditer(line):
        spans.update(range(m.start(), m.end()))
    return spans


def decode_text(data):
    """بایت‌های فایل را سخت‌گیرانه می‌خواند. خروجی: (متن، کدگذاری). BOM در UTF-8 نگه داشته می‌شود
    (تا --fix همان را بنویسد). UTF-16 با BOM و Windows-1256 (رایج در Subtitle Workshop و Notepad) هم
    خوانده می‌شوند؛ هر چیز دیگر ValueError با پیام فارسی."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return data.decode("utf-16"), "utf-16"
        except UnicodeDecodeError:
            pass
    else:
        try:
            return data.decode("utf-8"), "utf-8"
        except UnicodeDecodeError:
            pass
        try:
            text = data.decode("cp1256")
        except UnicodeDecodeError:
            text = None
        if text is not None and re.search("[؀-ۿ]", text):
            return text, "cp1256"
    raise ValueError("فایل UTF-8 نیست؛ آن را با UTF-8 ذخیره کن")


# ---------------------------------------------------------------- parsing

def parse_blocks(raw):
    """فایل SRT/VTT را به بلوک‌ها می‌شکند و خط‌ها را جدا نگه می‌دارد (برخلاف fa.parse_cues که خط‌ها را
    به هم می‌چسباند و زیرنویس خالی را دور می‌ریزد؛ بازبینی به هر دو نیاز دارد).
    هر بلوک: {"n", "start", "end", "tline", "traw", "lines": [متن خام], "linenos": [شماره‌ی خط در فایل از ۰]}.
    خط زمان‌بندی خراب («->» به جای «-->»، زمان پایان جاافتاده) هم بلوک باز می‌کند (با start/end = None)
    تا زیرنویسش بی‌صدا گم نشود و lint آن را خطای «زمان‌بندی نادرست» بگیرد."""
    raw = (raw or "").lstrip("﻿")
    lines = raw.splitlines()
    blocks, cur = [], None

    def timing_like(s):
        return bool(TIMING_RE.match(s) or LOOSE_TIME_RE.match(s) or "-->" in s)

    for i, line in enumerate(lines):
        m = TIMING_RE.match(line)
        if m:
            a, b = fa.parse_timestamp(m.group(1)), fa.parse_timestamp(m.group(2))
            cur = {"n": len(blocks) + 1, "start": a, "end": b, "tline": i, "traw": line,
                   "lines": [], "linenos": []}
            blocks.append(cur)
            continue
        if not line.strip():
            cur = None
            continue
        if cur is None:
            if LOOSE_TIME_RE.match(line) or "-->" in line:
                cur = {"n": len(blocks) + 1, "start": None, "end": None, "tline": i, "traw": line,
                       "lines": [], "linenos": []}
                blocks.append(cur)
            continue  # index lines, WEBVTT header, NOTE / STYLE blocks
        if line.strip().isdigit() and i + 1 < len(lines) and timing_like(lines[i + 1]):
            cur = None  # SRT index with the blank line missing
            continue
        cur["lines"].append(line)
        cur["linenos"].append(i)
    return blocks


def load_blocks(path, with_encoding=False):
    """فایل را می‌خواند. JSON (ویسپر) با fa.parse_cues خوانده می‌شود و هر cue یک خط است.
    خروجی: (بلوک‌ها، متن خام، نوع) و با with_encoding=True کدگذاری هم در انتها.
    فایلی که نه UTF-8 است نه UTF-16 نه Windows-1256: ValueError."""
    if os.path.isdir(path):
        raise OSError("پوشه است، نه فایل")
    with open(path, "rb") as fh:
        data = fh.read()
    raw, enc = decode_text(data)  # the UTF-8 BOM stays in raw so --fix can write it back
    if enc != "utf-8":
        raw = raw.lstrip("\ufeff")  # the output is UTF-8; a UTF-16 BOM is not carried over
    stripped = raw.lstrip("\ufeff").lstrip()
    if path.lower().endswith(".json") or stripped.startswith(("{", "[")):
        body = raw.lstrip("\ufeff")
        jkind = "json" if path.lower().endswith(".json") else None
        cues = fa.parse_cues(body, kind=jkind, normalized=False)
        if not cues and jkind == "json":
            cues = fa.parse_cues(body, kind=None, normalized=False)
        if cues or path.lower().endswith(".json"):
            blocks = [{"n": i + 1, "start": c.start, "end": c.end, "tline": None, "traw": None,
                       "lines": [c.text], "linenos": []} for i, c in enumerate(cues)]
            return (blocks, raw, "json", enc) if with_encoding else (blocks, raw, "json")
    kind = "vtt" if stripped.startswith("WEBVTT") else "srt"
    blocks = parse_blocks(raw)
    return (blocks, raw, kind, enc) if with_encoding else (blocks, raw, kind)


# ---------------------------------------------------------------- text checks / safe fixes

def _fix_letters(line, found):
    def conv(seg):
        seg = _unpresent(seg)
        for a, b in ARABIC_LETTERS.items():
            seg = seg.replace(a, b)
        return seg

    out = _text_only(line, conv)
    if out != line:
        words = []
        for w in re.findall(WCH + "+", _MARKUP.sub(" ", line)):
            if (any(a in w for a in ARABIC_LETTERS) or _PRESENTATION.search(w)) and w not in words:
                words.append(w)
        for w in words:
            found.append(("arabic-letter", w, conv(w)))
    return out


def _fix_arabic_digits(line, found):
    if not any(c in ARABIC_DIGITS for c in line):
        return line
    out = _text_only(line, lambda seg: "".join(ARABIC_DIGITS.get(c, c) for c in seg))
    if out != line:
        for run in sorted(set(re.findall("[٠-٩]+", _MARKUP.sub(" ", line)))):
            found.append(("arabic-digit", run, "".join(ARABIC_DIGITS[c] for c in run)))
    return out


def _join(word, suf):
    return word + suf if word[-1:] in NON_JOINING else word + ZWNJ + suf


def _fix_zwnj(line, found):
    def mi(m):
        new = m.group(1) + ZWNJ + m.group(2)
        found.append(("zwnj", m.group(0), new))
        return new

    def ha(m):
        word, suf = m.group(1), m.group(2)
        if word in HA_SKIP or re.fullmatch("[هاآ]+", word):
            return m.group(0)  # «آ ها»، laughter «ها ها»
        rest = m.string[m.end():]
        if suf == "ها" and (word in HA_VERB or _PLURAL_IMPERATIVE.fullmatch(word)
                            or not re.match(" " + L, rest)):
            # «ها» after a verb, or at the end of a sentence, may be the emphasis «ها» («مواظب باش ها!»)
            found.append(("zwnj-maybe", m.group(0), _join(word, suf)))
            return m.group(0)
        if suf in HA_AMBIGUOUS:
            # also whole words: «قدرت هاش ریت»، «یه هات داگ»، «دریاچه هامون»
            found.append(("zwnj-maybe", m.group(0), _join(word, suf)))
            return m.group(0)
        new = _join(word, suf)
        found.append(("zwnj", m.group(0), new))
        return new

    def tar(m):
        word, suf = m.group(1), m.group(2)
        rest = m.string[m.end():]
        bare = word.replace(ZWNJ, "")
        if suf == "ترین" and (bare in TRAIN_BEFORE or _LIGHT_VERB.match(rest)):
            return m.group(0)  # the loanword "train": «مدل رو ترین کردیم»، «باید مدل ترین بشه»
        sure = word in TAR_SURE or bare in TAR_SURE or (
            suf != "ترین" and re.match(r" از(?!" + L + ")", rest))
        new = _join(word, suf)
        if not sure:
            found.append(("zwnj-maybe", m.group(0), new))  # «تر» = "wet", «ترین» = "train"
            return m.group(0)
        found.append(("zwnj", m.group(0), new))
        return new

    def am(m):
        word, suf = m.group(1), m.group(2)
        rest = m.string[m.end():]
        if suf == "ای" and _VOCATIVE_NEXT.match(rest):
            return m.group(0)  # «خلاصه ای کاش …»: the vocative «ای»
        bare = word.replace(ZWNJ, "")
        if bare.endswith("اه") or bare.endswith(PRONOUNCED_HE):
            # the «ه» is spoken: «گروه ای» → «گروهی»، not «گروه‌ای»
            sugg = word + "ی" if suf in ("ای", "ی") else word + ZWNJ + suf
            found.append(("zwnj-maybe", m.group(0), sugg))
            return m.group(0)
        new = word + ZWNJ + suf
        found.append(("zwnj", m.group(0), new))
        return new

    def double(m):
        t, i, j = m.string, m.start(), m.end()
        while i > 0 and re.match(WCH, t[i - 1]):
            i -= 1
        while j < len(t) and re.match(WCH, t[j]):
            j += 1
        word = t[i:j]
        found.append(("zwnj", word, re.sub("[‎‏" + ZWNJ + "]+", ZWNJ, word)))
        return ZWNJ

    # doubled ZWNJ, or an RLM/LRM typed inside a word where a ZWNJ was meant («چی‏کار»)
    line = re.sub("(?<=" + L + ")(?:" + ZWNJ + "{2,}|[‎‏]+" + ZWNJ + "*)(?=" + L + ")", double, line)
    for m in MONTH_MI_RE.finditer(line):
        # «ماه می سال گذشته»: probably the month May; only a warning
        found.append(("zwnj-maybe", m.group(0), m.group(1) + ZWNJ + m.group(2)))
    line = MI_RE.sub(mi, line)
    line = HA_RE.sub(ha, line)
    line = TAR_RE.sub(tar, line)
    line = AM_RE.sub(am, line)
    return line


def _neighbor(text, i, step, skip=frozenset()):
    """نزدیک‌ترین نویسه‌ی واقعی کنار text[i]، با رد شدن از فاصله، RLM و برچسب / موجودیت HTML."""
    j = i + step
    while 0 <= j < len(text) and (text[j] in " \t" + RLM or j in skip):
        j += step
    return text[j] if 0 <= j < len(text) else ""


def _fix_punct(line, found):
    persian_line = fa.script_ratio(display_line(line)) >= 0.5
    markup = _markup_spans(line)  # «;» of &rlm; / &nbsp; and anything inside <…> or {…} stays
    chars = list(line)
    for i, ch in enumerate(line):
        if ch not in LATIN_PUNCT or i in markup:
            continue
        before = line[i - 1] if i > 0 else ""
        after = line[i + 1] if i + 1 < len(line) else ""
        if before.isdigit() and after.isdigit():
            continue  # 12,400 / 1;2
        prev, nxt = _neighbor(line, i, -1, markup), _neighbor(line, i, 1, markup)
        fa_near = bool(re.match(L, prev or "x")) or bool(re.match(L, nxt or "x"))
        tail = line[i + 1:]
        # a mark at the end of a Persian line («… یا Claude?») is Persian punctuation too
        at_end = persian_line and re.match(r"^[\s!?؟.…»\"”)]*$", _MARKUP.sub("", tail)) is not None
        if fa_near or at_end:
            chars[i] = LATIN_PUNCT[ch]
    out = "".join(chars)
    if out != line:
        for m in re.finditer(r"[?,;]", line):
            i = m.start()
            if chars[i] != line[i]:
                s = i
                while s > 0 and line[s - 1] in " \t":
                    s -= 1
                while s > 0 and re.match(WCH, line[s - 1]):
                    s -= 1
                found.append(("punct", line[s:i + 1].strip(), out[s:i + 1].strip()))
    return out


def _strip_latin(text):
    return _LATIN_WORD.sub(" ", text)


def _fix_digits(line, target, found):
    if target not in ("fa", "ascii"):
        return line

    def conv(seg):
        parts, pos = [], 0
        for m in _LATIN_WORD.finditer(seg):
            parts.append((seg[pos:m.start()], True))
            parts.append((m.group(0), False))
            pos = m.end()
        parts.append((seg[pos:], True))
        return "".join((fa.to_fa_digits(p) if target == "fa" else fa.to_ascii_digits(p)) if c else p
                       for p, c in parts)

    out = _text_only(line, conv)  # never inside <00:00:01.500>, #00FF00 or {\pos(100,200)}
    if out != line:
        found.append(("digits", line.strip(), out.strip()))
    return out


def _add_rlm(line, found):
    shown = display_line(line)
    if shown and fa.script_ratio(shown) >= 0.5 and re.match(r"[A-Za-z0-9]", shown) \
            and not _rtl_marked(line):
        found.append(("rlm", shown, RLM + shown))
        return RLM + line
    return line


_REPORTED_WHEN_UNSAFE = frozenset(["arabic-letter", "arabic-digit", "punct", "zwnj", "zwnj-maybe"])


def fix_line(line, digits=None, rlm=False):
    """اصلاح‌های بی‌خطر یک خط متن. خروجی: (خط جدید، فهرست (code, قبل, بعد)). موارد «شاید» با code
    zwnj-maybe در فهرست هستند ولی در خط جدید اعمال نشده‌اند. اگر «اسکلت» متن عوض شود (یعنی کلمه‌ای
    تغییر کرده باشد) خط دست نمی‌خورد، ولی ایرادهای پیداشده باز در فهرست می‌مانند و یک مورد
    («fix-unsafe»، خط، خط) هم اضافه می‌شود تا گزارش بگوید این خط را باید دستی درست کرد."""
    found = []
    out = _fix_letters(line, found)
    out = _fix_arabic_digits(out, found)
    out = _fix_zwnj(out, found)
    out = _fix_punct(out, found)
    if digits:
        out = _fix_digits(out, digits, found)
    if rlm:
        out = _add_rlm(out, found)
    if skeleton(line) != skeleton(out):
        kept = [f for f in found if f[0] in _REPORTED_WHEN_UNSAFE]
        return line, kept + [("fix-unsafe", line.strip(), line.strip())]
    return out, found


# ---------------------------------------------------------------- lint

def _issue(code, block, msg, lineno=None, fix=None):
    return {"code": code, "level": LEVEL_OF[code], "cue": block["n"] if block else None,
            "time": block["start"] if block else None,
            "line": (lineno + 1) if lineno is not None else None, "msg": msg,
            "fixable": code in FIXABLE, "fix": fix}


def _digit_kinds(text):
    t = _strip_latin(text)
    kinds = set()
    for ch in t:
        if "۰" <= ch <= "۹":
            kinds.add("fa")
        elif "0" <= ch <= "9":
            kinds.add("ascii")
        elif "٠" <= ch <= "٩":
            kinds.add("arabic")
    return kinds


def _ascii_timing(part, sep):
    """بخش زمان‌بندی یک خط («۰۰:۰۰:۰۱٫۰۰۰ --> …») با رقم انگلیسی؛ «٫» ← جداکننده‌ی قالب."""
    return fa.to_ascii_digits(part).replace("٫", sep)


def _maybe_msg(before, after):
    """متن هشدار «شاید نیم‌فاصله لازم باشد» بسته به الگو."""
    toks = before.split(" ")
    first, last = toks[0], toks[-1]
    if last == "ها":
        return ("«%s»: اگر «ها» نشانه‌ی جمع است ← «%s»؛ اگر «ها»ی تأکید است («مواظب باش ها!») "
                "درست است" % (before, after))
    if last in HA_AMBIGUOUS:
        return ("«%s»: اگر «%s» پسوند است ← «%s»؛ اگر کلمه‌ی جداست (هاش، هات داگ، هامون) درست است"
                % (before, last, after))
    if last == "ترین":
        return ("«%s»: اگر «ترین» پسوند صفت است ← «%s»؛ اگر یعنی train (ترین کردن مدل)، درست است"
                % (before, after))
    if last in ("تر", "تری"):
        return "«%s»: اگر «تر» پسوند صفت است ← «%s»؛ اگر یعنی «خیس»، درست است" % (before, after)
    if last in _AM_SUFFIXES and first.endswith("ه"):
        return ("«%s»: «ه» در «%s» خوانده می‌شود (ساکن نیست)؛ احتمالاً «%s» درست است"
                % (before, first, after))
    if first == "می":
        return ("«%s»: اگر «می» پیشوند فعل است ← «%s»؛ اگر ماه «می» (May) است، درست است"
                % (before, after))
    return "«%s»: شاید «%s» درست باشد" % (before, after)


def lint(blocks, opts=None):
    """همه‌ی بررسی‌ها. خروجی: {"cues", "duration", "issues": [...], "counts": {code: n}}."""
    o = dict(DEFAULTS)
    o.update(opts or {})
    issues = []
    prev = None
    file_digits = {"fa": 0, "ascii": 0, "arabic": 0}
    for b in blocks:
        lno = b["linenos"][0] if b["linenos"] else b["tline"]
        tm = TIMING_RE.match(b.get("traw") or "")
        if tm and re.search(r"[^\x00-\x7f]", tm.group(0)):
            fixed_t = _ascii_timing(tm.group(0), "." if "." in tm.group(0) else ",")
            issues.append(_issue("timing-digits", b, "«%s»: زمان‌ها باید با رقم انگلیسی باشند؛ یوتیوب و بیشتر "
                                 "پخش‌کننده‌ها رقم فارسی را در زمان‌بندی نمی‌خوانند" % tm.group(0).strip(),
                                 b["tline"], fixed_t.strip()))
        if b["start"] is None or b["end"] is None or b["end"] < b["start"]:
            issues.append(_issue("bad-time", b, "زمان شروع یا پایان خوانده نمی‌شود یا پایان قبل از شروع است",
                                 b["tline"]))
            continue
        shown = [display_line(x) for x in b["lines"]]
        shown = [x for x in shown if x]
        dur = b["end"] - b["start"]
        if not shown:
            issues.append(_issue("empty", b, "متنی ندارد؛ پاکش کن یا متن بگذار", b["tline"]))
        # timing against the previous cue
        if prev is not None:
            if b["start"] < prev["start"]:
                issues.append(_issue("order", b, "زودتر از زیرنویس قبلی (#%s) شروع می‌شود" % fan(prev["n"]),
                                     b["tline"]))
            elif b["start"] < prev["end"] - 0.0005:
                issues.append(_issue("overlap", b, "%s ثانیه با زیرنویس #%s هم‌پوشانی دارد"
                                     % (fan(round(prev["end"] - b["start"], 2)), fan(prev["n"])), b["tline"]))
            else:
                gap = b["start"] - prev["end"]
                if 0.0005 < gap < 2.0 / o["fps"] - 0.0005:
                    issues.append(_issue("gap", b, "فاصله با زیرنویس قبلی %s ثانیه است؛ یا بچسبانش (۰) یا "
                                         "دست‌کم ۲ فریم (%s ثانیه) فاصله بده"
                                         % (fan(round(gap, 3)), fan(round(2.0 / o["fps"], 2))), b["tline"]))
        if prev is None or b["end"] > prev["end"]:
            prev = b
        if shown:
            if dur < o["min_dur"]:
                issues.append(_issue("short", b, "فقط %s ثانیه دیده می‌شود (کمتر از %s)"
                                     % (fan(round(dur, 2)), fan(o["min_dur"])), b["tline"]))
            elif dur > o["max_dur"]:
                issues.append(_issue("long", b, "%s ثانیه روی صفحه می‌ماند (بیشتر از %s)؛ بشکنش"
                                     % (fan(round(dur, 1)), fan(o["max_dur"])), b["tline"]))
            chars = sum(visible_len(x) for x in shown)
            if dur > 0 and chars / dur > o["max_cps"] + 1e-9:
                issues.append(_issue("cps", b, "%s نویسه در ثانیه (حداکثر %s)؛ متن را کوتاه کن یا زمان را بیشتر"
                                     % (fan(round(chars / dur, 1)), fan(o["max_cps"])), lno))
            if len(shown) > o["max_lines"]:
                issues.append(_issue("lines", b, "%s خط دارد (حداکثر %s)" % (fan(len(shown)), fan(o["max_lines"])),
                                     lno))
        for raw_line, ln in zip(b["lines"], b["linenos"] or [None] * len(b["lines"])):
            text = display_line(raw_line)
            if not text:
                continue
            n = visible_len(text)
            if b["tline"] is None:
                # JSON (Whisper) has no line breaks: only check that the segment fits in max_lines lines
                cap = o["max_chars"] * o["max_lines"]
                if n > cap:
                    issues.append(_issue("capacity", b, "%s نویسه؛ در %s خط %s نویسه‌ای جا نمی‌شود: «%s»"
                                         % (fan(n), fan(o["max_lines"]), fan(o["max_chars"]), text), lno))
            elif n > o["max_chars"]:
                issues.append(_issue("line-long", b, "%s نویسه (حداکثر %s): «%s»" % (fan(n), fan(o["max_chars"]), text),
                                     ln if ln is not None else lno))
            _, found = fix_line(raw_line)
            unsafe = any(f[0] == "fix-unsafe" for f in found)
            where_ln = ln if ln is not None else lno
            for code, before, after in found:
                if code == "zwnj-maybe":
                    issues.append(_issue(code, b, _maybe_msg(before, after), where_ln, after))
                elif code == "fix-unsafe":
                    issues.append(_issue(code, b, "«%s»: اصلاح خودکار این خط امن نبود و --fix از آن رد می‌شود؛ "
                                         "ایرادهای بالا را دستی درست کن" % before, where_ln))
                elif code in CODE_FA:
                    it = _issue(code, b, "«%s» ← «%s»" % (before, after), where_ln, after)
                    if unsafe:
                        it["fixable"] = False
                    issues.append(it)
            if TATWEEL in text:
                words = []
                for w in _KASHIDA_WORD.findall(text):
                    if w not in words:
                        words.append(w)
                issues.append(_issue("kashida", b, "%s: در فایلی که آپلود می‌شود جست‌وجوی زیرنویس را خراب "
                                     "می‌کند (با جست‌وجوی «%s» پیدا نمی‌شود)؛ اگر سبک عمدیِ زیرنویس سوزانده "
                                     "روی ویدیو نیست، دستی پاکش کن (--fix به آن دست نمی‌زند)"
                                     % ("، ".join("«%s»" % w for w in words), words[0].replace(TATWEEL, "")),
                                     where_ln))
            if fa.script_ratio(text) >= 0.5 and re.match(r"[A-Za-z0-9]", text) and not _rtl_marked(raw_line):
                issues.append(_issue("rtl-start", b, "«%s»: در بعضی پخش‌کننده‌ها نشانه‌ها سمت اشتباه می‌افتند؛ "
                                     "خط را با کلمه‌ی فارسی شروع کن یا --fix --rlm" % text,
                                     ln if ln is not None else lno))
        kinds = _digit_kinds(" ".join(shown))
        for k in kinds:
            file_digits[k] += 1
        if "fa" in kinds and "ascii" in kinds:
            issues.append(_issue("digit-mix", b, "در یک زیرنویس هم رقم فارسی هست هم انگلیسی: «%s»" % " / ".join(shown),
                                 lno))
    if file_digits["fa"] and file_digits["ascii"]:
        issues.append({"code": "digit-mix", "level": "warn", "cue": None, "time": None, "line": None,
                       "msg": "در کل فایل %s زیرنویس رقم فارسی و %s زیرنویس رقم انگلیسی دارند؛ یکی را انتخاب کن "
                              "(--fix --digits fa یا ascii)" % (fan(file_digits["fa"]), fan(file_digits["ascii"])),
                       "fixable": False, "fix": None})
    counts = {}
    for it in issues:
        counts[it["code"]] = counts.get(it["code"], 0) + 1
    dur = max([b["end"] for b in blocks if b["end"] is not None] or [0.0])
    return {"cues": len(blocks), "duration": dur, "issues": issues, "counts": counts}


# ---------------------------------------------------------------- --fix

def apply_fixes(raw, blocks, digits=None, rlm=False, kind="srt"):
    """متن کامل فایل را با اصلاح‌های بی‌خطر برمی‌گرداند. خط‌های متن زیرنویس اصلاح می‌شوند و در خط
    زمان‌بندی فقط رقم فارسی ← انگلیسی (جداکننده‌ی «٫» ← «,» در SRT و «.» در VTT)؛ شماره‌ها، سربرگ
    WEBVTT، تنظیم‌های cue و پایان خط‌ها (CRLF) همان می‌مانند.
    خروجی: (متن جدید، فهرست تغییرها [(شماره‌ی خط، code، قبل، بعد)]). خطی که اصلاحش امن نبود با code
    «skipped» در فهرست می‌آید و دست نمی‌خورد."""
    bom = raw.startswith("﻿")
    body = raw[1:] if bom else raw
    lines = body.splitlines(True)
    changes = []
    textlines = set()
    sep = "." if kind == "vtt" else ","
    for b in blocks:
        textlines.update(b["linenos"])
        ti = b.get("tline")
        if ti is None or ti >= len(lines):
            continue
        tline = lines[ti]
        content = tline.rstrip("\r\n")
        m = TIMING_RE.match(content)
        if m and re.search(r"[^\x00-\x7f]", m.group(0)):
            new_part = _ascii_timing(m.group(0), sep)
            lines[ti] = new_part + tline[m.end():]
            changes.append((ti + 1, "timing-digits", m.group(0).strip(), new_part.strip()))
    for i in sorted(textlines):
        if i >= len(lines):
            continue
        line = lines[i]
        content = line.rstrip("\r\n")
        ending = line[len(content):]
        new, found = fix_line(content, digits=digits, rlm=rlm)
        if any(f[0] == "fix-unsafe" for f in found):
            changes.append((i + 1, "skipped", content.strip(), content.strip()))
            continue
        if new != content:
            lines[i] = new + ending
            for code, before, after in found:
                if code != "zwnj-maybe":
                    changes.append((i + 1, code, before, after))
    changes.sort(key=lambda c: c[0])
    return ("﻿" if bom else "") + "".join(lines), changes


def default_out(path):
    stem, ext = os.path.splitext(path)
    return stem + ".fixed" + (ext or ".srt")


# ---------------------------------------------------------------- --unsure

def unsure_items(blocks):
    """کلمه‌های لاتین و عددها برای فهرست «شنیده ← نوشته»، به ترتیب اولین بار.
    هر مورد: {"kind": "latin"|"number", "written", "first", "count", "cue"}."""
    items, order = {}, []

    def add(kind, written, b):
        written = written.strip(" ،,.؛;:")
        if not written:
            return
        key = (kind, fa.fold(written))
        if key not in items:
            items[key] = {"kind": kind, "written": written, "forms": [written], "first": b["start"],
                          "cue": b["n"], "count": 0}
            order.append(key)
        it = items[key]
        it["count"] += 1
        if written not in it["forms"]:
            it["forms"].append(written)

    for b in blocks:
        text = " ".join(display_line(x) for x in b["lines"])
        for p in fa.latin_tokens(text, phrases=True):
            if not re.fullmatch(r"[\d.,]+[KMBk]?", p):
                add("latin", p, b)
        for m in _NUM_RUN.finditer(text):
            add("number", m.group(0), b)
        for m in _SPELLED.finditer(fa.normalize(_strip_latin(text))):
            add("number", m.group(1), b)
    return [items[k] for k in order]


def spelling_choices(blocks):
    """کلمه‌هایی که در فایل به بیش از یک شکل نوشته شده‌اند («می‌خوام» / «میخوام»، «ChatGPT» / «Chatgpt»)."""
    forms, order = {}, []
    for b in blocks:
        for x in b["lines"]:
            for tok in fa.tokenize(display_line(x), normalized=True):
                key = fa.fold(tok)
                if len(key) < 2 or key.isdigit():
                    continue
                if key not in forms:
                    forms[key] = []
                    order.append(key)
                if tok not in forms[key]:
                    forms[key].append(tok)
    return [forms[k] for k in order if len(forms[k]) > 1]


def render_unsure(name, blocks):
    items = unsure_items(blocks)
    out = ["فهرست «شنیده ← نوشته»: %s" % name, "",
           "ستون «شنیده» را از روی صدا پر کن (همان چیزی که گوینده واقعاً گفت)، بعد کل فهرست را برای سازنده "
           "بفرست و تا «اوکی» نگرفتی زیرنویس را نهایی نکن.", ""]
    if items:
        out.append("| # | زمان | شنیده | نوشته | نوع | تکرار | تأیید |")
        out.append("|---|---|---|---|---|---|---|")
        for i, it in enumerate(items, 1):
            written = " / ".join(it["forms"])
            kind = "اسم یا اصطلاح لاتین" if it["kind"] == "latin" else "عدد"
            out.append("| %s | %s | … | %s | %s | %s | ☐ |" % (fan(i), ftime(it["first"]), written, kind,
                                                            fan(it["count"])))
    else:
        out.append("کلمه‌ی لاتین یا عددی پیدا نشد.")
    out += ["", "اسم آدم‌ها، شرکت‌ها و اصطلاح‌هایی که با حروف فارسی نوشته شده‌اند (مثل «جنسن هوانگ» یا "
                "«آرتیفکت») را ابزار نمی‌شناسد؛ آن‌ها را خودت به همین جدول اضافه کن."]
    choices = spelling_choices(blocks)
    if choices:
        out += ["", "انتخاب املا (یک کلمه به چند شکل نوشته شده؛ یکی را انتخاب کن):"]
        for forms in choices:
            out.append("  • " + " / ".join("«%s»" % f for f in forms))
    return "\n".join(out)


# ---------------------------------------------------------------- report

def render_report(name, result, kind):
    issues = result["issues"]
    errors = [i for i in issues if i["level"] == "error"]
    warns = [i for i in issues if i["level"] == "warn"]
    fixable = sum(1 for i in issues if i["fixable"]) if kind != "json" else 0
    out = ["بازبینی زیرنویس: %s" % name,
           "%s زیرنویس · مدت %s · %s خطا · %s هشدار · %s مورد با --fix درست می‌شود"
           % (fan(result["cues"]), ftime(result["duration"]), fan(len(errors)), fan(len(warns)), fan(fixable))]
    if kind == "json":
        out.append("(ورودی JSON است: شکستن خط‌ها معلوم نیست و --fix فقط روی SRT/VTT کار می‌کند.)")
    if not issues:
        out += ["", "ایرادی پیدا نشد."]

    def where(i):
        bits = []
        if i["cue"] is not None:
            bits.append("#" + fan(i["cue"]))
        if i["time"] is not None:
            bits.append(ftime(i["time"]))
        if i["line"] is not None:
            bits.append("خط " + fan(i["line"]))
        return " ".join(bits)

    for title, group in (("خطاها", errors), ("هشدارها", warns)):
        if not group:
            continue
        out += ["", title + ":"]
        for i in group:
            tag = " [--fix]" if i["fixable"] and kind != "json" else ""
            loc = where(i)
            out.append("  %s%s: %s%s" % (loc + " · " if loc else "", CODE_FA[i["code"]], i["msg"], tag))
    if issues:
        out += ["", "خلاصه:"]
        for code in CODE_FA:
            if code in result["counts"]:
                out.append("  %s: %s" % (CODE_FA[code], fan(result["counts"][code])))
    out += ["", "قبل از آپلود: python3 -I fasubs.py <فایل> --unsure و تأیید فهرست «شنیده ← نوشته» توسط سازنده."]
    return "\n".join(out)


def render_changes(name, out_name, changes, remaining):
    applied = [c for c in changes if c[1] != "skipped"]
    skipped = [c for c in changes if c[1] == "skipped"]
    out = ["اصلاح بی‌خطر روی %s؛ فایل اصلاح‌شده: %s" % (name, out_name),
           "%s تغییر (هیچ کلمه‌ای عوض نشده):" % fan(len(applied))]
    labels = {"digits": "یکدست کردن رقم", "rlm": "نشانه‌ی RLM اول خط"}
    for lno, code, before, after in applied:
        label = labels.get(code, CODE_FA.get(code, code))
        out.append("  خط %s · %s: «%s» ← «%s»" % (fan(lno), label, before, after))
    if not applied:
        out.append("  چیزی برای اصلاح خودکار نبود.")
    if skipped:
        out += ["", "%s خط دست نخورد چون اصلاح خودکارش امن نبود؛ دستی درستش کن:" % fan(len(skipped))]
        for lno, _, before, _ in skipped:
            out.append("  خط %s: «%s»" % (fan(lno), before))
    errors = sum(1 for i in remaining["issues"] if i["level"] == "error")
    warns = sum(1 for i in remaining["issues"] if i["level"] == "warn")
    out += ["", "%s خطا و %s هشدار مانده که باید دستی دیده شود (python3 -I fasubs.py %s)."
            % (fan(errors), fan(warns), out_name)]
    return "\n".join(out)


# ---------------------------------------------------------------- CLI

_NUM_OPTS = {"--fps": "fps", "--max-chars": "max_chars", "--max-lines": "max_lines", "--max-cps": "max_cps",
             "--min-dur": "min_dur", "--max-dur": "max_dur"}


def parse_args(argv):
    a = {"file": None, "fix": False, "out": None, "unsure": False, "json": False, "digits": None,
         "rlm": False, "force": False, "opts": {}}
    i = 0
    while i < len(argv):
        arg = argv[i]
        val = None
        if arg.startswith("--") and "=" in arg:
            arg, val = arg.split("=", 1)
        if arg in ("-h", "--help"):
            raise SystemExit(0)
        if arg in ("--fix", "--unsure", "--json", "--rlm", "--force"):
            a[arg[2:]] = True
        elif arg in _NUM_OPTS or arg in ("--out", "--digits"):
            if val is None:
                if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                    raise UsageError("گزینه‌ی %s مقدار می‌خواهد" % arg)
                i += 1
                val = argv[i]
            if arg == "--out":
                a["out"] = val
            elif arg == "--digits":
                if val not in ("fa", "ascii"):
                    raise UsageError("--digits فقط fa یا ascii")
                a["digits"] = val
            else:
                n = fa.parse_number(val)
                if n is None or n <= 0:
                    raise UsageError("مقدار %s باید عدد مثبت باشد: %s" % (arg, val))
                a["opts"][_NUM_OPTS[arg]] = int(n) if arg in ("--max-chars", "--max-lines") else n
        elif arg.startswith("--"):
            raise UsageError("گزینه‌ی ناشناخته: %s" % arg)
        elif a["file"] is None:
            a["file"] = arg
        else:
            raise UsageError("فقط یک فایل بده")
        i += 1
    if a["file"] is None:
        raise UsageError("فایل زیرنویس را بده (SRT، VTT یا JSON ویسپر)")
    if (a["digits"] or a["rlm"] or a["out"] or a["force"]) and not a["fix"]:
        raise UsageError("--digits، --rlm، --out و --force فقط همراه --fix معنی دارند")
    return a


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        a = parse_args(argv)
    except SystemExit:
        print(__doc__)
        return 0
    except UsageError as e:
        print("fasubs.py: %s\n" % e, file=sys.stderr)
        print(__doc__, file=sys.stderr)
        return 2
    path = a["file"]
    name = os.path.basename(path)
    try:
        blocks, raw, kind, enc = load_blocks(path, with_encoding=True)
    except OSError as e:
        reason = "پیدا نشد" if isinstance(e, FileNotFoundError) else (e.strerror or str(e))
        print("fasubs.py: فایل خوانده نشد (%s): %s" % (reason, name), file=sys.stderr)
        return 2
    except ValueError as e:
        print("fasubs.py: %s: %s" % (name, e), file=sys.stderr)
        return 2
    if enc != "utf-8":
        print("fasubs.py: فایل با %s خوانده شد؛ خروجی --fix به UTF-8 است." % enc, file=sys.stderr)
    if not blocks:
        print("fasubs.py: هیچ زیرنویسی در %s پیدا نشد (SRT، VTT یا JSON ویسپر؟)" % name, file=sys.stderr)
        return 2

    if a["fix"]:
        if kind == "json":
            print("fasubs.py: --fix فقط روی SRT/VTT کار می‌کند؛ اول از JSON یک SRT بساز.", file=sys.stderr)
            return 2
        out_path = a["out"] or default_out(path)
        if os.path.abspath(out_path) == os.path.abspath(path):
            print("fasubs.py: فایل اصلی بازنویسی نمی‌شود؛ با --out یک اسم دیگر بده.", file=sys.stderr)
            return 2
        new_raw, changes = apply_fixes(raw, blocks, digits=a["digits"], rlm=a["rlm"], kind=kind)
        if new_raw.count("\ufffd") > raw.count("\ufffd"):
            # last guard: never write a file whose letters were replaced by «�»
            print("fasubs.py: خروجی نویسه‌ی خراب (�) دارد که در فایل اصلی نبود؛ چیزی نوشته نشد.", file=sys.stderr)
            return 2
        new_bytes = new_raw.encode("utf-8")
        if os.path.exists(out_path) and not a["force"]:
            try:
                with open(out_path, "rb") as fh:
                    same = fh.read() == new_bytes
            except OSError:
                same = False
            if not same:
                print("fasubs.py: %s از قبل هست (شاید دستی اصلاحش کرده‌ای)؛ با --force بازنویسی کن یا "
                      "--out اسم دیگری بده." % os.path.basename(out_path), file=sys.stderr)
                return 2
        try:
            with open(out_path, "wb") as fh:
                fh.write(new_bytes)
        except OSError as e:
            print("fasubs.py: نوشتن فایل نشد: %s" % (e.strerror or e), file=sys.stderr)
            return 2
        remaining = lint(parse_blocks(new_raw), a["opts"])
        n_err = sum(1 for i in remaining["issues"] if i["level"] == "error")
        n_warn = sum(1 for i in remaining["issues"] if i["level"] == "warn")
        if a["json"]:
            print(json.dumps({"out": os.path.basename(out_path), "encoding": enc,
                              "changes": [{"line": l, "code": c, "before": b, "after": t}
                                          for l, c, b, t in changes],
                              "errors": n_err, "warnings": n_warn,
                              "remaining": remaining}, ensure_ascii=False, indent=2))
        else:
            print(render_changes(name, os.path.basename(out_path), changes, remaining))
        return 1 if n_err else 0

    if a["unsure"]:
        if a["json"]:
            print(json.dumps({"items": unsure_items(blocks), "spelling_choices": spelling_choices(blocks)},
                             ensure_ascii=False, indent=2))
        else:
            print(render_unsure(name, blocks))
        return 0

    result = lint(blocks, a["opts"])
    if a["json"]:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_report(name, result, kind))
    return 1 if any(i["level"] == "error" for i in result["issues"]) else 0


if __name__ == "__main__":
    sys.exit(main())
