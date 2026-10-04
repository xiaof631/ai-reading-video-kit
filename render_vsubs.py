#!/usr/bin/env python3
"""竖排字幕卡渲染：
   - 正文竖排（思源宋体 Regular），白色 + 1px 黑描边
   - 关键词单字放大（马善政毛笔体，朱砂红 #D9381E）
   - ASCII 跑纵中横，书名号等旋转 90 度
   - CJK 标点做竖排右上偏移

用法：
    python3 render_vsubs.py --config cards.json --outdir ./cards \\
        --serif /path/to/NotoSerifCJK-Regular.ttc \\
        --brush /path/to/MaShanZheng-Regular.ttf

cards.json 格式：
    [
      {"file": "vsub1.png", "right": "右列文本", "left": "左列文本", "keyword": "关"},
      ...
    ]
"""
import argparse
import json
import os
from safe_paths import child_path
from PIL import Image, ImageDraw, ImageFont

BODY = 40          # 正文px
KW = 110           # 关键词px
KW_COLOR = "#D9381E"  # 朱砂红
ASCII_SIZE = 30
COL_GAP = 92
PAD = 40

ROTATE_CHARS = set("《》〈〉「」『』（）")


def make_fonts(serif_path, brush_path, serif_index=2):
    return {
        "body": ImageFont.truetype(serif_path, BODY, index=serif_index),
        "kw": ImageFont.truetype(brush_path, KW),
        "ascii": ImageFont.truetype(serif_path, ASCII_SIZE, index=serif_index),
    }


def char_advance(ch, is_kw):
    return int(KW * 1.02) if is_kw else BODY


def draw_column(base_img, cx, y_top, text, keyword, fonts, skip_kw=False):
    """在 base_img 上以 (cx, y_top) 为列中心/顶端竖排绘制。
    返回 (列高, 关键词包围盒或None)。关键词仅首次出现放大。"""
    d = ImageDraw.Draw(base_img)
    font_body, font_kw, font_ascii = fonts["body"], fonts["kw"], fonts["ascii"]
    y = y_top
    i = 0
    kw_done = False
    kw_info = None
    while i < len(text):
        ch = text[i]
        # ASCII 纵中横
        if ord(ch) < 128 and ch not in "，。、；：？！…—":
            j = i
            while j < len(text) and ord(text[j]) < 128 \
                    and text[j] not in "，。、；：？！…—":
                j += 1
            run = text[i:j]
            cy = y + BODY / 2
            d.text((cx, cy), run, font=font_ascii, anchor="mm", fill="white",
                   stroke_width=1, stroke_fill=(0, 0, 0, 220))
            y += BODY
            i = j
            continue
        is_kw = (ch == keyword and not kw_done)
        if is_kw:
            kw_done = True
        f = font_kw if is_kw else font_body
        fill = KW_COLOR if is_kw else "white"
        adv = char_advance(ch, is_kw)
        cy = y + adv / 2
        px, py = cx, cy
        if ch in "，。、；：？！…—" and not is_kw:
            px, py = cx + BODY * 0.20, cy - BODY * 0.20  # 竖排标点右上偏移
        if is_kw and skip_kw:
            kw_info = (cx, y, adv, adv)
            y += adv
            i += 1
            continue
        if ch in ROTATE_CHARS:
            tmp = Image.new("RGBA", (BODY + 20, BODY + 20), (0, 0, 0, 0))
            td = ImageDraw.Draw(tmp)
            td.text((tmp.width / 2, tmp.height / 2), ch, font=font_body,
                    anchor="mm", fill="white",
                    stroke_width=1, stroke_fill=(0, 0, 0, 220))
            rot = tmp.rotate(-90, expand=True, resample=Image.BICUBIC)
            base_img.alpha_composite(
                rot, (int(px - rot.width / 2), int(py - rot.height / 2)))
        else:
            if is_kw:
                d.text((px, py), ch, font=f, anchor="mm", fill=fill)
            else:
                d.text((px, py), ch, font=f, anchor="mm", fill=fill,
                       stroke_width=1, stroke_fill=(0, 0, 0, 220))
        y += adv
        i += 1
    return (y - y_top), kw_info


def measure_column(text, keyword):
    h, i, kw_done = 0, 0, False
    while i < len(text):
        ch = text[i]
        if ord(ch) < 128 and ch not in "，。、；：？！…—":
            j = i
            while j < len(text) and ord(text[j]) < 128 \
                    and text[j] not in "，。、；：？！…—":
                j += 1
            h += BODY
            i = j
            continue
        is_kw = (ch == keyword and not kw_done)
        if is_kw:
            kw_done = True
        h += char_advance(ch, is_kw)
        i += 1
    return h


def render_card(right, left, keyword, fonts):
    hr = measure_column(right, keyword)
    hl = measure_column(left, keyword)
    H = int(max(hr, hl)) + PAD * 2
    col_w = KW + 30
    W = int(col_w * 2 + COL_GAP) + PAD * 2
    cx_right = W - PAD - col_w / 2
    cx_left = cx_right - col_w - COL_GAP + 30
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_column(img, cx_right, (H - hr) / 2, right, keyword, fonts)
    draw_column(img, cx_left, (H - hl) / 2, left, keyword, fonts)
    return img


def main():
    ap = argparse.ArgumentParser(description="竖排双栏字幕卡渲染")
    ap.add_argument("--config", required=True, help="字幕卡 JSON（见模块 docstring）")
    ap.add_argument("--outdir", required=True, help="输出目录")
    ap.add_argument("--serif", required=True, help="思源宋体 Regular ttc 路径")
    ap.add_argument("--brush", required=True, help="马善政毛笔体 ttf 路径")
    ap.add_argument("--serif-index", type=int, default=2,
                    help="NotoSerifCJK.ttc 中简体中文的 index（默认 2）")
    a = ap.parse_args()
    fonts = make_fonts(a.serif, a.brush, a.serif_index)
    os.makedirs(a.outdir, exist_ok=True)
    with open(a.config, encoding="utf-8") as f:
        cards = json.load(f)
    for c in cards:
        img = render_card(c["right"], c["left"], c["keyword"], fonts)
        fp = child_path(a.outdir, c["file"])
        img.save(fp)
        print(f"{fp}: {img.width}x{img.height}")


if __name__ == "__main__":
    main()
