#!/usr/bin/env python3
"""sf/*.js を作り直すスクリプト。

WebAudioFont の音色データ(MIT)から、dt-player が必要とする範囲だけを抜き出して
sf/ に書き出す。プレイヤー側のコード(GPL-3.0)は取り込まない。再生は index.html
内の SoundFont エンジンが自前でおこなう。

削減の方針は仕様書 6 章「第3段階」に従う。
  - タップ演奏データの音域は MIDI 48〜84 なので、その外のゾーンは落とす
  - 残ったゾーンを 2〜3 半音ごとに間引き、中間の音は playbackRate でずらす

    python3 tools/build-sf.py
"""

import base64
import json
import os
import re
import sys
import urllib.request

# 取得元をコミットに固定する。上流が変わっても同じ出力が得られるようにするため。
COMMIT = "23ca907d4370a04fd89ca483a92915e4d6159ab9"
BASE = "https://raw.githubusercontent.com/surikov/webaudiofontdata/" + COMMIT + "/sound/"

LO, HI = 48, 84  # タップ演奏データの音域(C3〜C6)

# id, 元ファイル, 表示名, 間引きの最小間隔(半音), 減衰音かどうか
INSTRUMENTS = [
    ("organ",   "0190_FluidR3_GM_sf2_file.js", "Church Organ",      3, False),
    ("piano",   "0000_FluidR3_GM_sf2_file.js", "Acoustic Grand",    3, True),
    ("strings", "0480_FluidR3_GM_sf2_file.js", "String Ensemble 1", 3, False),
]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "sf")
CACHE = os.path.join(ROOT, ".sfcache")

ZONE_RE = re.compile(r"\{([^{}]*)\}", re.S)
NUM_RE = re.compile(r"(\w+)\s*:\s*(-?[\d.]+)")
FILE_RE = re.compile(r"file\s*:\s*'([^']*)'")
NAME_RE = re.compile(r"//_tone\.(\S+)")


def fetch(name):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if not os.path.exists(path):
        sys.stderr.write("取得 " + name + " ... ")
        sys.stderr.flush()
        with urllib.request.urlopen(BASE + name, timeout=120) as r:
            data = r.read()
        with open(path, "wb") as f:
            f.write(data)
        sys.stderr.write("%d KB\n" % (len(data) // 1024))
    with open(path, encoding="utf-8") as f:
        return f.read()


def parse(src):
    """WebAudioFont の JS からゾーンを取り出す。

    base64 に波括弧は現れないので、波括弧で切り分けて問題ない。
    """
    zones = []
    for m in ZONE_RE.finditer(src[src.index("zones:["):]):
        body = m.group(1)
        blob = FILE_RE.search(body)
        if not blob:
            continue
        z = {k: (float(v) if "." in v else int(v)) for k, v in NUM_RE.findall(FILE_RE.sub("", body))}
        z["file"] = blob.group(1)
        nm = NAME_RE.search(body)
        z["sample"] = nm.group(1) if nm else ""
        zones.append(z)
    return zones


def pitch(z):
    """このゾーンの実際の基準音高(MIDI)。coarseTune / fineTune を織り込む。"""
    return (z["originalPitch"] - 100 * z.get("coarseTune", 0) - z.get("fineTune", 0)) / 100.0


def select(zones, min_step):
    """音域内のゾーンを残し、min_step 半音ごとに間引く。

    再生時は「基準音高が最も近いゾーン」を選ぶので、間引いて keyRange に
    すき間ができても音が抜けることはない。
    """
    keep = [z for z in zones if not (z["keyRangeHigh"] < LO or z["keyRangeLow"] > HI)]
    keep.sort(key=pitch)
    out = []
    for z in keep:
        if not out or pitch(z) - pitch(out[-1]) >= min_step:
            out.append(z)
    # 音域の上端が遠くなりすぎないよう、最後のゾーンは残す
    if keep and out[-1] is not keep[-1] and pitch(keep[-1]) - pitch(out[-1]) >= min_step / 2.0:
        out.append(keep[-1])
    return out


def emit(inst_id, label, source, decay, zones):
    payload = {
        "label": label,
        "source": source,
        "decay": decay,
        "zones": [
            {
                "pitch": round(pitch(z), 4),          # 基準音高(MIDI、小数)
                "loopStart": z["loopStart"] / float(z["sampleRate"]),  # 秒
                "loopEnd": z["loopEnd"] / float(z["sampleRate"]),      # 秒
                "looped": z["loopEnd"] > z["loopStart"],
                "file": z["file"],
            }
            for z in zones
        ],
    }
    head = (
        "/* dt-player 用に切り出した音色データ。tools/build-sf.py が生成する。手で編集しない。\n"
        "   元データ: WebAudioFont " + source + " (MIT, Srgy Surkv)\n"
        "   元音源:   FluidR3 GM (MIT, Copyright (c) 2000-2002, 2008 Frank Wen)\n"
        "   条件と帰属表示は sf/LICENSE を参照。 */\n"
    )
    body = "DTSF.add(" + json.dumps(inst_id) + "," + json.dumps(payload, separators=(",", ":")) + ");\n"
    path = os.path.join(OUT, inst_id + ".js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + body)
    return path, len(head) + len(body)


def main():
    os.makedirs(OUT, exist_ok=True)
    total = 0
    for inst_id, fname, label, step, decay in INSTRUMENTS:
        zones = parse(fetch(fname))
        picked = select(zones, step)
        path, size = emit(inst_id, label, fname.replace("_sf2_file.js", ""), decay, picked)
        raw = sum(len(z["file"]) for z in zones) * 3 // 4
        kept = sum(len(z["file"]) for z in picked) * 3 // 4
        print("%-8s %2d/%2d ゾーン  音声 %4dKB -> %4dKB  出力 %s (%d KB)"
              % (inst_id, len(picked), len(zones), raw // 1024, kept // 1024,
                 os.path.relpath(path, ROOT), size // 1024))
        print("         音高 " + " ".join("%.0f" % z["pitch"] for z in
              [{"pitch": pitch(z)} for z in picked]))
        total += size
    print("合計 %d KB" % (total // 1024))


if __name__ == "__main__":
    main()
