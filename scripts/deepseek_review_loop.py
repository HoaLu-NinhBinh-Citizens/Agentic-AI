#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
DeepSeek Review - DON GIAN

Usage:
    python deepseek_review_loop.py phase_1a.md
"""

import io, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright
import httpx

def main():
    import argparse
    from pathlib import Path

    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--port", "-p", default=9222)
    ap.add_argument("--wait", "-w", type=int, default=40)
    ap.add_argument("--output", "-o")
    args = ap.parse_args()

    # Load prompt
    fp = Path("prompts") / args.file
    if not fp.exists():
        fp = Path(args.file)
    prompt = fp.read_text(encoding="utf-8")
    print(f"File: {fp.name} ({len(prompt)} chars)")

    # Connect Chrome
    pw = sync_playwright().start()
    browser = None
    page = None

    try:
        r = httpx.get(f"http://localhost:{args.port}/json/version", timeout=3)
        ws = r.json()["webSocketDebuggerUrl"]
        print("Ket noi Chrome...")
        browser = pw.chromium.connect_over_cdp(ws)

        # Tim tab DeepSeek
        for ctx in browser.contexts:
            for p in ctx.pages:
                if "deepseek" in p.url.lower():
                    page = p
                    print("Tim thay tab DeepSeek")
                    break
        if page:
            page.bring_to_front()
    except Exception as e:
        print(f"Loi ket noi: {e}")
        print("Dang mo Chrome moi...")
        browser = pw.chromium.launch(headless=False)
        page = browser.new_page()

    if not page:
        page = browser.new_page()

    # Mo DeepSeek
    print("Mo DeepSeek...")
    page.goto("https://chat.deepseek.com/")

    # Doi load
    print("Doi load trang...")
    time.sleep(6)

    # Gui prompt
    print("Gui prompt...")
    try:
        page.locator("textarea").first.fill(prompt)
        time.sleep(0.5)
        page.keyboard.press("Enter")
    except Exception as e:
        print(f"Loi gui: {e}")
        browser.close()
        pw.stop()
        return

    print(f"Cho {args.wait}s...")
    time.sleep(args.wait)

    # Lay ket qua
    try:
        body = page.locator("body").inner_text()
        lines = body.split("\n")
        result = "\n".join(lines[-60:])

        print("\n" + "="*50)
        print("KET QUA:")
        print("="*50)
        print(result)
        print("="*50)

        if args.output:
            Path(args.output).write_text(result, encoding="utf-8")
            print(f"Luu: {args.output}")
    except Exception as e:
        print(f"Loi lay ket qua: {e}")

    input("An Enter de dong...")
    browser.close()
    pw.stop()

if __name__ == "__main__":
    main()
