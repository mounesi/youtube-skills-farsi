#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""seo.py - بررسی توضیحات (description) و تگ‌های ویدیوی یوتیوب، فارسی یا انگلیسی.

کاربرد:
    python3 -I seo.py description.txt
    python3 -I seo.py description.txt --tags "هوش مصنوعی,AI,کلاد,Claude"
    python3 -I seo.py description.txt --duration 18:42 --title "..." --keyword "کلاد کد"
    python3 -I seo.py --tags "a,b,c"            فقط تگ‌ها
    python3 -I seo.py - < description.txt       خواندن از ورودی استاندارد
    --tags-file tags.txt   تگ‌ها از فایل (با ویرگول یا هر تگ در یک خط)
    --json                 خروجی JSON

چیزی منتشر نمی‌کند؛ فقط می‌خواند و گزارش می‌دهد.
کد خروج: ۰ = بدون خطا (هشدار مجاز است)، ۱ = دست‌کم یک خطا، ۲ = ورودی یا فایل نادرست.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fatext as fa  # noqa: E402

# Rule sources, shown next to every check.
SRC_YT = "قانون رسمی یوتیوب"
SRC_DM = "تجربه‌ی کانال DrMounesi"
SRC_H = "قاعده‌ی سرانگشتی"

LEVELS = ("ok", "info", "warn", "error")
LABEL = {"ok": "درست", "info": "نکته", "warn": "هشدار", "error": "خطا"}

DESC_MAX = 5000
TAGS_MAX = 500
HOOK_GOOD, HOOK_MAX = 95, 150
CHAPTER_MIN_S = 10.0
CHAPTER_TITLE_MAX = 50
HASH_SHOWN, HASH_SPAM, HASH_IGNORED = 3, 15, 60

_URL = re.compile(
    r"(?:https?://|www\.)\S+"
    r"|\b(?:[A-Za-z0-9-]+\.)+(?:com|be|me|ir|org|net|io|ai|ly|co|app|dev|gg|tv|to)(?![A-Za-z0-9-])(?:/\S*)?",
    re.I)
_YT = re.compile(
    r"(?:https?://)?(?:www\.|m\.|music\.)?(?:youtube\.com/(?P<path>[^\s]*)|youtu\.be/(?P<short>[^\s]+))",
    re.I)
_DIG = "0-9۰-۹٠-٩"
_TS = r"[{d}]{{1,2}}(?::[{d}]{{2}}){{1,2}}".format(d=_DIG)
_LEAD = "\\s\\-–—•●▪◾*▫➤→►▶()\\[\\]"
_CHAPTER = re.compile(r"^[{lead}]*?\(?\[?({ts})\]?\)?(?=\s|$|[-–—:|.])[\s\-–—:|.]*(.*)$".format(
    lead=_LEAD, ts=_TS))
_CHAPTER_END = re.compile(r"\S.*?[\s\-–—:|(\[]\(?({ts})\)?\]?\s*$".format(ts=_TS))
_BULLET = re.compile(r"^\s*(?:[-–—•●▪◾*▫➤→►▶✅✔☑🔹🔸🔻👉📌]|[{d}]{{1,2}}[.)\-](?![{d}]))\s*\S".format(d=_DIG))
_HASHTAG = re.compile("#[\\w\u200c]+")
_ARABIC_LETTERS = re.compile("[يىك]")
_WATCH_CUES = {fa.fold(w) for w in (
    "ببین", "ببینید", "ببینی", "ببینین", "تماشا", "بعدی", "قبلی", "قسمت", "ادامه", "پلی‌لیست",
    "پلیلیست", "لیست", "ویدیو", "ویدئو", "اینو", "اینجا", "watch", "next", "playlist", "part",
    "video", "see", "continue", "series")}
_GREETING = {fa.fold(w) for w in (
    "سلام", "درود", "دوستان", "امروز", "خب", "hi", "hello", "hey", "welcome", "today")}
_COMMENT_CUES = {fa.fold(w) for w in (
    "کامنت", "نظرت", "نظرتون", "نظر", "بنویس", "بنویسید", "بنویسین", "بگو", "بگید", "بگین",
    "comment", "comments", "tell", "let", "below")}


# ---------------------------------------------------------------- helpers

def n(x):
    """Number in Persian digits for messages."""
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    return fa.to_fa_digits(str(x))


def squash(s):
    """Comparison form that also ignores spaces (کلاد کد == کلاد‌کد == کلادکد)."""
    return re.sub(r"\s+", "", fa.fold(s))


def _bare(s):
    """Comparison form without spaces, ZWNJ or punctuation (؛ ، . ! ? « » …), for the title check."""
    return re.sub(r"[\W_]+", "", fa.fold(s))


