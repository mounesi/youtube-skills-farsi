#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""keyword.py - شکل‌های مختلفی که بیننده‌ها یک «کلمه‌ی کامنت» را تایپ می‌کنند.

وقتی آخر ریلز می‌گویی «کامنت کن «آرتیفکت» تا آموزشش رو برات بفرستم»، همه همان را تایپ نمی‌کنند:
یکی «ارتیفکت» می‌نویسد، یکی «ارتیفکیت»، یکی «اردیفکت»، یکی با کیبورد عربی «آرتيفكت»، یکی
فینگلیش «artifact». اگر اتوماسیون کامنت ← دایرکت فقط شکل دقیق را بشناسد، این آدم‌ها جواب
نمی‌گیرند. این ابزار شکل‌های محتمل را می‌سازد، تکراری‌ها را حذف می‌کند و به ترتیب احتمال
(تخمینی، نه آمار) مرتب می‌کند؛ یک regex هم می‌دهد که همه‌شان را بگیرد.

    python3 -I keyword.py "آرتیفکت"                 # فهرست مرتب، ۳۰ تای اول
    python3 -I keyword.py "آرتیفکت" --max 60
    python3 -I keyword.py "آرتیفکت" --also artifact  # شکل انگلیسی/فینگلیش را هم اضافه کن
    python3 -I keyword.py "آرتیفکت" --regex         # فقط یک regex که همه را می‌گیرد
    python3 -I keyword.py "آرتیفکت" --regex --exact # regex برای «کل کامنت همین کلمه است»
    python3 -I keyword.py "آرتیفکت" --test "ارتیفکیت لطفا" --test "مرسی"
    python3 -I keyword.py "دهه ۶۰" --json

regex در پایتون و جاوااسکریپت (ES2018 به بعد) و PCRE یکسان کار می‌کند و فقط فلگ i می‌خواهد.
--test کامنت را بدون هیچ یکدست‌سازی، درست مثل اتوماسیون، با همان regex چاپ‌شده امتحان می‌کند.

