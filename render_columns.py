#!/usr/bin/env python3
"""把 render_vsubs.py 的字幕卡拆成可动画图层：
   - {base}_body_{right,left}.png：正文列（关键词位置留空）
   - {base}_body_{side}_kw.png：关键词单字（毛笔朱砂红）
   - kw_meta.json：关键词在正文列中的位置（供 gen_reveal.py 用）

用法：
    python3 render_columns.py --config cards.json --outdir ./columns \\
        --serif /path/to/NotoSerifCJK-Regular.ttc \\
        --brush /path/to/MaShanZheng-Regular.ttf
"""
import argparse
import json
import os
import sys
from safe_paths import child_path
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_vsubs import (make_fonts, draw_column, measure_column,
                          BODY, KW, PAD, COL_GAP, KW_COLOR)


def render_body_and_kw(text, keyword, fonts, outdir, base, side):
    h = measure_column(text, keyword)
    col_w = KW + 30
    W = int(col_w) + PAD
    H = int(h) + PAD * 2
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    _, kw_info = draw_column(img, W / 2, PAD, text, keyword, fonts,
                             skip_kw=True)
    body_fp = child_path(outdir, f"{base}_body_{side}.png")
    img.save(body_fp)

    kw_fp, kw_pos = None, None
    if kw_info:
        cx, y_top, w, h = kw_info
        kw_size = int(w) + 20
        kw_img = Image.new("RGBA", (kw_size, kw_size), (0, 0, 0, 0))
        d = ImageDraw.Draw(kw_img)
        d.text((kw_size / 2, kw_size / 2), keyword,
               font=fonts["kw"], anchor="mm", fill=KW_COLOR)
        kw_fp = child_path(outdir, f"{base}_body_{side}_kw.png")
        kw_img.save(kw_fp)
        kw_pos = [W / 2 - kw_size / 2, y_top + (h - kw_size) / 2]
    return body_fp, kw_fp, kw_pos


def main():
    ap = argparse.ArgumentParser(description="字幕卡图层分离")
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--serif", required=True)
    ap.add_argument("--brush", required=True)
    ap.add_argument("--serif-index", type=int, default=2)
    a = ap.parse_args()
    fonts = make_fonts(a.serif, a.brush, a.serif_index)
    os.makedirs(a.outdir, exist_ok=True)
    with open(a.config, encoding="utf-8") as f:
        cards = json.load(f)
    meta = {}
    for c in cards:
        base = c["file"].replace(".png", "")
        for side, text in (("right", c["right"]), ("left", c["left"])):
            bfp, kfp, kpos = render_body_and_kw(
                text, c["keyword"], fonts, a.outdir, base, side)
            print(f"{base}_{side}: body={os.path.basename(bfp)}, "
                  f"kw={os.path.basename(kfp) if kfp else None}")
            if kfp:
                meta[f"{base}_{side}"] = {
                    "kw_file": os.path.basename(kfp),
                    "kw_pos": kpos,
                }
    with open(child_path(a.outdir, "kw_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print("kw_meta.json saved")


if __name__ == "__main__":
    main()
