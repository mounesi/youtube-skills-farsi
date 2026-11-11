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
    "homophone": "حرف هم‌صدا",
    "heard": "اشتباه شنیداری",
    "repeat_last": "تکرار حرف آخر",
    "ascii_digits": "رقم انگلیسی",
    "fa_digits": "رقم فارسی",
    "ar_digits": "رقم عربی",
    "quotes": "داخل گیومه",
    "also": "شکلی که خودت دادی",
    "loanword": "املای انگلیسی",
    "finglish": "فینگلیش",
    "latin_case": "حروف کوچک",
    "latin_ck": "c ↔ k",
    "latin_vowel": "جابه‌جایی حرف صدادار لاتین",
    "latin_double": "حرف دوتایی لاتین",
    "latin_space": "فاصله/خط تیره‌ی لاتین",
}


# nobody inserts a vowel letter next to these (دهه never becomes دیهه)
GUTTURAL = set("هحعءئ")
# edits that end a chain (a second edit on top of them only adds noise)
TERMINAL = {"repeat_last", "double_vowel", "quotes", "ar_digits"}


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

def _ops_latin(s):
    n = len(s)
    for i, ch in enumerate(s):
        if ch in "ck":
            yield s[:i] + ("k" if ch == "c" else "c") + s[i + 1:], 0.35, "latin_ck"
        if ch in "aeiou" and 0 < i:
            for alt in {"a": "e", "e": "a", "i": "e", "o": "u", "u": "o"}[ch]:
                yield s[:i] + alt + s[i + 1:], 0.2, "latin_vowel"
        if i + 1 < n and s[i + 1] == ch and ch.isalpha():
            yield s[:i] + s[i + 1:], 0.35, "latin_double"
        if ch in " -":
            yield s[:i] + s[i + 1:], 0.6, "latin_space"
            yield s[:i] + ("-" if ch == " " else " ") + s[i + 1:], 0.3, "latin_space"
    if re.search("[۰-۹٠-٩]", s):
        yield fa.to_ascii_digits(s), 0.6, "ascii_digits"


# ------------------------------------------------------------ finglish

def _finglish(s):
    """Return [(latin, weight)] for a Persian word; short vowels are unknown so a few guesses."""
    t = fa.fold(s.replace(ZWNJ, " ")).replace("أ", "ا")
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
    for i, ch in enumerate(w):
        prev_vowel = i == 0 or w[i - 1] in VOWELS
        if ch == "ا":
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
    # Short vowels are not written in Persian. A word cannot start with two consonants and a
    # syllable cannot hold three, so guess a short vowel after the first consonant of such a run
    # (کلاد -> kelad, آرتیفکت -> artifakt); the bare skeleton stays as a weaker option.
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
            # loanwords keep the bare cluster (prompt), Persian words take the vowel (kelas)
            v1, v2 = ("e", "a") if at_start else ("a", "e")
            bare = 1.0
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


# ------------------------------------------------------------ generator

def _canon(kw):
    s = fa.normalize(kw, diacritics=True).strip("«»\"'“”‹›")
    s = fa.normalize(s)
    return s.lower() if not _is_fa(s) else s


def generate(keyword, also=(), depth=2):
    """[(variant, score, [labels])] sorted by score; the first item is the keyword itself."""
    base = _canon(keyword)
    if not base:
        return []
    found = {}

    def add(v, w, why):
        v = v.strip()
        if not v:
            return False
        if v not in found or found[v][0] < w:
            found[v] = (w, why)
            return True
        return False

    seeds = [(base, 1.0, ["orig"])]
    for a in also:
        a = _canon(a)
        if a and a != base:
            seeds.append((a, 0.85, ["also"]))
    if _is_fa(base):
        key = fa.fold(base).replace(" ", "")
        if key in LOANWORDS:
            seeds.append((LOANWORDS[key], 0.6, ["loanword"]))
        for lat, w in _finglish(base):
            seeds.append((lat, 0.35 * w, ["finglish"]))
    if not _is_fa(base) and keyword.strip() != base and keyword.strip():
        add(keyword.strip(), 0.4, ["latin_case"])

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
            ops = _ops_latin(v) if latin else _ops_fa(v)
            for nv, ow, lab in ops:
                if nv == v:
                    continue
                score = w * ow
                if score < (0.03 if latin else 0.01):
                    continue
                if add(nv, score, why + [lab] if why != ["orig"] else [lab]):
                    nxt.append((nv, score, found[nv][1]))
        nxt.sort(key=lambda x: -x[1])
        frontier = nxt[:250]
    add("«" + base + "»", 0.3, ["quotes"])
    add('"' + base + '"', 0.2, ["quotes"])
    items = [(v, round(w, 4), why) for v, (w, why) in found.items()]
    items.sort(key=lambda x: (-x[1], abs(len(x[0]) - len(base)), x[0]))
    return items