امتیازها حدس‌اند (قاعده‌ی سرانگشتی از غلط‌های رایج تایپی و شنیداری فارسی)، نه شمارش واقعی کامنت‌ها.
فقط کتابخانه‌ی استاندارد پایتون ۳.۹.
"""
import argparse
import json
import os
import re
import sys

# append, not insert(0): this file is named keyword.py and must not shadow the stdlib module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import _fatext as fa  # noqa: E402

ZWNJ = fa.ZWNJ
VOWELS = set("اآوی")
AA = "\uE000"  # stands in for آ inside finglish (fold() turns آ into ا, but آوا is ava, not ova)
ALEFS = "آا"
FA_LETTERS = set("ابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهیآئء")

# homophone groups (same sound, different letter) - the most common Persian misspellings
HOMOPHONES = [("سصث", 0.2), ("زذضظ", 0.2), ("تط", 0.15), ("هح", 0.15), ("قغ", 0.3)]
# sound-alike swaps people make when they only HEARD the word (voiced/unvoiced pairs)
HEARD = {"ت": ("د", 0.25), "د": ("ت", 0.25), "پ": ("ب", 0.15), "ب": ("پ", 0.15),
         "ک": ("گ", 0.15), "گ": ("ک", 0.15)}
# letters an Arabic keyboard does not have
ARABIC_KB = {"پ": "ب", "چ": "ج", "گ": "ک", "ژ": "ز"}

# common loanwords: the English spelling people type in Latin letters
LOANWORDS = {
    "ارتیفکت": "artifact", "ارتیفکتها": "artifacts", "کلاد": "claude", "کلود": "claude",
    "جمینای": "gemini", "جمنای": "gemini", "جمینی": "gemini", "چتجیپیتی": "chatgpt",
    "پرامپت": "prompt", "پرامپتنویسی": "prompt", "ایجنت": "agent", "کدکس": "codex",
    "کرسر": "cursor", "سورا": "sora", "میدجرنی": "midjourney", "نوتبوک": "notebook",
    "پایتون": "python", "ورکفلو": "workflow", "اتومیشن": "automation", "اتوماسیون": "automation",
    "تمپلیت": "template", "قالب": "template", "اسکیل": "skill", "امسیپی": "mcp", "انایتان": "n8n",
    "نوشن": "notion", "اکسل": "excel", "کپکات": "capcut", "یوتیوب": "youtube", "گوگل": "google",
    "اینستاگرام": "instagram", "ریلز": "reels", "دیپسیک": "deepseek", "گراک": "grok",
    "پرپلکسیتی": "perplexity", "هوشمصنوعی": "ai",
}

# finglish: Persian letter -> Latin options (first = most common)
FINGLISH = {
    "ب": ["b"], "پ": ["p"], "ت": ["t"], "ث": ["s"], "ج": ["j"], "چ": ["ch"], "ح": ["h"],
    "خ": ["kh", "x"], "د": ["d"], "ذ": ["z"], "ر": ["r"], "ز": ["z"], "ژ": ["zh"], "س": ["s"],
    "ش": ["sh"], "ص": ["s"], "ض": ["z"], "ط": ["t"], "ظ": ["z"], "ع": ["", "a"], "غ": ["gh"],
    "ف": ["f"], "ق": ["gh", "q"], "ک": ["k", "c"], "گ": ["g"], "ل": ["l"], "م": ["m"],
    "ن": ["n"], "ئ": ["e"], "ء": [""],
}
# two consonants an English word can start with (prompt, claude, skill...): only these keep the
# bare cluster as the top finglish guess; every other cluster takes a short vowel (شروع = shoro)
ONSETS = {"pr", "pl", "br", "bl", "tr", "dr", "kr", "kl", "gr", "gl", "fr", "fl", "sk", "sp",
          "st", "sm", "sn", "sl", "sw"}

LABEL = {
    "orig": "شکل اصلی",
    "madda": "آ ← ا",
    "to_madda": "ا ← آ",
    "ar_ye": "ی عربی (ي)",
    "ar_kaf": "ک عربی (ك)",
    "ar_kb": "کیبورد عربی (بدون پ/چ/ژ/گ)",
    "zwnj_space": "نیم‌فاصله ← فاصله",
    "zwnj_none": "نیم‌فاصله ← چسبیده",
    "space_zwnj": "فاصله ← نیم‌فاصله",
    "space_none": "فاصله ← چسبیده",
    "drop_vowel": "حذف حرف صدادار",
    "add_vowel": "اضافه شدن حرف صدادار",
    "double_vowel": "کشیدن حرف صدادار",
    "swap_vowel": "جابه‌جایی ا و و",
    "drop_cons": "جاافتادن حرف بی‌صدا",
    "homophone": "حرف هم‌صدا",
    "heard": "اشتباه شنیداری",
    "repeat_last": "تکرار حرف آخر",
    "ascii_digits": "رقم انگلیسی",
    "fa_digits": "رقم فارسی",
    "ar_digits": "رقم عربی",
    "num_words": "عدد با حروف",
    "quotes": "داخل گیومه",
    "also": "شکلی که خودت دادی",
    "loanword": "املای انگلیسی",
    "finglish": "فینگلیش",
    "latin_case": "حروف کوچک",
    "latin_ck": "c ↔ k",
    "latin_vowel": "جابه‌جایی حرف صدادار لاتین",
    "latin_double": "حرف دوتایی لاتین",
    "latin_space": "فاصله/خط تیره‌ی لاتین",
    "latin_drop": "جاافتادن حرف لاتین",
    "latin_plural": "جمع انگلیسی (s)",
}


# nobody inserts a vowel letter next to these (دهه never becomes دیهه)
GUTTURAL = set("هحعءئ")
# edits that end a chain (a second edit on top of them only adds noise)
TERMINAL = {"repeat_last", "double_vowel", "quotes", "ar_digits", "latin_plural", "drop_cons"}


def _is_cons(ch):
    return ch in FA_LETTERS and ch not in VOWELS


def _is_fa(s):
    return fa.script_counts(s)["fa"] > 0


# ------------------------------------------------------------ Persian edits
# each op yields (new_text, weight, label_key)

def _ops_fa(s):
    n = len(s)
    for i, ch in enumerate(s):
        if ch == "آ":
            yield s[:i] + "ا" + s[i + 1:], (0.9 if i == 0 else 0.7), "madda"
        if ch == "ا" and i == 0 and n > 1 and _is_cons(s[1]):
            yield "آ" + s[1:], 0.25, "to_madda"
        if ch == ZWNJ:
            yield s[:i] + " " + s[i + 1:], 0.7, "zwnj_space"
            yield s[:i] + s[i + 1:], 0.6, "zwnj_none"
        if ch == " ":
            yield s[:i] + ZWNJ + s[i + 1:], 0.35, "space_zwnj"
            yield s[:i] + s[i + 1:], 0.55, "space_none"
        if ch in "اوی" and 0 < i < n - 1 and s[i - 1] not in " " + ZWNJ:
            yield s[:i] + s[i + 1:], {"ی": 0.3, "ا": 0.25, "و": 0.2}[ch], "drop_vowel"
            yield s[:i] + ch + s[i:], 0.08, "double_vowel"
        # ا <-> و between two consonants: پرامپت is very often written پرومپت
        if ch in "او" and 0 < i < n - 1 and _is_cons(s[i - 1]) and _is_cons(s[i + 1]):
            yield s[:i] + {"ا": "و", "و": "ا"}[ch] + s[i + 1:], 0.4, "swap_vowel"
        # a consonant lost inside a cluster just before the last letter (پرامپت -> پرامت)
        if i == n - 2 and n >= 4 and _is_cons(ch) and _is_cons(s[i - 1]) and _is_cons(s[i + 1]):
            yield s[:i] + s[i + 1:], 0.1, "drop_cons"
        if _is_cons(ch) and i + 1 < n and _is_cons(s[i + 1]) and not {ch, s[i + 1]} & GUTTURAL:
            for v, w in (("ی", 0.3), ("ا", 0.2), ("و", 0.12)):
                yield s[:i + 1] + v + s[i + 1:], w, "add_vowel"
        for grp, gw in HOMOPHONES:
            if ch in grp:
                if ch == "ه" and (i == n - 1 or s[i + 1] in " " + ZWNJ):
                    continue  # a silent final ه is never written ح
                for alt in grp:
                    if alt != ch:
                        yield s[:i] + alt + s[i + 1:], gw, "homophone"
        if ch in HEARD:
            yield s[:i] + HEARD[ch][0] + s[i + 1:], HEARD[ch][1], "heard"
    if "ی" in s:
        yield s.replace("ی", "ي"), 0.3, "ar_ye"
    if "ک" in s:
        yield s.replace("ک", "ك"), 0.3, "ar_kaf"
    if any(c in ARABIC_KB for c in s):
        yield "".join(ARABIC_KB.get(c, c) for c in s), 0.15, "ar_kb"
    if s and s[-1] in FA_LETTERS:
        yield s + s[-1], 0.08, "repeat_last"
    yield from _digit_ops(s)


def _digit_ops(s):
    if re.search("[۰-۹٠-٩]", s):
        yield fa.to_ascii_digits(s), 0.6, "ascii_digits"
    if re.search("[0-9۰-۹]", s):
        ar = fa.to_ascii_digits(s).translate({ord(str(i)): "٠١٢٣٤٥٦٧٨٩"[i] for i in range(10)})
        yield ar, 0.2, "ar_digits"
    if re.search("[0-9]", s):
        yield fa.to_fa_digits(s), 0.6, "fa_digits"


# ------------------------------------------------------------ Latin edits

def _ops_latin(s, letters=True, loan=False):
    """letters=False (acronyms such as MCP, AI): only space/hyphen and digit edits.
    loan=True (the English spelling itself): also the common prompt -> promt and plural -s."""
    n = len(s)
    for i, ch in enumerate(s):
        if letters:
            # c inside "ch" is a different sound: chatgpt never becomes khatgpt
            if ch in "ck" and not (ch == "c" and i + 1 < n and s[i + 1] == "h"):
                yield s[:i] + ("k" if ch == "c" else "c") + s[i + 1:], 0.35, "latin_ck"
            if ch in "aeiou" and 0 < i:
                for alt in {"a": "e", "e": "a", "i": "e", "o": "u", "u": "o"}[ch]:
                    yield s[:i] + alt + s[i + 1:], 0.2, "latin_vowel"
            if i + 1 < n and s[i + 1] == ch and ch.isalpha():
                yield s[:i] + s[i + 1:], 0.35, "latin_double"
        if ch in " -":
            yield s[:i] + s[i + 1:], 0.6, "latin_space"
            yield s[:i] + ("-" if ch == " " else " ") + s[i + 1:], 0.3, "latin_space"
    if loan and letters:
        if s.endswith("mpt"):
            yield s[:-2] + "t", 0.35, "latin_drop"
        if s[-1:].isalpha() and not s.endswith("s"):
            yield s + "s", 0.3, "latin_plural"
    if re.search("[۰-۹٠-٩]", s):
        yield fa.to_ascii_digits(s), 0.6, "ascii_digits"


# ------------------------------------------------------------ finglish

def _finglish(s):
    """Return [(latin, weight)] for a Persian word; short vowels are unknown so a few guesses."""
    t = fa.fold(s.replace(ZWNJ, " ").replace("آ", AA)).replace("أ", "ا")
    # letters and digits are separate words (دهه60 -> دهه 60), so a final silent ه stays final
    t = re.sub(r"(?<=[^\W\d_])(?=\d)|(?<=\d)(?=[^\W\d_])", " ", t)
    words = t.split()
    out = {}
    for joiner, jw in (("", 1.0), (" ", 0.7)):
        parts = [_finglish_word(w) for w in words]
        if not parts or any(not p for p in parts):
            return []
        combos = [("", 1.0)]
        for p in parts:
            combos = [(a + (joiner if a else "") + b, wa * wb) for a, wa in combos for b, wb in p]
            combos = sorted(combos, key=lambda x: -x[1])[:6]
        for lat, w in combos:
            if lat and (lat not in out or out[lat] < w * jw):
                out[lat] = w * jw
        if len(words) == 1:
            break
    return sorted(out.items(), key=lambda x: (-x[1], x[0]))[:6]


def _finglish_word(w):
    # tokens: (latin options, is_vowel)
    toks = []
    n = len(w)
    i = 0
    while i < n:
        ch = w[i]
        prev_vowel = i == 0 or w[i - 1] in VOWELS or w[i - 1] == AA
        if i == 0 and ch == "ا" and n > 1 and w[1] in "یو":
            # a word-initial ای / او is one vowel: ایران = iran, اوپن = open (not ayran / avpn)
            toks.append((["i", "ey"] if w[1] == "ی" else ["o", "u", "oo"], True))
            i += 2
            continue
        if ch == "ا" or ch == AA:
            toks.append((["a"], True))
        elif ch == "و":
            toks.append((["v"], False) if prev_vowel else (["o", "u", "oo"], True))
        elif ch == "ی":
            if i == 0 or (prev_vowel and i < n - 1):
                toks.append((["y"], False))
            else:
                toks.append((["i", "y"] if i == n - 1 else ["i", "ee"], True))
        elif ch == "ه":
            if i == n - 1 and i > 0:
                toks.append((["e", "eh", "h"], True))
            else:
                toks.append((["h"], False))
        elif ch.isdigit() or ch.isascii():
            toks.append(([ch], None))  # neither vowel nor consonant: ends a cluster
        elif ch in FINGLISH:
            toks.append((FINGLISH[ch], False))
        else:
            return []
        i += 1
    # Short vowels are not written in Persian. A word cannot start with two consonants and a
    # syllable cannot hold three, so guess a short vowel after the first consonant of such a run
    # (کلاد -> kelad, آرتیفکت -> artifakt). The bare cluster stays the top guess only at the start
    # of a word and only for a real English onset (prompt, claude); anywhere else it is weak.
    seq, k = [], 0
    while k < len(toks):
        if toks[k][1] is not False:
            seq.append(toks[k])
            k += 1
            continue
        j = k
        while j < len(toks) and toks[j][1] is False:
            j += 1
        run = toks[k:j]
        at_start = k == 0
        if len(run) >= 3 or (at_start and len(run) >= 2):
            seq.append(run[0])
            v1, v2 = ("e", "a") if at_start else ("a", "e")
            bare = 1.0 if at_start and run[0][0][0] + run[1][0][0] in ONSETS else 0.3
            if run[1][0][0] in ("h", ""):  # no loanword starts dh-/th-: دهه = dahe
                v1, v2, bare = "a", "e", 0.3
            seq.append(([("", bare), (v1, 0.95), (v2, 0.45)], True))
            seq.extend(run[1:])
        else:
            seq.extend(run)
        k = j
    combos = [("", 1.0)]
    for opts, _v in seq:
        nxt = []
        for a, wa in combos:
            for j, o in enumerate(opts):
                o, ow = o if isinstance(o, tuple) else (o, 1.0 if j == 0 else 0.45)
                nxt.append((a + o, wa * ow))
        combos = sorted(nxt, key=lambda x: -x[1])[:8]
    return combos


# ------------------------------------------------------------ numbers in words

def _num_words(n):
    """0..999 -> Persian words (60 -> شصت, 65 -> شصت و پنج); None when out of range."""
    if not 0 <= n <= 999:
        return None
    names = {}
    for word, val in fa._FA_WORD_NUM.items():
        names.setdefault(val, word)  # first spelling in the table is the standard one
    if n in names:
        return names[n]
    parts = []
    hundreds, rest = n - n % 100, n % 100
    if hundreds:
        parts.append(names[hundreds])
    if rest in names:
        parts.append(names[rest])
    elif rest:
        parts += [names[rest - rest % 10], names[rest % 10]]
    return " و ".join(parts)


def _spelled_numbers(s):
    """دهه ۶۰ -> [(«دهه شصت», 0.3), («دهه شست», 0.15)]: the number written out in words."""
    t = fa.to_ascii_digits(s)
    if not re.search(r"\d", t):
        return []
    bad = []

    def rep(m):
        words = _num_words(int(m.group(0)))
        if words is None:
            bad.append(m.group(0))
            return m.group(0)
        return " " + words + " "

    t = re.sub(r"\d+", rep, t)
    if bad:
        return []
    t = re.sub(" +", " ", t).strip()
    out = [(t, 0.3)]
    if "شصت" in t:
        out.append((t.replace("شصت", "شست"), 0.15))  # the most common misspelling of شصت
    return out


# ------------------------------------------------------------ generator

def _display(kw):
    s = fa.normalize(kw, diacritics=True).strip("«»\"'“”‹›")
    return fa.normalize(s)


def _canon(kw):
    s = _display(kw)
    return s.lower() if not _is_fa(s) else s


def generate(keyword, also=(), depth=2):
    """[(variant, score, [labels])] sorted by score; the first item is the keyword itself,
    spelled the way the user typed it."""
    display = _display(keyword)
    base = display.lower() if not _is_fa(display) else display
    if not base:
        return []
    latin_kw = not _is_fa(base)
    # acronyms (MCP, AI, n8n): no letter edits, only spacing and digits
    acronym = latin_kw and (display.isupper() or len(base.replace(" ", "")) <= 3)
    found = {}

    def add(v, w, why):
        v = v.strip()
        if not v:
            return False
        if v not in found or found[v][0] < w:
            found[v] = (w, why)
            return True
        return False

    seeds = []
    if display != base:
        # show the user's own casing (ChatGPT) as the keyword; edits run on the lowercase form
        add(display, 1.0, ["orig"])
        seeds.append((base, 0.95, ["latin_case"]))
    else:
        seeds.append((base, 1.0, ["orig"]))
    for a in also:
        a = _canon(a)
        if a and a != base:
            seeds.append((a, 0.85, ["also"]))
    if _is_fa(base):
        key = fa.fold(base).replace(" ", "")
        loan = key in LOANWORDS
        if loan:
            seeds.append((LOANWORDS[key], 0.6, ["loanword"]))
        # for a known loanword the real English spelling is already there: finglish guesses
        # (pramapt) must not outrank the real Persian misspellings
        fw = 0.15 if loan else 0.35
        for lat, w in _finglish(base):
            seeds.append((lat, fw * w, ["finglish"]))

    frontier = []
    for v, w, why in seeds:
        if add(v, w, why):
            frontier.append((v, w, why))
    for level in range(depth):
        nxt = []
        for v, w, why in frontier:
            if why[-1] in TERMINAL or (level and why[0] == "finglish"):
                continue  # finglish is already a guess: one edit on top of it is enough
            latin = not _is_fa(v)
            if latin:
                letters = not (acronym or (why[0] == "loanword" and len(v.replace(" ", "")) <= 3))
                loan_seed = level == 0 and why == ["loanword"]
                ops = _ops_latin(v, letters=letters, loan=loan_seed)
            else:
                ops = _ops_fa(v)
            for nv, ow, lab in ops:
                if nv == v:
                    continue
                score = w * ow
                if score < (0.03 if latin else 0.01):
                    continue
                label = [lab] if why in (["orig"], ["latin_case"]) else why + [lab]
                if add(nv, score, label):
                    nxt.append((nv, score, found[nv][1]))
        nxt.sort(key=lambda x: -x[1])
        frontier = nxt[:250]
    if _is_fa(base):
        for txt, w in _spelled_numbers(base):
            add(txt, w, ["num_words"])
    add("«" + display + "»", 0.3, ["quotes"])
    add('"' + display + '"', 0.2, ["quotes"])
    items = [(v, round(w, 4), why) for v, (w, why) in found.items()]
    items.sort(key=lambda x: (-x[1], abs(len(x[0]) - len(base)), x[0]))
    return items


# ------------------------------------------------------------ regex
# The pattern is written so that Python re, JavaScript (with or without the u flag, ES2018+ for
# the lookbehind) and PCRE read it the same way: no \w / \W (ASCII-only in JavaScript), invisible
# characters as \u escapes, and every repeat that could overlap a neighbour is bounded.

# a "word character" for the boundaries: Latin letters, digits, Arabic-script letters, marks and
# digits (not ، ؛ ؟ ٪ ۔, not ZWNJ: «کلاد‌ها» still counts as the keyword)
_WORD = (r"[0-9A-Za-z_\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u024F\u0610-\u061A\u0620-\u0669"
         r"\u066E-\u06D3\u06D5-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFE]")
_NOT_WORD = "[^" + _WORD[1:]
V = "[اآویيى]"
# what can sit inside a Persian word without changing it: tatweel, harakat, hamza above,
# superscript alef, ZWNJ, LRM, RLM, BOM
GAP = r"[\u0640\u064B-\u0652\u0654\u0670\u200C\u200E\u200F\uFEFF]*"
WGAP = r"[ \u200C]*"
# between two words, after a Persian letter: optional ezafe (دهه‌ی ۶۰، دهه ی ۶۰، دههٔ ۶۰)
EZAFE_GAP = r"(?:[ \u200C]*(?:[یيى]|\u0654))?[ \u200C]*"
REP = "{1,8}"  # a stretched last letter (آرتیفکتتت), bounded so long comments stay fast
# spoken-Persian endings glued to the keyword: ارتیفکتو، پرامپتشو، ارتیفکتها، کلادی
FA_SUFFIX = ("(?:\\u200C?(?:هاشو|هارو|های|هات|هاش|ها|اشو|ارو|اش|ای|شو|مو|تو|رو|یه|و|ی|ه|ش|م|ت|ا))?")
LAT_SUFFIX = "(?:'s|’s|es|s)?"
_SPECIAL = set("\\^$.|?*+()[]{}/")


def _esc(ch):
    return "\\" + ch if ch in _SPECIAL else ch


def _char_class(chars):
    chars = "".join(sorted(set(chars), key=chars.index))
    if len(chars) == 1:
        return _esc(chars)
    return "[" + "".join("\\" + c if c in "\\]^-[" else c for c in chars) + "]"


def _vslot(lo, hi):
    return "(?:" + GAP + V + "){%d,%d}" % (lo, hi)


def _fa_pattern(s):
    """A pattern for one Persian keyword that tolerates the usual misspellings. A vowel letter in
    the middle may be swapped or doubled; it may be dropped (and one may be added between two
    consonants) only when the word has at least three consonants, so a short keyword (سورا)
    does not shrink to a skeleton that matches سر, سری, سیر."""
    n = len(s)
    loose = sum(1 for c in s if _is_cons(c)) >= 3
    out = []
    prev_fa = False  # the previous token is a Persian letter: a GAP goes before the next one
    i = 0
    while i < n:
        ch = s[i]
        if ch in " " + ZWNJ:
            j = i
            while j < n and s[j] in " " + ZWNJ:
                j += 1
            out.append(EZAFE_GAP if i and s[i - 1] in FA_LETTERS else WGAP)
            prev_fa = False
            i = j
            continue
        gap = GAP if prev_fa else ""
        word_start = i == 0 or s[i - 1] in " " + ZWNJ
        if ch in VOWELS and word_start:
            if ch in ALEFS:
                cls = "[آا]"
            else:
                cls = "[یيى]" if ch == "ی" else "و"
            nxt_vowel = i + 1 < n and s[i + 1] in VOWELS
            out.append(gap + cls + ("" if nxt_vowel else REP))
            prev_fa = True
            i += 1
            continue
        if ch in VOWELS:
            j = i
            while j < n and s[j] in VOWELS:
                j += 1
            run = s[i:j]
            word_end = j == n or s[j] in " " + ZWNJ
            if word_end:
                mid, fin = run[:-1], run[-1]
                if mid:
                    out.append(_vslot(max(1, len(mid) - 1), len(mid) + 5))
                fin_cls = "[اآ]" if fin in ALEFS else ("[یيى]" if fin == "ی" else "و")
                out.append(GAP + fin_cls + REP)
            else:
                lo = max(0 if loose else 1, len(run) - 1)
                out.append(_vslot(lo, len(run) + 5))
            prev_fa = True
            i = j
            continue
        if ch.isdigit():
            d = fa.to_ascii_digits(ch)
            out.append(_char_class(d + fa.to_fa_digits(d) + "٠١٢٣٤٥٦٧٨٩"[int(d)]))
            prev_fa = False
            i += 1
            continue
        if ch not in FA_LETTERS:
            out.append(_esc(ch))
            prev_fa = False
            i += 1
            continue
        last = i == n - 1
        alts = ch
        for grp, _gw in HOMOPHONES:
            if ch in grp and not (ch == "ه" and (last or s[i + 1] in " " + ZWNJ)):
                alts += grp
        if ch in HEARD:
            alts += HEARD[ch][0]
        if ch == "ک":
            alts += "كگ"
        if ch in ARABIC_KB:
            alts += ARABIC_KB[ch]
            if ARABIC_KB[ch] == "ک":
                alts += "ك"
        out.append(gap + _char_class(alts) + (REP if last else ""))
        prev_fa = True
        if (not last and loose and _is_cons(s[i + 1])
                and not {ch, s[i + 1]} & GUTTURAL):
            out.append(_vslot(0, 2))  # a vowel letter added between two consonants
        i += 1
    return "".join(out)


def _fa_literal(v):
    """A Persian variant as a literal, with the same invisible-character and spacing tolerance."""
    out, prev_fa, i, n = [], False, 0, len(v)
    while i < n:
        ch = v[i]
        if ch in " " + ZWNJ:
            j = i
            while j < n and v[j] in " " + ZWNJ:
                j += 1
            out.append(EZAFE_GAP if i and v[i - 1] in FA_LETTERS else WGAP)
            prev_fa, i = False, j
            continue
        if ch == "-":
            out.append("[ -]*")
            prev_fa = False
        else:
            is_fa = "\u0600" <= ch <= "\u06FF"
            out.append((GAP if prev_fa and is_fa else "") + _esc(ch))
            prev_fa = is_fa
        i += 1
    return "".join(out)


def _latin_literal(v):
    return re.sub(r"(?:\\?[ \-])+", "[ -]*", "".join(_esc(c) for c in v))


def _fa_letter_count(s):
    return sum(1 for c in s if c in FA_LETTERS)


def build_regex(items, exact=False):
    """One pattern (use it case-insensitive, flag i) that matches every variant in items."""
    variants = [v for v, _s, _w in items]
    if not variants:
        return ""
    fa_bases = [v for v, _s, why in items if why in (["orig"], ["also"]) and _is_fa(v)]
    parts = [_fa_pattern(b) for b in fa_bases]
    rx = re.compile("(?:" + "|".join(parts) + ")", re.I) if parts else None
    fa_extra, lat_extra, fa_words, seen = [], [], list(fa_bases), set()
    for v in variants:
        bare = v.strip("«»\"").strip()
        if not bare or bare.lower() in seen:
            continue
        seen.add(bare.lower())  # flag i covers the other case: AI and ai are one entry
        if rx is not None and rx.fullmatch(bare):
            continue
        if _is_fa(bare):
            piece, dest = _fa_literal(bare), fa_extra
        else:
            piece, dest = _latin_literal(bare), lat_extra
        if re.fullmatch(piece, ""):
            continue  # a piece that matches nothing-at-all would match every comment
        if piece not in dest:
            dest.append(piece)
            if dest is fa_extra:
                fa_words.append(bare)
    groups = []
    fa_alts = parts + fa_extra
    if fa_alts:
        g = "(?:" + "|".join(fa_alts) + ")"
        # glued endings only for keywords of 3+ letters: on a 2-letter word they match too much
        if min(_fa_letter_count(w) for w in fa_words) >= 3:
            g += FA_SUFFIX
        groups.append(g)
    if lat_extra:
        groups.append("(?:" + "|".join(lat_extra) + ")" + LAT_SUFFIX)
    if not groups:
        return ""
    body = "(?:" + "|".join(groups) + ")"
    if exact:
        return "^" + _NOT_WORD + "*" + body + _NOT_WORD + "*$"
    return "(?<!" + _WORD + ")" + body + "(?!" + _WORD + ")"


def matches(pattern, text):
    """Exactly what the automation does: the printed pattern on the raw comment, flag i."""
    return re.search(pattern, text or "", re.I) is not None


# ------------------------------------------------------------ CLI

def _parser():
    p = argparse.ArgumentParser(
        prog="keyword.py",
        description="شکل‌های محتملی که بیننده‌ها کلمه‌ی کامنت را تایپ می‌کنند (برای اتوماسیون کامنت ← دایرکت).",
        epilog='نمونه: python3 -I keyword.py "آرتیفکت" --also artifact --regex')
    p.add_argument("keyword", help="کلمه‌ی کامنت، همان‌طور که روی صفحه می‌آید (فارسی یا انگلیسی)")
    p.add_argument("--also", action="append", default=[], metavar="WORD",
                   help="شکل دیگری از همان کلمه (مثلاً املای انگلیسی)؛ چند بار هم می‌شود")
    p.add_argument("--max", type=int, default=30, metavar="N", help="چند شکل نشان بدهد (پیش‌فرض ۳۰)")
    p.add_argument("--json", action="store_true", help="خروجی JSON")
    p.add_argument("--regex", action="store_true", help="فقط یک regex چاپ کن که همه‌ی شکل‌ها را بگیرد")
    p.add_argument("--exact", action="store_true",
                   help="regex برای وقتی که کل کامنت فقط همین کلمه است (به‌جای «کامنت شامل کلمه»)")
    p.add_argument("--test", action="append", default=[], metavar="COMMENT",
                   help="یک کامنت نمونه را با regex امتحان کن؛ چند بار هم می‌شود")
    return p


def main(argv=None):
    p = _parser()
    a = p.parse_args(argv)
    if a.max is not None and a.max < 1:
        p.error("مقدار --max باید ۱ یا بیشتر باشد")
    items = generate(a.keyword, a.also)
    if not items:
        print("کلمه‌ی کامنت خالی است. یک کلمه بده، مثلاً: python3 -I keyword.py \"آرتیفکت\"", file=sys.stderr)
        return 2
    pattern = build_regex(items, exact=a.exact)
    if not pattern or re.search(pattern, "", re.I):
        print("این کلمه فقط علامت است و regex آن هر کامنتی را می‌گیرد. "
              "کلمه‌ای بده که حرف یا عدد داشته باشد.", file=sys.stderr)
        return 2
    shown = items[:a.max]
    tests = [(t, matches(pattern, t)) for t in a.test]

    if a.json:
        out = {
            "keyword": items[0][0],
            "total": len(items),
            "variants": [{"text": v, "score": s, "why": [LABEL.get(w, w) for w in why]}
                         for v, s, why in shown],
            "regex": pattern,
            "regex_flags": "i",
            "regex_flavor": "python, javascript (ES2018+), pcre",
            "regex_mode": "exact" if a.exact else "contains",
            "tests": [{"comment": t, "match": m} for t, m in tests],
            "note": "امتیازها تخمینی‌اند (قاعده‌ی سرانگشتی)، نه شمارش واقعی کامنت‌ها.",
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if a.regex:
        print(pattern)
        print("حساس به حروف بزرگ/کوچک نباشد (فلگ i)؛ در پایتون و جاوااسکریپت یکسان کار می‌کند. "
              + ("فقط وقتی می‌گیرد که کل کامنت همین کلمه باشد." if a.exact
                 else "هر کامنتی که این کلمه را داشته باشد می‌گیرد."), file=sys.stderr)
        for t, m in tests:
            print(("می‌گیرد    " if m else "نمی‌گیرد  ") + t, file=sys.stderr)
        return 0

    print("کلمه‌ی کامنت: «%s»" % items[0][0])
    print("%s شکل ساخته شد؛ %s تای محتمل‌تر:" % (fa.to_fa_digits(str(len(items))),
                                              fa.to_fa_digits(str(len(shown)))))
    print()
    width = max(len(v) for v, _s, _w in shown)
    for k, (v, s, why) in enumerate(shown, 1):
        print("%s. %s   %s   (%s)" % (fa.to_fa_digits(str(k)).rjust(3), v.ljust(width),
                                    fa.to_fa_digits("%.2f" % s, separators=True),
                                    "، ".join(LABEL.get(w, w) for w in why)))
    print()
    print("برای کپی در اتوماسیون (هر خط یکی):")
    print("```")
    for v, _s, _w in shown:
        print(v)
    print("```")
    print()
    print("یک regex که همه‌ی %s شکل را می‌گیرد (فلگ i، در پایتون و جاوااسکریپت یکسان):"
          % fa.to_fa_digits(str(len(items))))
    print("```")
    print(pattern)
    print("```")
    if tests:
        print()
        print("امتحان کامنت‌ها (با همین regex، روی متن خام کامنت):")
        for t, m in tests:
            print("  %s  %s" % ("می‌گیرد  " if m else "نمی‌گیرد", t))
    print()
    print("امتیازها تخمینی‌اند (قاعده‌ی سرانگشتی از غلط‌های رایج)، نه آمار واقعی.")
    print("قبل از انتشار ریلز، جواب دایرکت را با چند تا از همین شکل‌ها واقعاً امتحان کن.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
