#!/usr/bin/env python3
"""data/ の曲データを検証する。

一覧(data/songs.json)の taps と range は表示用のキャッシュなので、実データと
食い違ったら実データが正しい(仕様書 5 章)。このスクリプトは食い違いを見つけて
報告し、--fix でキャッシュを実データに合わせる。

曲を足したり作り直したあとに走らせる。

    python3 tools/check-songs.py
    python3 tools/check-songs.py --fix
"""

import json
import os
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
LO, HI = 48, 84            # タップ演奏データの音域(C3〜C6)
MAX_VALUES = 3             # 1イベントの最大同時発音数

NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
name_of = lambda n: NAMES[n % 12] + str(n // 12 - 1)


def main():
    fix = "--fix" in sys.argv
    index = json.load(open(os.path.join(DATA, "songs.json"), encoding="utf-8"))
    songs = index["songs"]
    problems = []
    changed = False

    seen_ids, seen_files = set(), set()
    for m in songs:
        sid = m["id"]
        if sid in seen_ids:
            problems.append("%s: id が重複している" % sid)
        seen_ids.add(sid)
        if m["file"] in seen_files:
            problems.append("%s: file が重複している" % sid)
        seen_files.add(m["file"])

        # 題名は NFC で持つ。macOS 由来の NFD 濁点が混ざると照合が崩れる
        for key in ("title", "title_en"):
            v = m.get(key)
            if v is None:
                if key == "title_en":
                    problems.append("%s: title_en が無い(英語の画面で日本語のまま出る)" % sid)
                continue
            if v != unicodedata.normalize("NFC", v):
                problems.append("%s: %s が NFC で正規化されていない" % (sid, key))

        path = os.path.join(DATA, m["file"])
        if not os.path.exists(path):
            problems.append("%s: %s が無い" % (sid, m["file"]))
            continue
        ev = json.load(open(path, encoding="utf-8"))

        if not isinstance(ev, list) or not ev:
            problems.append("%s: 素のイベント配列ではない" % sid)
            continue
        for k, e in enumerate(ev):
            if not isinstance(e, dict) or not isinstance(e.get("values"), list) or not e["values"]:
                problems.append("%s: %d番目に values が無い" % (sid, k + 1))
                break
            if len(e["values"]) > MAX_VALUES:
                problems.append("%s: %d番目が%d音(最大%d音)" % (sid, k + 1, len(e["values"]), MAX_VALUES))
                break
            v = e.get("velocity", 100)
            if not isinstance(v, int) or not 0 <= v <= 127:
                problems.append("%s: %d番目の velocity が 0〜127 でない" % (sid, k + 1))
                break

        pitches = [p for e in ev for p in e.get("values", [])]
        out = sorted({p for p in pitches if p < LO or p > HI})
        if out:
            problems.append("%s: 音域外 %s (iPad 実機では鳴らない)"
                            % (sid, " ".join(name_of(p) for p in out)))

        taps, rng = len(ev), [min(pitches), max(pitches)]
        if m.get("taps") != taps or m.get("range") != rng:
            msg = "%s: 一覧のキャッシュが実データと違う taps %s→%d range %s→%s" % (
                sid, m.get("taps"), taps, m.get("range"), rng)
            if fix:
                m["taps"], m["range"] = taps, rng
                changed = True
                print("直した: " + msg)
            else:
                problems.append(msg)

    if fix and changed:
        with open(os.path.join(DATA, "songs.json"), "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(index, ensure_ascii=False, indent=2) + "\n")

    print("%d曲 / %dタップ" % (len(songs), sum(m["taps"] for m in songs)))
    if problems:
        print("\n問題 %d件:" % len(problems))
        for p in problems:
            print("  - " + p)
        return 1
    print("問題なし")
    return 0


if __name__ == "__main__":
    sys.exit(main())
