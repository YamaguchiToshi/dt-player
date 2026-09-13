#!/usr/bin/env python3
"""icons/icon.svg から各サイズの PNG を作る。

iPadOS はホーム画面のアイコンに manifest ではなく <link rel="apple-touch-icon">
を使うので、そちら向けの寸法(152/167/180)を必ず出す。192/512 は manifest 用。

Playwright(開発用)が要る。アイコンの絵を変えたときだけ走らせる。

    python3 tools/build-icons.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "icons", "icon.svg")
OUT = os.path.join(ROOT, "icons")

# 152 iPad / 167 iPad Pro / 180 iPhone・iPad Retina / 192・512 manifest / 32 favicon
SIZES = [32, 152, 167, 180, 192, 512]


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.stderr.write("Playwright が要ります: pip install playwright && playwright install chromium\n")
        return 1

    svg = open(SRC, encoding="utf-8").read()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for size in SIZES:
            page = browser.new_page(viewport={"width": size, "height": size},
                                    device_scale_factor=1)
            page.set_content(
                '<style>html,body{margin:0;padding:0}svg{display:block;width:%dpx;height:%dpx}</style>%s'
                % (size, size, svg))
            page.wait_for_timeout(120)
            path = os.path.join(OUT, "icon-%d.png" % size)
            page.screenshot(path=path, omit_background=False)
            page.close()
            print("%-22s %5d bytes" % (os.path.relpath(path, ROOT), os.path.getsize(path)))
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
