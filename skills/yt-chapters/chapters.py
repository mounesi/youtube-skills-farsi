#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chapters.py - فصل‌بندی (چپتر) یوتیوب از زیرنویس زمان‌دار، و بررسی یک فهرست فصل آماده.

ساختن پیش‌نویس فصل‌ها از زیرنویس (.srt / .vtt / .json ویسپر):

    python3 -I chapters.py transcript.srt
    python3 -I chapters.py transcript.srt --target 8 --duration 12:40
    python3 -I chapters.py transcript.srt --json

بررسی فهرستی که خودت نوشته‌ای یا از توضیحات کپی کرده‌ای (رقم فارسی هم قبول است، مثل «۰۰:۰۰ مقدمه»):

    python3 -I chapters.py --check chapters.txt --duration 12:40
    python3 -I chapters.py --check chapters.txt transcript.srt     # طول ویدیو از زیرنویس
    python3 -I chapters.py --check - < chapters.txt                # از ورودی استاندارد

قانون‌های رسمی یوتیوب (Help Center، «Video chapters») که اینجا بررسی می‌شوند: اولین فصل 0:00،
دست‌کم ۳ فصل، زمان‌ها به ترتیب صعودی، هر فصل دست‌کم ۱۰ ثانیه. این ابزار فصل آخر را هم تا پایان
ویدیو می‌سنجد (اگر طول ویدیو را بدهی). سقف ۵۰ نویسه برای عنوان قاعده‌ی این پک است، نه یوتیوب.

خروجی همیشه یک بلوک آماده‌ی چسباندن با رقم انگلیسی (0-9) است؛ امن‌ترین شکل برای یوتیوب.
مرزها از مکث‌های واقعی گفتار و تغییر واژه‌ها پیدا می‌شوند؛ عنوان‌ها پیش‌نویس‌اند و باید بازنویسی شوند.

کد خواندن زیرنویس و پیدا کردن مرزها از youtube-agent-skill اثر Jake Schincariol (مجوز MIT) است.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fatext as fa  # noqa: E402

MIN_LEN = 10.0          # YouTube: each chapter >= 10 s
MIN_COUNT = 3           # YouTube: at least 3 chapters
TITLE_MAX = 50          # this pack's rule (readable on a phone), not a YouTube limit

USAGE = ("python3 -I chapters.py transcript.srt [--target N] [--duration 12:40] [--json]\n"
         "       python3 -I chapters.py --check chapters.txt [transcript.srt] [--duration 12:40] [--json]")

# Titles that say where you are, not what the viewer gets.
GENERIC = frozenset(fa.fold(w) for w in """
مقدمه معرفی شروع آغاز پایان جمع‌بندی جمعبندی نتیجه‌گیری نتیجه ادامه بخش قسمت فصل خداحافظی
خلاصه توضیحات سخن‌پایانی سوال سوالات پرسش intro introduction outro conclusion summary end start
part section chapter ending wrap wrap-up recap
""".split())
GENERIC_PHRASES = frozenset(fa.fold(p) for p in (
    "سخن پایانی", "حرف آخر", "حرف پایانی", "پرسش و پاسخ", "سوال و جواب", "wrap up", "final thoughts",
    "q&a", "بخش اول", "بخش دوم", "بخش سوم", "قسمت اول", "قسمت دوم", "قسمت سوم"))

# Spoken Persian words that say nothing about the topic (on top of fatext's stopwords).
_STOP_FA = frozenset(fa.fold(w) for w in list(fa.STOPWORDS_FA) + """
بگم بگی بگیم گفتم گفت داشته داشتم داشت باشه باشید باشن باشد بشه بشن بذار بذارید بزن بزنید کن کنی
بریم بری برید رفتیم سراغ همون همین فقط نباید اول آخر آخرش خوب خوبه بد بیشتر کمتر واقعا اصلا دقیقا
میشه نمیشه هست نیست بودن بوده میخوام میخوای ببین ببینید بیا بیاید چیز چیزا اینه اونه کنیم کنن
""".split())
_STOP_EN = fa.STOPWORDS_EN
_DIG = "0-9۰-۹٠-٩"
_TS = r"[%s]{1,2}(?::[%s]{2}){1,2}" % (_DIG, _DIG)
_LEAD = re.compile(r"^[\s(\[]*(%s)[)\]]?(?:\s*[-–—:|.)•]+\s*|\s+|$)(.*)$" % _TS)
_TRAIL = re.compile(r"^(.*?)(?:\s*[-–—:|(•]+\s*|\s+)[(\[]?(%s)[)\]]?\s*$" % _TS)
_BULLET = re.compile(r"^\s*[-–—•*▪●◦]+\s*")