# ------------------------------------------------------------ regex

def _char_class(chars):
    chars = "".join(sorted(set(chars), key=chars.index))
    if len(chars) == 1:
        return re.escape(chars)
    return "[" + "".join("\\" + c if c in "\\]^-[" else c for c in chars) + "]"


def _fa_pattern(s):
    out = []
    n = len(s)
    for i, ch in enumerate(s):
        last = i == n - 1
        if ch in " " + ZWNJ:
            out.append("[ " + ZWNJ + "]?")
            continue
        if ch in ALEFS:
            out.append("[آا]+" if i == 0 else "[اآویيى]*")
            continue
        if ch in "یو":
            own = "[یيى]" if ch == "ی" else "و"
            if i == 0 or last:
                out.append(own + "+")
            else:
                out.append("[اآویيى]*")  # dropped, doubled or swapped vowel letter
            continue
        if ch.isdigit():
            d = fa.to_ascii_digits(ch)
            out.append(_char_class(d + fa.to_fa_digits(d) + "٠١٢٣٤٥٦٧٨٩"[int(d)]))
            continue
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
        cls = _char_class(alts)
        out.append(cls + ("+" if last else ""))
        if not last and _is_cons(s[i + 1]):
            out.append("[اآویيى]*")
    return "".join(out)


def build_regex(items, exact=False):
    """One pattern (use it case-insensitive) that matches every variant in items."""
    variants = [v for v, _s, _w in items]
    if not variants:
        return ""
    fa_bases = [v for v, _s, why in items if why in (["orig"], ["also"]) and _is_fa(v)]
    parts = [_fa_pattern(b) for b in fa_bases]
    core = "(?:" + "|".join(parts) + ")" if parts else ""
    rx = re.compile(core, re.I) if core else None
    extra = []
    for v in variants:
        bare = v.strip("«»\"")
        if rx is not None and rx.fullmatch(bare):
            continue
        piece = re.escape(bare).replace("\\ ", "[ -]?").replace("\\-", "[ -]?")
        if piece not in extra:
            extra.append(piece)
    alts = parts + extra
    body = "(?:" + "|".join(alts) + ")"
    if exact:
        return r"^[\W_]*" + body + r"[\W_]*$"
    return r"(?<!\w)" + body + r"(?!\w)"


def matches(pattern, text):
    return re.search(pattern, fa.normalize(text) if text else "", re.I) is not None or \
        re.search(pattern, text or "", re.I) is not None


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
            "regex_mode": "exact" if a.exact else "contains",
            "tests": [{"comment": t, "match": m} for t, m in tests],
            "note": "امتیازها تخمینی‌اند (قاعده‌ی سرانگشتی)، نه شمارش واقعی کامنت‌ها.",
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if a.regex:
        print(pattern)
        print("حساس به حروف بزرگ/کوچک نباشد (فلگ i). "
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
    print("یک regex که همه‌ی %s شکل را می‌گیرد (بدون حساسیت به حروف بزرگ/کوچک):"
          % fa.to_fa_digits(str(len(items))))
    print("```")
    print(pattern)
    print("```")
    if tests:
        print()
        print("امتحان کامنت‌ها:")
        for t, m in tests:
            print("  %s  %s" % ("می‌گیرد  " if m else "نمی‌گیرد", t))
    print()
    print("امتیازها تخمینی‌اند (قاعده‌ی سرانگشتی از غلط‌های رایج)، نه آمار واقعی.")
    print("قبل از انتشار ریلز، جواب دایرکت را با چند تا از همین شکل‌ها واقعاً امتحان کن.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
