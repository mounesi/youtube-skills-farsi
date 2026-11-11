#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_lib.py - کپی lib/fatext.py در پوشه‌ی هر مهارت با نام _fatext.py

    python3 -I scripts/sync_lib.py           # کپی‌ها را به‌روز می‌کند
    python3 -I scripts/sync_lib.py --check   # فقط بررسی؛ اگر کپی‌ای نبود یا فرق داشت، خروجی ۱

هر مهارت باید جدا هم کار کند (کاربر ممکن است فقط یک پوشه را در ~/.claude/skills/ کپی کند)،
پس ابزارها از پوشه‌ی مهارت دیگر import نمی‌کنند و هر کدام کپی خودشان را دارند.
کپی‌ها را دستی ویرایش نکنید: lib/fatext.py را عوض کنید و این را اجرا کنید.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "lib", "fatext.py")
SKILLS = os.path.join(ROOT, "skills")
COPY_NAME = "_fatext.py"

# skills that get a copy even before they have a tool of their own
LISTED = ("yt-script", "yt-package", "yt-edit", "yt-chapters", "yt-retention", "yt-viral",
          "yt-reel", "yt-results", "yt-subtitle", "yt-seo")


def has_tool(folder):
    try:
        names = os.listdir(folder)
    except OSError:
        return False
    return any(n.endswith(".py") and n != COPY_NAME and not n.startswith("test_") for n in names)


def targets():
    """پوشه‌هایی که باید _fatext.py داشته باشند (مرتب)."""
    out = set(LISTED)
    if os.path.isdir(SKILLS):
        for name in os.listdir(SKILLS):
            if has_tool(os.path.join(SKILLS, name)):
                out.add(name)
    return sorted(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="کپی lib/fatext.py در پوشه‌ی هر مهارت با نام _fatext.py")
    ap.add_argument("--check", action="store_true", help="فقط بررسی کن؛ چیزی ننویس")
    args = ap.parse_args(argv)
    with open(LIB, "rb") as fh:
        src = fh.read()
    bad, done = [], []
    for name in targets():
        folder = os.path.join(SKILLS, name)
        dst = os.path.join(folder, COPY_NAME)
        cur = None
        if os.path.exists(dst):
            with open(dst, "rb") as fh:
                cur = fh.read()
        if cur == src:
            continue
        if args.check:
            bad.append("%s/%s %s" % (name, COPY_NAME, "وجود ندارد" if cur is None else "با lib/fatext.py فرق دارد"))
            continue
        os.makedirs(folder, exist_ok=True)
        with open(dst, "wb") as fh:
            fh.write(src)
        done.append(name)
    if args.check:
        if bad:
            print("کپی‌های _fatext.py به‌روز نیستند:")
            for b in bad:
                print("  - " + b)
            print("برای درست کردن: python3 -I scripts/sync_lib.py")
            return 1
        print("همه‌ی کپی‌های _fatext.py با lib/fatext.py یکی‌اند (%s پوشه)." % str(len(targets())).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")))
        return 0
    if done:
        print("به‌روز شد: " + "، ".join(done))
    else:
        print("همه‌ی کپی‌ها از قبل به‌روز بودند.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