def _hook_has_keyword(keyword, hook):
    """Whole-word match: «AI» is not inside «Gmail», but «ایمیل» matches «ایمیل‌ها»
    and «کلاد کد» matches «کلادکد»."""
    kt = [fa.fold(t) for t in fa.tokenize(keyword)]
    if not kt:
        return bool(squash(keyword)) and squash(keyword) in squash(hook)
    toks = fa.tokenize(hook)
    full = [fa.fold(t) for t in toks]
    cut = [fa.fold(t.split(fa.ZWNJ)[0]) for t in toks]  # «ایمیل‌ها» -> «ایمیل»
    k = len(kt)
    for i in range(len(toks) - k + 1):
        if all(kt[j] in (full[i + j], cut[i + j]) for j in range(k)):
            return True
    sk = squash(keyword)
    for size in {max(1, k - 1), k, k + 1}:
        for i in range(len(full) - size + 1):
            if "".join(full[i:i + size]) == sk:
                return True
    return False


def strip_urls(s):
    return _URL.sub(" ", s)


def visible(line):
    """Line without bidi marks/BOM, for parsing."""
    return fa.normalize(line).strip()


def check(level, cid, title, msg, source):
    return {"id": cid, "level": level, "title": title, "message": msg, "source": source}


def paragraphs(lines):
    """[(start_index, [lines])] split on blank lines."""
    out, cur, start = [], [], None
    for i, ln in enumerate(lines):
        if ln.strip():
            if start is None:
                start = i
            cur.append(ln)
        elif cur:
            out.append((start, cur))
            cur, start = [], None
    if cur:
        out.append((start, cur))
    return out


def hashtags_in(line):
    return [m.group(0) for m in _HASHTAG.finditer(strip_urls(line))]


def is_hashtag_line(line):
    s = strip_urls(visible(line))
    tags = hashtags_in(s)
    if not tags:
        return False
    rest = _HASHTAG.sub(" ", s)
    return fa.word_count(rest) <= len(tags)  # mostly hashtags (allows «#هوش مصنوعی» mistakes)


def chapter_match(line):
    m = _CHAPTER.match(visible(line))
    if not m:
        return None
    t = fa.parse_timestamp(m.group(1))
    if t is None:
        return None
    return t, m.group(1), m.group(2).strip()


# ---------------------------------------------------------------- description checks

def check_length(text):
    c = len(text)
    if c > DESC_MAX:
        return check("error", "length", "طول توضیحات",
                     "{} کاراکتر؛ سقف یوتیوب {} است و بیشترش ذخیره نمی‌شود. {} کاراکتر کم کن.".format(
                         n(c), n(DESC_MAX), n(c - DESC_MAX)), SRC_YT)
    return check("ok", "length", "طول توضیحات", "{} از {} کاراکتر.".format(n(c), n(DESC_MAX)), SRC_YT)


def check_angle_brackets(text):
    if "<" in text or ">" in text:
        return check("error", "brackets", "علامت < و >",
                     "توضیحات < یا > دارد؛ YouTube Studio این دو علامت را در توضیحات قبول نمی‌کند. "
                     "به جایشان ‹ › یا «» بگذار.", SRC_YT)
    return None


def check_arabic_letters(text):
    k = len(_ARABIC_LETTERS.findall(text))
    if k:
        return check("warn", "arabic_letters", "ی و ک عربی",
                     "{} حرف ي/ى/ك عربی پیدا شد. جست‌وجوی فارسی با ی و ک فارسی است؛ "
                     "با کیبورد فارسی دوباره بنویس.".format(n(k)), SRC_H)
    return None