def fa_num(n):
    return fa.to_fa_digits(str(n))


# ---------------------------------------------------------------- draft from a transcript

def _key(tok):
    """Comparison key for a content word, or None when it is not one."""
    f = fa.fold(tok)
    if not f or f.isdigit() or any(ch.isdigit() for ch in f):
        return None
    if re.fullmatch(r"[a-z'’\-]+", f):
        if f in _STOP_EN or fa.is_filler(f):
            return None
        if len(f) >= 4 or (tok.isupper() and len(tok) >= 2):   # keep AI, GPT, SEO
            return f
        return None
    if f in _STOP_FA or fa.is_filler(f):
        return None
    if re.match("^(?:ن?می|ن?ب)" + fa.ZWNJ, fa.normalize(tok)):     # verbs: می‌گیره، نمی‌شه
        return None
    for suf in ("های", "ها"):                      # light plural folding: ویدیوها = ویدیو
        if f.endswith(suf) and len(f) - len(suf) >= 3:
            f = f[:-len(suf)]
            break
    return f if len(f) >= 3 else None


def keywords(text):
    return {k for k in (_key(t) for t in fa.tokenize(text)) if k}


def draft_title(text):
    """Top three content words of a section, most frequent first, shown in their spoken form."""
    count, shown = {}, {}
    for t in fa.tokenize(text):
        k = _key(t)
        if not k:
            continue
        count[k] = count.get(k, 0) + 1
        forms = shown.setdefault(k, {})
        forms[t] = forms.get(t, 0) + 1
    order = sorted(count, key=lambda k: (-count[k], k))[:3]
    words = []
    for k in order:
        w = max(shown[k], key=lambda f: (shown[k][f], -len(f)))
        words.append(w.capitalize() if re.fullmatch(r"[a-z'’\-]+", w) else w)
    sep = ", " if all(re.fullmatch(r"[A-Za-z'’\-]+", w) for w in words) else "، "
    return sep.join(words) or "بخش"


def draft(cues, target, dur):
    cand = []
    for i in range(1, len(cues)):
        gap = max(0.0, cues[i].start - cues[i - 1].end)
        before = " ".join(c.text for c in cues[max(0, i - 12):i])
        after = " ".join(c.text for c in cues[i:i + 12])
        kb, ka = keywords(before), keywords(after)
        shift = 1 - (len(kb & ka) / len(kb | ka)) if (kb | ka) else 0
        cand.append((gap * 1.6 + shift * 3.2, cues[i].start, i))
    cand.sort(reverse=True)
    picked = [0.0]
    for _, t, _i in cand:
        if len(picked) >= target:
            break
        if all(abs(t - p) >= MIN_LEN for p in picked) and dur - t >= MIN_LEN:
            picked.append(t)
    picked.sort()
    chapters = []
    for n, t in enumerate(picked):
        end = picked[n + 1] if n + 1 < len(picked) else dur
        # a cue belongs to the chapter it starts in, so one crossing a boundary still counts once
        text = " ".join(c.text for c in cues if t <= c.start < end)
        title = draft_title(text)
        chapters.append({"start": round(t, 2), "label": fa.fmt_timestamp(t), "draft_title": title,
                         "seconds": round(end - t, 2)})
    return chapters


# ---------------------------------------------------------------- checking a pasted list

def parse_list(raw):
    """Lines with a timestamp at the start or the end. Other lines (the rest of a description) are skipped."""
    items = []
    for n, line in enumerate(raw.splitlines(), 1):
        s = fa.normalize(line).strip()
        s = _BULLET.sub("", s) if not re.match(r"^\s*[%s]" % _DIG, s) else s
        if not s:
            continue
        m = _LEAD.match(s)
        if m:
            ts, title = m.group(1), m.group(2)
        else:
            m = _TRAIL.match(s)
            if not m:
                continue
            title, ts = m.group(1), m.group(2)
        title = title.strip(" \t-–—:|•.")
        items.append({"line": n, "raw_ts": ts, "start": fa.parse_timestamp(ts), "title": title,
                      "fa_digits": bool(re.search(r"[۰-۹٠-٩]", ts))})
    return items


def _is_generic(title):
    f = fa.fold(title)
    f = re.sub(r"[\d\s]+$", "", f).strip()          # «بخش ۲»، «Part 3»
    if not f:
        return True
    return f in GENERIC or f in GENERIC_PHRASES


