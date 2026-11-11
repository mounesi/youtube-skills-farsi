#!/usr/bin/env python3
"""title.py - عنوان و متن تامبنیل یوتیوب را با هم، به‌عنوان یک جفت، قبل از انتشار چک می‌کند.

    python3 -I title.py --title "..." --thumb "سه کلمه‌ی بزرگ"
    python3 -I title.py titles.txt --thumb "..."          # هر خط یک عنوان، رتبه‌بندی‌شده
    python3 -I title.py --title "..." --keyword "کلاد کد" --en "Claude Code in 10 minutes"
    python3 -I title.py --title "..." --json

فارسی و انگلیسی هر دو را می‌فهمد، با رقم فارسی/عربی/لاتین.

چه چیزهایی چک می‌شود:
  - طول: ۴۰ نویسه (فید موبایل)، ۶۰ (جستجوی دسکتاپ؛ هدف ≤ ۶۰ تا ۷۰)، ۱۰۰ (سقف یوتیوب).
  - تعداد کلمه‌ی عنوان فارسی: هدف ۶ تا ۷ کلمه، بیرون از ۴ تا ۱۰ هشدار.
  - کلیدواژه اول عنوان (--keyword).
  - شروع نکردن با اسم مهمان (--guest) یا «قسمت N»؛ برند و شماره‌ی قسمت آخر عنوان.
  - عدد، اسم یا تاریخ (رقم فارسی، عدد با حروف، اسم ماه شمسی و میلادی، اسم لاتین مثل Claude).
  - کلمه‌های مبهم فارسی و انگلیسی (فوق‌العاده، بهترین، amazing…).
  - شکلک زیاد و «!!!» (برای عنوان فارسی به‌جای چک حروف بزرگ).
  - تکرار نشدن کلمه‌های عنوان روی تامبنیل (روی کلمه‌های یکدست‌شده‌ی فارسی) و حداکثر ۳ کلمه روی تامبنیل.
  - ترجمه‌ی برگشتی: یوتیوب عنوان فارسی را از راه ترجمه هم می‌خواند؛ با --en ترجمه‌ی انگلیسی را بده
    تا ببینیم کلیدواژه، اسم‌ها و عددها در ترجمه مانده‌اند یا نه.

بر پایه‌ی title.py از Jake Schincariol (youtube-agent-skill، MIT).
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fatext as fa  # noqa: E402

MOBILE, DESKTOP, SOFT, HARD = 40, 60, 70, 100
WORDS_TARGET = (6, 7)
WORDS_OK = (4, 10)
THUMB_MAX = 3

VAGUE_EN = {"amazing", "incredible", "insane", "crazy", "huge", "massive", "ultimate", "best", "powerful",
            "secret", "revolutionary", "mindblowing", "epic", "perfect", "complete", "everything"}
VAGUE_FA_RAW = ["فوق‌العاده", "باورنکردنی", "باورنکردنیه", "خفن", "دیوانه‌کننده", "عالی", "بهترین",
                "انقلابی", "معجزه", "معجزه‌آسا", "شگفت‌انگیز", "بی‌نظیر", "جادویی", "قدرتمند", "همه‌چیز",
                "محشر", "وحشتناک", "ترکوند", "ترکونده", "کامل‌ترین", "نهایی"]
STOP_EN = {"the", "a", "an", "of", "for", "to", "in", "on", "and", "or", "is", "are", "with", "your", "you",
           "my", "i", "this", "that", "it", "how", "what", "why"}

# Persian month and weekday names (folded for comparison). «مه» and «می» are left out: fog / verb prefix.
MONTHS_FA_RAW = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی",
                 "بهمن", "اسفند",
                 "ژانویه", "ژانویهٔ", "فوریه", "مارس", "آوریل", "ژوئن", "ژوئیه", "جولای", "اوت", "آگوست",
                 "سپتامبر", "اکتبر", "نوامبر", "دسامبر"]
# «تیر», «مهر», «دی» are also everyday words (bullet, kindness, ...): count them only next to a number.
AMBIGUOUS_MONTHS_FA_RAW = ["تیر", "مهر", "دی"]
WEEKDAYS_FA_RAW = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "پنج‌شنبه", "جمعه"]
MONTHS_EN = {"january", "february", "march", "april", "may", "june", "july", "august", "september",
             "october", "november", "december", "jan", "feb", "apr", "jun", "jul", "aug", "sep", "sept",
             "oct", "nov", "dec"}
WEEKDAYS_EN = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
AMBIGUOUS_EN = {"may", "march"}  # everyday words; dates only when capitalised

# Spelled-out Persian numbers. «نه» (= no) and «یه» (= a) are left out on purpose.
NUM_WORDS_FA_RAW = ["یک", "دو", "سه", "چهار", "پنج", "شش", "شیش", "هفت", "هشت", "ده", "یازده", "دوازده",
                    "سیزده", "چهارده", "پانزده", "پونزده", "شانزده", "بیست", "سی", "چهل", "پنجاه", "شصت",
                    "هفتاد", "هشتاد", "نود", "صد", "دویست", "سیصد", "پانصد", "هزار", "میلیون", "میلیارد",
                    "نصف", "نیم"]

EPISODE_WORDS_RAW = ["قسمت", "اپیزود", "فصل", "ep", "episode", "part", "پارت"]
GUEST_OPENERS_RAW = ["دکتر", "مهندس", "استاد", "پروفسور", "گفتگو با", "گفت‌وگو با", "مصاحبه با",
                     "با حضور", "میهمان", "مهمان"]
DEFAULT_BRANDS = ["DrMounesi", "AI with AL"]

F = fa.fold
VAGUE_FA = {F(w): w for w in VAGUE_FA_RAW}
MONTHS_FA = {F(w) for w in MONTHS_FA_RAW}
AMBIG_FA = {F(w) for w in AMBIGUOUS_MONTHS_FA_RAW}
WEEKDAYS_FA = {F(w) for w in WEEKDAYS_FA_RAW}
NUM_WORDS_FA = {F(w) for w in NUM_WORDS_FA_RAW}
EPISODE_WORDS = {F(w) for w in EPISODE_WORDS_RAW}
STOP_ALL = {F(w) for w in fa.STOPWORDS_FA} | STOP_EN | {F(w) for w in fa.STOPWORDS_EN}

EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]")
BANG_RUN = re.compile(r"[!！]{2,}|[؟?]{2,}|[!！؟?]{3,}")
SEPARATORS = re.compile(r"\s[|｜–—\-:]\s|\s*[|｜]\s*")
FA_SUFFIXES = ("هایی", "های", "ها", "ترین", "تر", "ای", "ی")


def fd(x):
    """Persian digits for the report text."""
    return fa.to_fa_digits(str(x))


# ---------------------------------------------------------------- helpers

def toks(text):
    return [F(t) for t in fa.tokenize(text) if F(t)]


def stem(w):
    """Very light Persian stem for overlap checks (ویدیوهای → ویدیو)."""
    for s in FA_SUFFIXES:
        if w.endswith(s) and len(w) - len(s) >= 3 and re.search("[؀-ۿ]", w):
            return w[:-len(s)]
    return w


def content_set(text):
    return {stem(w) for w in toks(text) if w not in STOP_ALL and not w.isdigit()}


def find_seq(hay, needle):
    """Index of needle (folded tokens) inside hay; the last needle token may carry a suffix."""
    if not needle:
        return -1
    n = len(needle)
    for i in range(len(hay) - n + 1):
        if hay[i:i + n - 1] == needle[:-1] and hay[i + n - 1].startswith(needle[-1]):
            return i
    return -1


def char_pos_of_token(title, index):
    """Character position where token number `index` starts in the (normalized) title."""
    start = 0
    for k, tok in enumerate(fa.tokenize(title, normalized=False)):
        at = title.find(tok, start)
        if at < 0:
            break
        if k == index:
            return at
        start = at + len(tok)
    return len(title)


def numbers(title):
    ascii_t = fa.to_ascii_digits(title)
    found = re.findall(r"\d[\d,.٫٬]*%?٪?", ascii_t)
    spelled = [t for t in fa.tokenize(title) if F(t) in NUM_WORDS_FA]
    return found, spelled


def date_words(title):
    found = []
    tk = fa.tokenize(title)
    for i, w in enumerate(tk):
        f = F(w)
        lw = w.lower()
        if f in WEEKDAYS_FA:
            found.append(w)
        elif f in MONTHS_FA:
            if f in AMBIG_FA:
                near = tk[max(0, i - 1):i] + tk[i + 1:i + 2]
                if not any(re.search(r"\d", fa.to_ascii_digits(n)) for n in near):
                    continue
            found.append(w)
        elif re.fullmatch(r"[A-Za-z]+", w) and (lw in WEEKDAYS_EN or lw in MONTHS_EN):
            if lw in AMBIGUOUS_EN and not w[0].isupper():
                continue
            found.append(w)
    return found


def latin_names(title, persian):
    """Latin-script names. In a Persian title every Latin word is a name (Claude, ChatGPT).
    In an English title only CamelCase (YouTube), letter+digit (GPT-5), acronyms, or a capitalised
    word mid-sentence when the title is in sentence case. Title Case English cannot be told apart."""
    if persian:
        return fa.latin_tokens(title, phrases=True)
    words = re.findall(r"[A-Za-z][A-Za-z0-9'\-]*", title)
    out = []
    caps_mid = [w for w in words[1:] if w[0].isupper()]
    title_case = len(words) > 2 and len(caps_mid) >= (len(words) - 1) * 0.6
    for i, w in enumerate(words):
        if re.search(r"[a-z][A-Z]", w) or (re.search(r"\d", w) and re.search(r"[A-Za-z]", w)):
            out.append(w)
        elif len(w) >= 2 and w.isupper() and w != "I":
            continue  # acronyms like AI are too common to count as a name
        elif i > 0 and w[0].isupper() and w != "I" and not title_case and w.lower() not in STOP_EN:
            out.append(w)
    return out


def is_persian_title(title, brands):
    """Persian if Persian words are at least as many as Latin words (brand names not counted).
    Letter share alone fails on «آموزش Claude Code … | DrMounesi»."""
    skip = set()
    for b in brands:
        skip |= set(toks(b))
    fa_n = lat_n = 0
    for w in fa.tokenize(title):
        if F(w) in skip:
            continue
        c = fa.script_counts(w)
        if c["fa"] > c["latin"]:
            fa_n += 1
        elif c["latin"]:
            lat_n += 1
    return fa_n > 0 and fa_n >= lat_n


def segments(title):
    return [s for s in SEPARATORS.split(title) if s.strip()]


def brand_markers(title, brands):
    """(segment index, marker) for every brand / «قسمت N» marker in the title."""
    segs = segments(title)
    found = []
    for si, seg in enumerate(segs):
        ft = toks(seg)
        for b in brands:
            if find_seq(ft, toks(b)) >= 0:
                found.append((si, b))
        for i, w in enumerate(ft):
            if w in EPISODE_WORDS:
                found.append((si, fa.tokenize(seg)[i]))
        if re.search(r"(^|\s)#\d", fa.to_ascii_digits(seg)):
            found.append((si, "#N"))
    return segs, found


# ---------------------------------------------------------------- the check

def check(title, thumb=None, keyword=None, guest=None, en=None, keyword_en=None, brands=None):
    raw = (title or "").lstrip("﻿").strip()
    t = fa.normalize(raw)
    brands = DEFAULT_BRANDS if brands is None else brands
    n = len(t)
    issues, good, notes = [], [], []
    persian = is_persian_title(t, brands)
    tk = toks(t)

    if raw != t and re.search("[يكىـ]", raw):
        issues.append(("letters", "ی/ک عربی یا کشیده داشت؛ یوتیوب آن را با ی/ک فارسی یکی نمی‌گیرد. "
                                  "نسخه‌ی درست بالا آمده"))

    # length: 40 / 60 / 70 / 100
    if n > HARD:
        issues.append(("length", f"{fd(n)} نویسه؛ سقف یوتیوب {fd(HARD)} است"))
    elif n > SOFT:
        issues.append(("length", f"{fd(n)} نویسه؛ جستجوی دسکتاپ نزدیک {fd(DESKTOP)} می‌بُرد، هدف حداکثر "
                                 f"{fd(DESKTOP)} تا {fd(SOFT)} است"))
    elif n > DESKTOP:
        issues.append(("length", f"{fd(n)} نویسه؛ از {fd(DESKTOP)} رد شده و ته عنوان در دسکتاپ "
                                 "ممکن است بریده شود"))
    else:
        good.append(f"{fd(n)} نویسه، زیر برش {fd(DESKTOP)} نویسه‌ای دسکتاپ")
    if n > MOBILE:
        cut = t[:MOBILE + 1]  # one extra char keeps a word that ends exactly at the cut
        head = (cut.rsplit(" ", 1)[0] if " " in cut else t[:MOBILE]).rstrip()
        issues.append(("mobile", f"فید موبایل حدوداً «{head}…» را نشان می‌دهد؛ ببین موضوع و کلیدواژه "
                                 "در همین تکه مانده باشد"))

    # Persian word count
    if persian:
        wc = fa.word_count(t)
        if WORDS_TARGET[0] <= wc <= WORDS_TARGET[1]:
            good.append(f"{fd(wc)} کلمه، درست در هدف ۶ تا ۷ کلمه")
        elif WORDS_OK[0] <= wc <= WORDS_OK[1]:
            notes.append(f"{fd(wc)} کلمه؛ قابل قبول است ولی هدف ۶ تا ۷ کلمه است")
        else:
            issues.append(("word-count", f"{fd(wc)} کلمه؛ بیرون از بازه‌ی ۴ تا ۱۰ (هدف ۶ تا ۷ کلمه)"))

    # spam: emoji and !!! for every title, all-caps only for Latin-script titles
    emo = EMOJI.findall(t)
    if len(emo) > 2:
        issues.append(("spam", f"{fd(len(emo))} شکلک؛ بیشتر از دو تا عنوان را تبلیغاتی و اسپم نشان می‌دهد"))
    if BANG_RUN.search(t):
        issues.append(("spam", "«!!!» یا «؟؟» پشت‌سرهم؛ یک علامت کافی است، بیشتر از آن حالت اسپم دارد"))
    if not persian:
        caps = [w for w in t.split() if len(w) > 2 and w.isupper()]
        if len(caps) > 2:
            issues.append(("shouting", f"{fd(len(caps))} کلمه با حروف بزرگ؛ بیشتر از دو تا حالت داد زدن و "
                                       "اسپم دارد"))
        elif caps:
            good.append(f"{fd(len(caps))} کلمه‌ی حروف بزرگ برای تأکید")

    # vague words (single tokens + joined bigrams, so «فوق العاده» with a space is caught too)
    cand = set(tk) | {a + b for a, b in zip(tk, tk[1:])}
    cand |= {c[:-len(x)] for c in list(cand) for x in ("ترین", "تر") if c.endswith(x) and len(c) > len(x) + 2}
    lat = re.findall(r"[a-z0-9']+", t.lower()) + re.findall(r"[a-z0-9']+", t.lower().replace("-", ""))
    v_fa = sorted(VAGUE_FA[w] for w in cand if w in VAGUE_FA)
    v_en = sorted({w for w in lat if w in VAGUE_EN})
    v = v_fa + v_en
    if v:
        issues.append(("vague", f"{'، '.join(v)}؛ به‌جایش یک عدد، یک اسم یا یک تاریخ بگذار"))

    # number / date / name
    nums, spelled = numbers(t)
    dates = date_words(t)
    names = [x for x in latin_names(t, persian)
             if not any(F(x) == F(b) or F(x) in toks(b) for b in brands)]
    if nums or spelled:
        shown = [fd(x) for x in nums] + spelled
        good.append(f"عدد مشخص دارد ({'، '.join(shown[:3])})")
    elif dates:
        good.append(f"تاریخ مشخص دارد ({'، '.join(dates[:3])})")
    elif names:
        good.append(f"اسم مشخص دارد ({'، '.join(names[:3])})")
    else:
        issues.append(("no-number", "نه عدد پیدا شد، نه تاریخ، نه اسم لاتین. یک عدد، تاریخ یا اسم مشخص "
                                    "اضافه کن (اسم فارسی آدم‌ها و اسم‌های Title Case انگلیسی را تشخیص "
                                    "نمی‌دهم، دستی چک کن)"))
    if dates and (nums or spelled):
        good.append(f"تاریخ هم دارد ({'، '.join(dates[:2])})")

    if t.endswith("?") or t.endswith("؟"):
        good.append("سؤال باز در عنوان")
        if persian and t.endswith("?"):
            notes.append("در عنوان فارسی علامت سؤال فارسی «؟» بگذار، نه «?»")

    # front-load: first three words all stopwords
    front = [w for w in tk[:3] if w not in STOP_ALL]
    if tk and not front:
        issues.append(("front-load", "سه کلمه‌ی اول همه کلمه‌ی پرکننده‌اند؛ موضوع را بیاور جلو"))

    # starts with «قسمت N» / episode marker
    if tk and (tk[0] in EPISODE_WORDS or re.match(r"#\d", fa.to_ascii_digits(t))):
        issues.append(("episode-first", "با «قسمت N» شروع شده؛ شماره‌ی قسمت را ببر آخر عنوان، "
                                        "اول عنوان مال کلیدواژه است"))
    # starts with the guest's name
    if guest:
        gi = find_seq(tk, toks(guest))
        if gi == 0:
            issues.append(("guest-first", f"با اسم مهمان («{guest}») شروع شده؛ کسی اسم او را جستجو "
                                          "نمی‌کند، موضوع حرفش را بیاور اول"))
    else:
        for op in GUEST_OPENERS_RAW:
            if find_seq(tk[:len(toks(op))], toks(op)) == 0:
                issues.append(("guest-first", f"با «{op}» شروع شده؛ احتمالاً اسم مهمان اول آمده. "
                                              "موضوع حرف را بیاور اول و اسم را ببر وسط یا آخر"))
                break

    # brand / episode at the end
    segs, markers = brand_markers(t, brands)
    if markers:
        last = len(segs) - 1
        ep_first = "episode-first" in [k for k, _ in issues]
        early = [m for si, m in markers if si != last and not (ep_first and si == 0 and F(m) in EPISODE_WORDS)]
        if len(segs) == 1:
            first_tok = min(find_seq(tk, toks(m)) if m != "#N" else 0 for _, m in markers)
            if 0 <= first_tok < len(tk) - 3 and not (ep_first and first_tok == 0):
                early = [markers[0][1]]
        if early:
            issues.append(("brand-last", f"«{early[0]}» وسط یا اول عنوان آمده؛ برند و شماره‌ی قسمت "
                                         "همیشه آخر عنوان می‌آیند (مثلاً «… | DrMounesi»)"))
        else:
            good.append("برند/شماره‌ی قسمت آخر عنوان است")

    # keyword first
    if keyword:
        kt = toks(keyword)
        ki = find_seq(tk, kt)
        if ki < 0:
            issues.append(("keyword", f"کلیدواژه‌ی «{keyword}» در عنوان نیست"))
        elif ki == 0:
            good.append(f"کلیدواژه‌ی «{keyword}» اول عنوان است")
        else:
            pos = char_pos_of_token(t, ki)
            where = "بعد از ۴۰ نویسه‌ی اول، یعنی در موبایل دیده نمی‌شود" if pos >= MOBILE else \
                f"از کلمه‌ی {fd(ki + 1)} شروع می‌شود"
            issues.append(("keyword-first", f"کلیدواژه‌ی «{keyword}» هست ولی اول عنوان نیست ({where})؛ "
                                            "ببرش اول"))

    # thumbnail
    if thumb:
        tw, hw = content_set(t), content_set(thumb)
        shared = tw & hw
        if shared:
            issues.append(("duplicate", f"تامبنیل همان کلمه‌های عنوان را تکرار می‌کند ({'، '.join(sorted(shared))})؛ "
                                        "تامبنیل باید چیزی بگوید که عنوان نمی‌گوید"))
        else:
            good.append("تامبنیل و عنوان کلمه‌های متفاوت دارند")
        nthumb = fa.word_count(thumb)
        if nthumb > THUMB_MAX:
            issues.append(("thumb-length", f"{fd(nthumb)} کلمه روی تامبنیل؛ در اندازه‌ی فید سقف سه کلمه است"))
        if fa.is_persian(thumb):
            lt = fa.latin_tokens(thumb)
            if lt:
                notes.append(f"کلمه‌ی لاتین روی تامبنیل ({'، '.join(lt)})؛ اگر اسم برند یا محصول نیست، "
                             "فارسی‌اش کن")

    # back-translation
    back = None
    if en is not None:
        en_l = en.lower()
        missing = []
        want = []
        if keyword_en:
            want.append(keyword_en)
        elif keyword and fa.latin_tokens(keyword):
            want.append(" ".join(fa.latin_tokens(keyword)))
        for nm in fa.latin_tokens(t, phrases=True):
            if nm not in want and not any(b.lower() == nm.lower() for b in brands):
                want.append(nm)
        for w in want:
            if w.lower() not in en_l:
                missing.append(w)
        for num in nums:
            core = re.sub(r"[^\d]", "", num)
            if core and core not in re.sub(r"[^\d ]", "", fa.to_ascii_digits(en)).split() and core not in en:
                missing.append(fa.to_fa_digits(num))
        back = {"en": en, "missing": missing, "checked": want + [fa.to_fa_digits(x) for x in nums]}
        if missing:
            issues.append(("back-translation", f"در ترجمه‌ی برگشتی گم شد: {'، '.join(missing)}. یوتیوب عنوان را "
                                               "این‌طور می‌فهمد؛ عنوان را طوری بازنویسی کن که ترجمه درست دربیاید"))
        elif want or nums:
            good.append("کلیدواژه، اسم‌ها و عددها در ترجمه‌ی برگشتی ماندند")
        if keyword and not keyword_en and not fa.latin_tokens(keyword):
            notes.append("کلیدواژه فارسی است؛ برای چک آن در ترجمه، شکل انگلیسی‌اش را با --keyword-en بده")
    elif persian:
        back = {"en": None, "missing": [], "checked": []}
        notes.append("ترجمه‌ی برگشتی: عنوان را به انگلیسی ترجمه کن، بلند بخوان، و اگر معنی یا کلیدواژه "
                     "عوض شد بازنویسی‌اش کن. بعد با --en \"...\" دوباره اجرا کن")

    score = max(0, min(100, 100 - 14 * len(issues) + 4 * len(good)))
    return {"title": t, "chars": n, "words": fa.word_count(t), "persian": persian, "score": score,
            "issues": issues, "good": good, "notes": notes, "back_translation": back}


# ---------------------------------------------------------------- output

LABELS = {"length": "طول", "mobile": "موبایل", "word-count": "تعداد کلمه", "spam": "اسپم",
          "shouting": "حروف بزرگ", "vague": "مبهم", "no-number": "بی‌عدد", "front-load": "شروع ضعیف",
          "episode-first": "شروع با قسمت", "guest-first": "اسم مهمان", "brand-last": "جای برند",
          "keyword": "کلیدواژه", "keyword-first": "کلیدواژه", "duplicate": "تکرار", "letters": "حروف عربی",
          "thumb-length": "تامبنیل", "back-translation": "ترجمه"}


def show(r):
    print(f"\n  «{r['title']}»")
    print(f"  {fd(r['chars'])} نویسه   {fd(r['words'])} کلمه   امتیاز {fd(r['score'])}/۱۰۰")
    for k, m in r["issues"]:
        print(f"    ✗  {LABELS.get(k, k)}: {m}")
    for m in r["good"]:
        print(f"    ✓  {m}")
    for m in r["notes"]:
        print(f"    •  {m}")


class FaParser(argparse.ArgumentParser):
    def error(self, message):
        print(f"title.py: ورودی درست نیست ({message}). راهنما: python3 -I title.py -h", file=sys.stderr)
        sys.exit(2)


def main(argv=None):
    p = FaParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", nargs="?", help="فایل متنی، هر خط یک عنوان (خط‌های شروع‌شده با # نادیده)")
    p.add_argument("--title", help="یک عنوان برای چک")
    p.add_argument("--thumb", help="متن تامبنیل که با عنوان(ها) جفت می‌شود")
    p.add_argument("--keyword", help="کلیدواژه‌ای که باید اول عنوان بیاید")
    p.add_argument("--keyword-en", dest="keyword_en", help="شکل انگلیسی کلیدواژه برای چک ترجمه‌ی برگشتی")
    p.add_argument("--guest", help="اسم مهمان (عنوان نباید با آن شروع شود)")
    p.add_argument("--brand", action="append", help="برند یا اسم کانال (چند بار هم می‌شود)؛ "
                                                    "پیش‌فرض: DrMounesi و AI with AL")
    p.add_argument("--en", help="ترجمه‌ی برگشتی انگلیسی عنوان (فقط با --title)")
    p.add_argument("--json", action="store_true", help="خروجی JSON به‌جای گزارش")
    args = p.parse_args(argv)
    kw = dict(keyword=args.keyword, guest=args.guest, keyword_en=args.keyword_en, brands=args.brand)
    if args.title is not None:
        if not args.title.strip():
            print("title.py: عنوان خالی است", file=sys.stderr)
            sys.exit(1)
        rows = [check(args.title, args.thumb, en=args.en, **kw)]
    elif args.file and os.path.isfile(args.file):
        if args.en is not None:
            print("title.py: --en فقط با یک عنوان (--title) کار می‌کند", file=sys.stderr)
            sys.exit(1)
        try:
            with open(args.file, encoding="utf-8-sig") as f:
                lines = f.read().splitlines()
        except (OSError, UnicodeDecodeError) as e:
            print(f"title.py: فایل خوانده نشد: {args.file} ({e})", file=sys.stderr)
            sys.exit(1)
        rows = [check(l, args.thumb, **kw) for l in lines if l.strip() and not l.lstrip().startswith("#")]
        if not rows:
            print(f"title.py: فایل هیچ عنوانی ندارد: {args.file}", file=sys.stderr)
            sys.exit(1)
    elif args.file and not os.path.exists(args.file):
        print(f"title.py: فایل پیدا نشد: {args.file}", file=sys.stderr)
        sys.exit(1)
    else:
        print(__doc__)
        sys.exit(1)
    rows.sort(key=lambda r: -r["score"])
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return
    for r in rows:
        show(r)
    if len(rows) > 1:
        print(f"\n  {fd(len(rows))} عنوان رتبه‌بندی شد. دو یا سه‌تای اول را نگه دار و دو تای قوی را در "
              "«Test & compare» یوتیوب استودیو بگذار.")
    print()


if __name__ == "__main__":
    main()