def check_hook(lines, title=None, keyword=None):
    out = []
    first = next((ln for ln in lines if ln.strip()), "")
    hook = visible(first)
    if not hook:
        return [check("error", "hook", "خط اول (هوک)", "توضیحات خالی است.", SRC_DM)]
    c = len(hook)
    if c <= HOOK_GOOD:
        out.append(check("ok", "hook", "خط اول (هوک)",
                         "{} کاراکتر؛ بالای «...بیشتر» کامل دیده می‌شود.".format(n(c)), SRC_DM))
    elif c <= HOOK_MAX:
        out.append(check("info", "hook", "خط اول (هوک)",
                         "{} کاراکتر؛ بهتر است ≤ {} باشد تا در موبایل و نتیجه‌ی جست‌وجو کامل دیده شود.".format(
                             n(c), n(HOOK_GOOD)), SRC_DM))
    else:
        out.append(check("warn", "hook", "خط اول (هوک)",
                         "{} کاراکتر؛ خیلی بلند است (بیشتر از {}) و بریده می‌شود. یک جمله‌ی کوتاه با کلیدواژه "
                         "بنویس.".format(n(c), n(HOOK_MAX)), SRC_DM))
    first_words = [fa.fold(w) for w in fa.tokenize(hook)[:4]]
    if any(w in _GREETING for w in first_words[:2]) or " ".join(first_words[:3]).startswith("in this video"):
        out.append(check("warn", "hook_greeting", "شروع با سلام",
                         "خط اول با سلام و مقدمه شروع شده. این خط همان متنی است که در نتیجه‌ی جست‌وجو دیده می‌شود؛ "
                         "مستقیم بگو بیننده چه می‌گیرد.", SRC_DM))
    if _URL.search(hook):
        out.append(check("error", "hook_link", "لینک در خط اول",
                         "خط اول لینک دارد. خط اول برای قول ویدیو و کلیدواژه است؛ لینک را به خط دوم ببر.",
                         SRC_DM))
    if title:
        t, h = _bare(title), _bare(hook)
        if t and t == h:
            out.append(check("warn", "hook_title", "تکرار عنوان",
                             "خط اول عین عنوان است. همان قول را با کلمه‌های دیگر بگو تا عبارت‌های جست‌وجوی بیشتری را "
                             "پوشش بدهد.", SRC_DM))
        elif t and len(t) >= 15 and t in h:
            out.append(check("warn", "hook_title", "تکرار عنوان",
                             "خط اول عنوان را عیناً در خودش تکرار کرده. همان قول را با کلمه‌های دیگر بگو تا عبارت‌های "
                             "جست‌وجوی بیشتری را پوشش بدهد.", SRC_DM))
    if keyword:
        if _hook_has_keyword(keyword, hook):
            out.append(check("ok", "hook_keyword", "کلیدواژه در خط اول",
                             "«{}» در خط اول هست.".format(keyword), SRC_DM))
        else:
            out.append(check("warn", "hook_keyword", "کلیدواژه در خط اول",
                             "«{}» در خط اول نیست؛ عبارتی که مردم جست‌وجو می‌کنند باید در همین خط باشد.".format(
                                 keyword), SRC_DM))
    return out


def check_watch_next(lines):
    nonempty = [ln for ln in lines if ln.strip()]
    title = "خط دوم (ویدیوی بعدی)"
    if len(nonempty) < 2:
        return [check("warn", "watch_next", title,
                      "خط دومی نیست. خط دوم = یک جمله‌ی «اینو هم ببین» + لینک یک ویدیوی دیگر از یک پلی‌لیست.",
                      SRC_DM)]
    line = visible(nonempty[1])
    m = _YT.search(line)
    if not m:
        return [check("warn", "watch_next", title,
                      "خط دوم لینک یوتیوب ندارد. یک جمله‌ی «ویدیوی بعدی» + لینک ویدیوی دیگرت بگذار "
                      "(ترجیحاً لینکی که &list= دارد تا پخش خودکار در همان پلی‌لیست ادامه پیدا کند).", SRC_DM)]
    out = []
    url = m.group(0)
    path = m.group("path") or ""
    if "list=" in url:
        out.append(check("ok", "watch_next", title, "لینک پلی‌لیست هست (list=).", SRC_DM))
    elif path.startswith("@") or path.startswith("channel/") or path.startswith("c/"):
        out.append(check("warn", "watch_next", title,
                         "لینک خط دوم به کانال است، نه یک ویدیو. لینک یک ویدیو از پلی‌لیست بگذار "
                         "(…watch?v=…&list=…).", SRC_DM))
    else:
        out.append(check("warn", "watch_next", title,
                         "لینک یوتیوب هست ولی پلی‌لیستی نیست. لینک ویدیو را از داخل پلی‌لیست کپی کن تا "
                         "&list= داشته باشد؛ بیننده بعد از آن ویدیو در زنجیره‌ی تو می‌ماند.", SRC_DM))
    words = fa.tokenize(strip_urls(line))
    if len(words) < 2:
        out.append(check("warn", "watch_next_text", "جمله‌ی ویدیوی بعدی",
                         "خط دوم فقط لینک است. یک جمله قبلش بگذار که بگوید چرا باید آن را ببیند.", SRC_DM))
    elif not any(fa.fold(w) in _WATCH_CUES for w in words):
        out.append(check("info", "watch_next_text", "جمله‌ی ویدیوی بعدی",
                         "جمله‌ی خط دوم شبیه دعوت به ویدیوی بعدی نیست (مثلاً «قسمت قبلی رو ندیدی؟ اینجا ببین»).",
                         SRC_H))
    return out