def check(items, dur):
    """Return (chapters, errors, warnings). errors break YouTube's rules; warnings are this pack's advice."""
    errors, warnings = [], []
    bad = [it for it in items if it["start"] is None]
    for it in bad:
        errors.append("خط %s: زمان «%s» خوانا نیست (ثانیه و دقیقه باید زیر ۶۰ باشند)."
                      % (fa_num(it["line"]), it["raw_ts"]))
    good = [it for it in items if it["start"] is not None]
    if not items:
        errors.append("هیچ خطی با زمان پیدا نشد. هر فصل یک خط است: «0:00 عنوان».")
        return [], errors, warnings
    if len(good) < MIN_COUNT:
        errors.append("دست‌کم ۳ فصل لازم است؛ این فهرست %s فصل دارد." % fa_num(len(good)))
    if good and good[0]["start"] != 0:
        errors.append("اولین فصل باید 0:00 باشد؛ الان %s است." % fa.fmt_timestamp(good[0]["start"]))
    chapters = []
    for i, it in enumerate(good):
        nxt = good[i + 1]["start"] if i + 1 < len(good) else None
        end = nxt if nxt is not None else dur
        secs = None if end is None else round(end - it["start"], 2)
        chapters.append({"start": it["start"], "label": fa.fmt_timestamp(it["start"]), "title": it["title"],
                         "seconds": secs, "line": it["line"]})
        label = fa.fmt_timestamp(it["start"])
        if nxt is not None and nxt <= it["start"]:
            errors.append("خط %s: زمان‌ها باید صعودی باشند؛ بعد از %s آمده %s."
                          % (fa_num(good[i + 1]["line"]), label, fa.fmt_timestamp(nxt)))
        elif nxt is not None and secs < MIN_LEN:
            errors.append("فصل %s («%s») فقط %s ثانیه است؛ هر فصل دست‌کم ۱۰ ثانیه می‌خواهد."
                          % (label, it["title"] or "بی‌عنوان", fa_num(int(secs))))
        elif nxt is None and dur is not None:
            if it["start"] >= dur:
                errors.append("فصل آخر (%s) بعد از پایان ویدیو (%s) شروع می‌شود."
                              % (label, fa.fmt_timestamp(dur)))
            elif secs < MIN_LEN:
                errors.append("فصل آخر (%s) تا پایان ویدیو فقط %s ثانیه است؛ دست‌کم ۱۰ ثانیه لازم است."
                              % (label, fa_num(int(secs))))
        t = it["title"]
        if not t:
            warnings.append("فصل %s عنوان ندارد." % label)
        else:
            if len(t) > TITLE_MAX:
                warnings.append("عنوان فصل %s %s نویسه است؛ زیر ۵۰ نگهش دار تا در موبایل کامل دیده شود."
                                % (label, fa_num(len(t))))
            if _is_generic(t):
                warnings.append("«%s» (%s) فقط می‌گوید کجای ویدیو هستیم؛ بنویس بیننده اینجا چه می‌گیرد."
                                % (t, label))
    if dur is None and good:
        warnings.append("طول ویدیو را نداده‌ای، پس طول فصل آخر بررسی نشد (--duration 12:40 یا فایل زیرنویس بده).")
    if any(it["fa_digits"] for it in items):
        warnings.append("زمان‌ها رقم فارسی داشتند؛ در بلوک زیر به رقم انگلیسی برگشتند (امن‌ترین شکل برای یوتیوب).")
    seen = {}
    for c in chapters:
        f = fa.fold(c["title"])
        if f and f in seen:
            warnings.append("عنوان «%s» دو بار آمده (%s و %s)." % (c["title"], seen[f], c["label"]))
        seen.setdefault(f, c["label"])
    return chapters, errors, warnings


# ---------------------------------------------------------------- cli