def check_bullets(lines):
    k = 0
    for ln in lines:
        v = visible(ln)
        if not _BULLET.match(v) or chapter_match(v):
            continue
        if fa.word_count(strip_urls(v)) >= 2:
            k += 1
    if k == 0:
        return check("warn", "bullets", "فهرست نکته‌ها",
                     "فهرستی (- یا •) نیست. ۴ تا ۶ خط کوتاه بنویس که هر کدام یک چیز از ویدیو را با کلمه‌هایی که "
                     "مردم جست‌وجو می‌کنند بگوید.", SRC_DM)
    if 4 <= k <= 6:
        return check("ok", "bullets", "فهرست نکته‌ها", "{} خط فهرست.".format(n(k)), SRC_DM)
    return check("info", "bullets", "فهرست نکته‌ها",
                 "{} خط فهرست؛ پیشنهاد ۴ تا ۶ است.".format(n(k)), SRC_DM)


def chapter_scan(lines):
    """Chapter runs in the description.

    Returns (blocks, gapped, bad): blocks = [[(index, seconds, raw, title)]]; a run goes on across
    blank lines and lines with an impossible time, and ends only at another non-blank line.
    gapped = ids (positions in blocks) of runs that had blank lines inside; bad = [(index, raw)]
    for lines that look like a chapter but whose time is impossible (e.g. 3:75)."""
    blocks, gapped, bad = [], set(), []
    cur, gap, cur_gapped = [], False, False
    for i, ln in enumerate(lines):
        if not ln.strip():
            if cur:
                gap = True
            continue
        cm = chapter_match(ln)
        if cm:
            if cur and gap:
                cur_gapped = True
            cur.append((i,) + cm)
            gap = False
            continue
        m = _CHAPTER.match(visible(ln))
        if m and fa.parse_timestamp(m.group(1)) is None:
            bad.append((i, m.group(1)))
            continue
        if cur:
            if cur_gapped:
                gapped.add(len(blocks))
            blocks.append(cur)
        cur, gap, cur_gapped = [], False, False
    if cur:
        if cur_gapped:
            gapped.add(len(blocks))
        blocks.append(cur)
    return blocks, gapped, bad


def chapter_blocks(lines):
    return chapter_scan(lines)[0]


def validate_chapters(entries, duration=None):
    """entries: [(seconds, title)]. Returns [(level, message, source)]; YouTube rules local copy."""
    probs = []
    if not entries:
        return probs
    if entries[0][0] != 0:
        probs.append(("error", "فصل اول باید از 0:00 شروع شود (الان {}).".format(
            fa.fmt_timestamp(entries[0][0])), SRC_YT))
    if len(entries) < 3:
        probs.append(("error", "دست‌کم ۳ فصل لازم است (الان {}).".format(n(len(entries))), SRC_YT))
    for a, b in zip(entries, entries[1:]):
        if b[0] <= a[0]:
            probs.append(("error", "زمان‌ها باید صعودی باشند: {} بعد از {} آمده.".format(
                fa.fmt_timestamp(b[0]), fa.fmt_timestamp(a[0])), SRC_YT))
        elif b[0] - a[0] < CHAPTER_MIN_S:
            probs.append(("error", "فصل {} فقط {} ثانیه است؛ هر فصل دست‌کم ۱۰ ثانیه.".format(
                fa.fmt_timestamp(a[0]), n(int(b[0] - a[0]))), SRC_YT))
    if duration is not None:
        last = entries[-1][0]
        if last >= duration:
            probs.append(("error", "فصل آخر ({}) بعد از پایان ویدیو ({}) است.".format(
                fa.fmt_timestamp(last), fa.fmt_timestamp(duration)), SRC_YT))
        elif duration - last < CHAPTER_MIN_S:
            probs.append(("error", "فصل آخر فقط {} ثانیه است؛ فصل آخر هم باید دست‌کم ۱۰ ثانیه باشد.".format(
                n(int(duration - last))), SRC_YT))
    for t, ttl in entries:
        if not ttl:
            probs.append(("warn", "فصل {} عنوان ندارد.".format(fa.fmt_timestamp(t)), SRC_DM))
        elif len(ttl) > CHAPTER_TITLE_MAX:
            probs.append(("warn", "عنوان فصل {} {} کاراکتر است؛ ≤ {} و به شکل «چیزی که بیننده می‌گیرد».".format(
                fa.fmt_timestamp(t), n(len(ttl)), n(CHAPTER_TITLE_MAX)), SRC_DM))
    return probs


def check_chapters(lines, duration=None):
    title = "فصل‌ها (چپترها)"
    blocks, gapped, bad = chapter_scan(lines)
    bad_checks = [check("error", "chapters", title,
                        "زمان «{}» در خط {} معتبر نیست (دقیقه و ثانیه باید زیر ۶۰ باشند).".format(raw, n(i + 1)),
                        SRC_YT) for i, raw in bad]
    if not blocks and bad_checks:
        return bad_checks
    if not blocks:
        tail = [ln for ln in lines if _CHAPTER_END.match(visible(ln)) and not _URL.search(ln)]
        if len(tail) >= 2:
            return [check("warn", "chapters", title,
                          "زمان‌ها آخر خط آمده‌اند. شکل مستند یوتیوب «0:00 عنوان» است؛ زمان را اول خط بگذار.",
                          SRC_YT)]
        return [check("info", "chapters", title,
                      "فصلی پیدا نشد. برای ویدیوی بلند با yt-chapters فصل بساز (0:00 اول، دست‌کم ۳، هر کدام ≥ ۱۰ ثانیه).",
                      SRC_YT)]
    block = max(blocks, key=len) if not any(b[0][1] == 0 for b in blocks) else \
        next(b for b in blocks if b[0][1] == 0)
    if block[0][1] != 0 and len(block) == 1 and not bad_checks:
        return [check("info", "chapters", title,
                      "فقط یک زمان در توضیحات هست ({})؛ این فصل‌بندی نیست و یوتیوب از آن فصل نمی‌سازد. "
                      "برای فصل‌بندی با 0:00 شروع کن و دست‌کم ۳ فصل بنویس.".format(fa.fmt_timestamp(block[0][1])),
                      SRC_YT)]
    entries = [(e[1], e[3]) for e in block]
    out = list(bad_checks)
    if blocks.index(block) in gapped:
        out.append(check("warn", "chapters_gap", "خط خالی بین فصل‌ها",
                         "بین خط‌های فصل خط خالی هست؛ فصل‌ها را پشت سر هم و بدون خط خالی بنویس.", SRC_H))
    probs = validate_chapters(entries, duration)
    errs = [p for p in probs if p[0] == "error"] + bad_checks
    for lvl, msg, src in probs:
        out.append(check(lvl, "chapters", title, msg, src))
    if not errs:
        msg = "{} فصل، معتبر.".format(n(len(entries)))
        if duration is None:
            msg += " طول فصل آخر بررسی نشد؛ با --duration طول ویدیو را بده."
        out.append(check("ok", "chapters", title, msg, SRC_YT))
    if any(re.search("[۰-۹٠-٩]", e[2]) for e in block):
        out.append(check("warn", "chapters_digits", "رقم‌های زمان",
                         "زمان فصل‌ها با رقم فارسی نوشته شده. مطمئن نیستیم یوتیوب آن را فصل بشناسد؛ "
                         "با رقم انگلیسی بنویس (0:00).", SRC_H))
    if len(blocks) > 1:
        out.append(check("info", "chapters_blocks", "چند فهرست زمان",
                         "بیش از یک فهرست زمان در توضیحات هست ({})؛ فقط یکی را فصل‌بندی کن.".format(
                             "، ".join("از خط {} با {}".format(n(b[0][0] + 1), b[0][2]) for b in blocks)), SRC_H))
    return out


def check_question(lines, skip):
    qs = []
    for i, ln in enumerate(lines):
        if i in skip or not ln.strip():
            continue
        v = visible(ln)
        if chapter_match(v) or is_hashtag_line(v):
            continue
        body = strip_urls(v).strip()
        k = body.count("؟") + body.count("?")
        if k:
            qs.append((body, k))
    title = "سؤال برای کامنت"
    if not qs:
        return check("warn", "question", title,
                     "سؤالی برای کامنت نیست. یک سؤال مشخص بپرس که جوابش کوتاه باشد "
                     "(مثلاً «تو با کدوم شروع می‌کنی؟ تو کامنت بنویس»).", SRC_DM)
    total = sum(k for _, k in qs)
    if total > 1:
        return check("warn", "question", title,
                     "{} سؤال پیدا شد؛ فقط یک سؤال بپرس تا جواب‌ها پخش نشوند.".format(n(total)), SRC_DM)
    words = {fa.fold(w) for w in fa.tokenize(qs[0][0])}
    if not words & _COMMENT_CUES:
        return check("info", "question", title,
                     "یک سؤال هست ولی نمی‌گوید جواب را کجا بنویسند؛ «تو کامنت بنویس» را اضافه کن.", SRC_H)
    return check("ok", "question", title, "یک سؤال برای کامنت هست.", SRC_DM)