class FaParser(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write("روش اجرا:\n  %s\n\nخطا در ورودی: %s\n" % (USAGE, message))
        sys.exit(2)


def read_cues(path):
    try:
        cues = fa.load_cues(path)
    except (OSError, UnicodeDecodeError) as e:
        sys.stderr.write("فایل زیرنویس خوانده نشد: %s (%s)\n" % (path, e))
        print(__doc__)
        sys.exit(1)
    return sorted(cues, key=lambda c: (c.start, c.end))


def block(chapters, key):
    return "\n".join("%s %s" % (c["label"], c[key]) for c in chapters)


def main():
    p = FaParser(prog="chapters.py", usage=USAGE, add_help=False)
    p.add_argument("path", nargs="?")
    p.add_argument("--target", type=int, default=7)
    p.add_argument("--duration")
    p.add_argument("--check", metavar="FILE")
    p.add_argument("--json", action="store_true")
    p.add_argument("-h", "--help", action="store_true")
    args = p.parse_args()
    if args.help:
        print(__doc__)
        return 0
    if args.target < MIN_COUNT:
        p.error("مقدار --target باید دست‌کم ۳ باشد (یوتیوب دست‌کم ۳ فصل می‌خواهد).")
    dur = None
    if args.duration is not None:
        dur = fa.parse_timestamp(args.duration)
        if dur is None or dur <= 0:
            p.error("مقدار --duration خوانا نیست: «%s» (مثلاً 12:40 یا 1:02:30 یا 760)." % args.duration)

    if args.check:
        return run_check(args, dur)

    if not args.path or not os.path.isfile(args.path):
        if args.path:
            sys.stderr.write("فایل پیدا نشد: %s\n" % args.path)
        print(__doc__)
        return 1
    cues = read_cues(args.path)
    if len(cues) < 6:
        print("زیرنویس برای فصل‌بندی خیلی کوتاه است (کمتر از ۶ خط).")
        return 1
    end = fa.duration(cues)
    note = None
    if dur is not None:
        if dur < end:
            note = "طولی که دادی (%s) از پایان زیرنویس (%s) کوتاه‌تر است؛ همان را پایان ویدیو گرفتم." % (
                fa.fmt_timestamp(dur), fa.fmt_timestamp(end))
        end = dur
    chapters = draft(cues, args.target, end)
    ok = (len(chapters) >= MIN_COUNT and chapters[0]["start"] == 0
          and all(c["seconds"] >= MIN_LEN for c in chapters))
    long_titles = [c["label"] for c in chapters if len(c["draft_title"]) > TITLE_MAX]
    if args.json:
        print(json.dumps({"valid": ok, "duration": round(end, 2), "chapters": chapters},
                         ensure_ascii=False, indent=1))
        return 0
    out = ["", "پیش‌نویس فصل‌ها (عنوان‌ها فقط واژه‌های پرتکرار هر بخش‌اند؛ همه را بازنویسی کن):", ""]
    out.append(block(chapters, "draft_title"))
    out.append("")
    out.append("%s فصل، تا پایان ویدیو %s." % (fa_num(len(chapters)), fa.fmt_timestamp(end)))
    if not ok:
        out.append("نامعتبر: یوتیوب دست‌کم ۳ فصل، شروع از 0:00 و هر فصل دست‌کم ۱۰ ثانیه می‌خواهد.")
    if note:
        out.append(note)
    if long_titles:
        out.append("عنوان این فصل‌ها بیش از ۵۰ نویسه است: %s" % "، ".join(long_titles))
    out.append("هر عنوان را به شکل «چیزی که بیننده می‌گیرد» با واژه‌ای که مردم جست‌وجو می‌کنند بنویس،")
    out.append("بعد فهرست را با --check دوباره بررسی کن.")
    out.append("")
    print("\n".join(out))
    return 0


def run_check(args, dur):
    if args.check == "-":
        raw = sys.stdin.read()
    else:
        try:
            with open(args.check, encoding="utf-8-sig") as f:
                raw = f.read()
        except (OSError, UnicodeDecodeError) as e:
            sys.stderr.write("فهرست فصل‌ها خوانده نشد: %s (%s)\n" % (args.check, e))
            return 2
    if dur is None and args.path:
        if not os.path.isfile(args.path):
            sys.stderr.write("فایل زیرنویس پیدا نشد: %s\n" % args.path)
            return 2
        cues = read_cues(args.path)
        dur = fa.duration(cues) or None
    chapters, errors, warnings = check(parse_list(raw), dur)
    ok = not errors
    if args.json:
        print(json.dumps({"valid": ok, "duration": dur, "last_checked": dur is not None,
                          "chapters": chapters, "errors": errors, "warnings": warnings},
                         ensure_ascii=False, indent=1))
        return 0 if ok else 1
    out = [""]
    if ok:
        out.append("فهرست با قانون‌های یوتیوب جور است (%s فصل)." % fa_num(len(chapters)))
    else:
        out.append("این فهرست فصل نمی‌سازد؛ یوتیوب آن را نادیده می‌گیرد تا این‌ها درست شوند:")
        out += ["  - " + e for e in errors]
    if warnings:
        out.append("")
        out.append("پیشنهاد (قاعده‌ی این پک، نه یوتیوب):")
        out += ["  - " + w for w in warnings]
    if chapters:
        out.append("")
        out.append("بلوک آماده‌ی چسباندن (رقم انگلیسی):" if ok else "بلوک یکدست‌شده (بعد از اصلاح بچسبان):")
        out.append("")
        out.append(block(chapters, "title"))
    out.append("")
    print("\n".join(out))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