def check_english_block(lines, text):
    title = "بخش انگلیسی"
    if fa.script_ratio(strip_urls(text)) < 0.3:
        return check("info", "english", title, "توضیحات انگلیسی است؛ بخش انگلیسی جدا لازم نیست.", SRC_DM)
    paras = [p for p in paragraphs(lines)
             if not all(is_hashtag_line(ln) for ln in p[1])]
    tail = paras[-3:]
    for _, plines in reversed(tail):
        body = " ".join(strip_urls(visible(ln)) for ln in plines if not chapter_match(ln))
        counts = fa.script_counts(body)
        letters = counts["fa"] + counts["latin"]
        if letters and counts["latin"] >= 40 and counts["latin"] / letters >= 0.8 and fa.word_count(body) >= 8:
            sentences = len(re.findall(r"[.!?](?:\s|$)", body.strip() + " "))
            if sentences > 3:
                return check("info", "english", title,
                             "بخش انگلیسی هست ولی {} جمله است؛ ۱ تا ۳ جمله کافی است.".format(n(sentences)), SRC_DM)
            return check("ok", "english", title, "بخش انگلیسی نزدیک آخر توضیحات هست.", SRC_DM)
    return check("warn", "english", title,
                 "نزدیک آخر توضیحات یک پاراگراف ۱ تا ۳ جمله‌ای انگلیسی نیست. یوتیوب متن فارسی را از راه "
                 "ترجمه می‌فهمد و کیفیت ترجمه از فارسی پایین است؛ یک خلاصه‌ی انگلیسی قبل از هشتگ‌ها بگذار.", SRC_DM)


def check_hashtags(lines):
    out = []
    title = "هشتگ‌ها"
    all_tags, positions = [], []
    for i, ln in enumerate(lines):
        for t in hashtags_in(visible(ln)):
            all_tags.append(t)
            positions.append(i)
    total = len(all_tags)
    if total == 0:
        return [check("warn", "hashtags", title,
                      "هشتگی نیست. ۳ هشتگ مرتبط در آخرین خط بگذار (یوتیوب ۳ تای اول را بالای عنوان نشان می‌دهد).",
                      SRC_YT)]
    paras = paragraphs(lines)
    last_start = paras[-1][0] if paras else 0
    body = [t for t, p in zip(all_tags, positions) if p < last_start]
    if total > HASH_IGNORED:
        out.append(check("error", "hashtags", title,
                         "{} هشتگ؛ با بیش از ۶۰ هشتگ یوتیوب همه‌ی هشتگ‌های ویدیو را نادیده می‌گیرد.".format(n(total)),
                         SRC_YT))
    elif total > HASH_SPAM:
        out.append(check("warn", "hashtags", title,
                         "{} هشتگ؛ بیش از ۱۵ هشتگ اسپم به نظر می‌رسد. ۳ تا بس است.".format(n(total)), SRC_DM))
    elif total > HASH_SHOWN:
        out.append(check("warn", "hashtags", title,
                         "{} هشتگ؛ یوتیوب فقط ۳ تای اول را بالای عنوان نشان می‌دهد. ۳ تای اصلی را نگه دار.".format(
                             n(total)), SRC_YT))
    else:
        out.append(check("ok", "hashtags", title, "{} هشتگ.".format(n(total)), SRC_YT))
    if body:
        out.append(check("warn", "hashtags_place", "جای هشتگ‌ها",
                         "{} هشتگ وسط متن است ({}). هشتگ‌ها را به آخرین خط ببر.".format(
                             n(len(body)), " ".join(body[:3])), SRC_DM))
    # Persian hashtag spelling problems
    for ln in lines:
        v = strip_urls(visible(ln))
        if not hashtags_in(v):
            continue
        for m in re.finditer(r"#[^\s#]+", v):
            raw = m.group(0)
            core = _HASHTAG.match(raw)
            core = core.group(0) if core else "#"
            if fa.ZWNJ in core:
                out.append(check("warn", "hashtag_zwnj", "نیم‌فاصله در هشتگ",
                                 "«{}» نیم‌فاصله دارد؛ هشتگ ممکن است آنجا بشکند. با _ بنویس: «{}».".format(
                                     core, core.replace(fa.ZWNJ, "_")), SRC_H))
            if len(core) < len(raw) and raw[len(core)] in "-‐–.":
                out.append(check("warn", "hashtag_break", "هشتگ شکسته",
                                 "«{}» بعد از «{}» می‌شکند؛ کلمه‌ها را با _ به هم بچسبان.".format(raw, core), SRC_YT))
        if is_hashtag_line(v):
            m = re.search(r"#([^\W\d_]+)\s+([^#\s\W\d][^\s#]*)", v)
            if m and fa.is_persian(m.group(1)) and fa.is_persian(m.group(2)):
                out.append(check("warn", "hashtag_space", "فاصله در هشتگ",
                                 "«#{} {}» دو تکه است و فقط «#{}» هشتگ می‌شود. بنویس «#{}_{}».".format(
                                     m.group(1), m.group(2), m.group(1), m.group(1), m.group(2)), SRC_YT))
    folded = [fa.fold(t) for t in all_tags]
    dups = sorted({t for t, f in zip(all_tags, folded) if folded.count(f) > 1})
    if dups:
        out.append(check("info", "hashtag_dup", "هشتگ تکراری", "تکراری: " + " ".join(dups), SRC_H))
    return out


def lint_description(text, title=None, keyword=None, duration=None):
    if text.startswith("﻿"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    # A line with only invisible characters (RLM/LRM/ZWNJ/BOM, a paste artefact) is a blank line.
    lines = [ln if visible(ln) else "" for ln in lines]
    res = [check_length(text)]
    for c in (check_angle_brackets(text), check_arabic_letters(text)):
        if c:
            res.append(c)
    res += check_hook(lines, title, keyword)
    res += check_watch_next(lines)
    res.append(check_bullets(lines))
    res += check_chapters(lines, duration)
    nonempty_idx = [i for i, ln in enumerate(lines) if ln.strip()]
    res.append(check_question(lines, set(nonempty_idx[:2])))
    res.append(check_english_block(lines, text))
    res += check_hashtags(lines)
    return res


# ---------------------------------------------------------------- tags

def split_tags(raw):
    parts = re.split(r"[,،٬\n]", raw)
    return [p.strip() for p in parts if p.strip()]


def studio_length(tags):
    """Studio counts commas, and a tag with a space as if wrapped in quotes."""
    if not tags:
        return 0
    return sum(len(t) + (2 if " " in t else 0) for t in tags) + len(tags) - 1


def lint_tags(tags):
    out = []
    title = "تگ‌ها"
    if not tags:
        return [check("warn", "tags", title, "تگی داده نشد.", SRC_H)]
    L = studio_length(tags)
    if L > TAGS_MAX:
        out.append(check("error", "tags", title,
                         "حدود {} کاراکتر (با ویرگول‌ها و گیومه‌ی تگ‌های چندکلمه‌ای، به شیوه‌ی شمارش Studio)؛ "
                         "سقف ۵۰۰ است. {} کاراکتر کم کن.".format(n(L), n(L - TAGS_MAX)), SRC_YT))
    else:
        out.append(check("ok", "tags", title, "{} تگ، حدود {} از ۵۰۰ کاراکتر.".format(n(len(tags)), n(L)), SRC_YT))
    fa_tags = [t for t in tags if fa.script_counts(t)["fa"] > 0]
    en_tags = [t for t in tags if fa.script_counts(t)["latin"] > 0]
    if not fa_tags or not en_tags:
        missing = "انگلیسی" if not en_tags else "فارسی"
        out.append(check("warn", "tags_scripts", "املای فارسی و انگلیسی",
                         "تگ {} نیست. هر دو املا را بگذار (مثلاً «کلاد» و «Claude») چون بیننده‌ها هر دو را تایپ "
                         "می‌کنند.".format(missing), SRC_DM))
    else:
        out.append(check("ok", "tags_scripts", "املای فارسی و انگلیسی",
                         "{} تگ فارسی و {} تگ انگلیسی.".format(n(len(fa_tags)), n(len(en_tags))), SRC_DM))
    hashed = [t for t in tags if t.startswith("#")]
    if hashed:
        out.append(check("warn", "tags_hash", "# در تگ",
                         "تگ # نمی‌خواهد: " + "، ".join(hashed[:5]), SRC_H))
    folded = [fa.fold(t) for t in tags]
    dups = sorted({t for t, f in zip(tags, folded) if folded.count(f) > 1})
    if dups:
        msg = "تکراری: " + "، ".join(dups)
        groups = {}
        for t in dups:
            groups.setdefault(fa.fold(t), set()).add(t)
        if any(len({t.lower() for t in g}) > 1 for g in groups.values()):
            msg += ". بعضی فقط در نیم‌فاصله، اعراب، آ/ا یا ی/ک عربی فرق دارند؛ اگر عمداً برای کیبورد عربی گذاشتی، نگهش دار."
        out.append(check("info", "tags_dup", "تگ تکراری", msg, SRC_H))
    if len(tags) > 15:
        out.append(check("info", "tags_many", "تعداد تگ‌ها",
                         "{} تگ؛ تگ‌ها سیگنال ضعیفی‌اند و ۱۵ تا بس است. وقتت را روی عنوان و تامبنیل بگذار.".format(
                             n(len(tags))), SRC_H))
    return out


# ---------------------------------------------------------------- CLI

USAGE = __doc__


def parse_args(argv):
    opts = {"file": None, "tags": None, "tags_file": None, "title": None, "keyword": None,
            "duration": None, "json": False}
    flags = {"--tags": "tags", "--tags-file": "tags_file", "--title": "title", "--keyword": "keyword",
             "--duration": "duration"}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            return "help", None
        if a == "--json":
            opts["json"] = True
        elif "=" in a and a.split("=", 1)[0] in flags:
            k, v = a.split("=", 1)
            opts[flags[k]] = v
        elif a in flags:
            if i + 1 >= len(argv) or (argv[i + 1].startswith("--") and argv[i + 1] != "--"):
                return None, "{} مقدار می‌خواهد.".format(a)
            opts[flags[a]] = argv[i + 1]
            i += 1
        elif a.startswith("--"):
            return None, "گزینه‌ی ناشناخته: {}".format(a)
        elif opts["file"] is None:
            opts["file"] = a
        else:
            return None, "فقط یک فایل توضیحات بده."
        i += 1
    if opts["duration"] is not None:
        d = fa.parse_timestamp(opts["duration"])
        if d is None or d <= 0:
            return None, "--duration نامعتبر است (مثلاً 18:42 یا 1122)."
        opts["duration"] = d
    if opts["file"] is None and opts["tags"] is None and opts["tags_file"] is None:
        return None, None
    return opts, None


def read_text(path):
    if path == "-":
        data = sys.stdin.buffer.read()
        return data.decode("utf-8-sig")
    with open(path, encoding="utf-8-sig") as f:
        return f.read()


def why(e):
    if isinstance(e, FileNotFoundError):
        return "پیدا نشد"
    if isinstance(e, IsADirectoryError):
        return "پوشه است، نه فایل"
    if isinstance(e, UnicodeDecodeError):
        return "با UTF-8 خوانده نمی‌شود"
    return e.__class__.__name__


def summarize(res):
    errs = sum(1 for r in res if r["level"] == "error")
    warns = sum(1 for r in res if r["level"] == "warn")
    return errs, warns


def print_report(name, res, tags):
    print()
    if name:
        print("بررسی توضیحات یوتیوب: {}".format(name))
    for r in res:
        print("  [{}] {}: {}  ({})".format(LABEL[r["level"]], r["title"], r["message"], r["source"]))
    errs, warns = summarize(res)
    print()
    if errs:
        print("نتیجه: {} خطا، {} هشدار. خطاها را قبل از انتشار درست کن.".format(n(errs), n(warns)))
    elif warns:
        print("نتیجه: خطایی نیست، {} هشدار. هشدارها را بخوان و خودت تصمیم بگیر.".format(n(warns)))
    else:
        print("نتیجه: همه‌چیز مرتب است.")
    if tags is not None:
        print("یادت باشد: تگ‌ها کم‌اثرند؛ عنوان، تامبنیل و خط اول توضیحات خیلی بیشتر اثر دارند.")
    print("این ابزار چیزی منتشر نمی‌کند.")
    print()


def utf8_stdio():
    """UTF-8 output even on a Windows pipe or a legacy locale (-I ignores PYTHONIOENCODING)."""
    if hasattr(fa, "utf8_stdio"):
        fa.utf8_stdio()
        return
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def main(argv=None):
    utf8_stdio()
    argv = sys.argv[1:] if argv is None else argv
    opts, err = parse_args(argv)
    if opts == "help":
        sys.stdout.write(USAGE)
        return 0
    if opts is None:
        if err:
            sys.stderr.write("خطا: {}\n".format(err))
        sys.stderr.write(USAGE)
        return 2
    res = []
    text = None
    if opts["file"] is not None:
        try:
            text = read_text(opts["file"])
        except (OSError, UnicodeDecodeError) as e:
            sys.stderr.write("خطا: فایل «{}» خوانده نشد ({}).\n".format(opts["file"], why(e)))
            return 2
        if not text.strip():
            sys.stderr.write("خطا: فایل «{}» خالی است.\n".format(opts["file"]))
            return 2
        res += lint_description(text, opts["title"], opts["keyword"], opts["duration"])
    tags = None
    if opts["tags"] is not None or opts["tags_file"] is not None:
        raw = opts["tags"] or ""
        if opts["tags_file"] is not None:
            try:
                raw = (raw + "," if raw else "") + read_text(opts["tags_file"])
            except (OSError, UnicodeDecodeError) as e:
                sys.stderr.write("خطا: فایل تگ‌ها «{}» خوانده نشد ({}).\n".format(
                    opts["tags_file"], why(e)))
                return 2
        tags = split_tags(raw)
        res += lint_tags(tags)
    errs, warns = summarize(res)
    if opts["json"]:
        out = {"file": opts["file"], "chars": len(text) if text is not None else None,
               "errors": errs, "warnings": warns, "checks": res}
        if tags is not None:
            out["tags"] = tags
            out["tags_chars"] = studio_length(tags)
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        print_report(opts["file"], res, tags)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
