#!/usr/bin/env python3
"""语音同步字幕揭示：字幕出现速度跟随真实语音节奏。

原理：给定短语级时间戳（文本，音频开始秒，音频结束秒），对任意时刻
计算应显示的字符数。说话时字流动，停顿时字停留。关键词在说出时
缩放弹出（0.7→1.0 + 淡入），尾部淡出。

时间戳来源：ffmpeg silencedetect 抓停顿点（不要用 Whisper，
tiny 模型中文误识别率高）：
    ffmpeg -i narration.wav -af silencedetect=noise=-35dB:d=0.25 \\
        -f null /dev/null

用法：
    python3 gen_reveal.py --config reveal.json --columns ./columns \\
        --outdir ./reveal_frames

reveal.json 格式：
    {
      "fps": 30,
      "cards": [
        {
          "name": "vsub1",
          "start": 0.4, "end": 4.54,          // 字幕在视频中的起止秒
          "right_phrases": [0],               // 右列包含的短语索引
          "left_phrases": [1],                // 左列包含的短语索引
          "keyword": "蛤", "keyword_phrase": 1, // 关键词及所在短语索引
          "phrases": [                        // 短语文本 + 音频时间戳
            ["如果emo有形状，", 0.0, 1.17],
            ["大概就是一只不想起床的蛤蟆。", 1.79, 3.72]
          ]
        }
      ]
    }
"""
import argparse
import json
import os
from safe_paths import child_path
from PIL import Image

FADE_OUT = 15       # 尾部淡出帧数
KW_POP_FRAMES = 12  # 关键词弹出时长（帧）

CARD_W = 452
CX_RIGHT, CX_LEFT = 342, 140


def load(coldir, fname):
    with Image.open(child_path(coldir, fname)) as img:
        return img.convert("RGBA")


def set_alpha(img, a):
    out = img.copy()
    r, g, b, al = out.split()
    al = al.point(lambda v: int(v * max(0.0, min(1.0, a))))
    out.putalpha(al)
    return out


def ease_out_cubic(p):
    return 1 - (1 - p) ** 3


def count_items(text):
    """数字幕条目数（ASCII run 算1个，CJK 单字算1个）。"""
    n, i = 0, 0
    while i < len(text):
        ch = text[i]
        if ord(ch) < 128 and ch not in "，。、；：？！…—《》":
            j = i
            while j < len(text) and ord(text[j]) < 128 \
                    and text[j] not in "，。、；：？！…—《》":
                j += 1
            n += 1
            i = j
        else:
            n += 1
            i += 1
    return n


def gen_card(card, coldir, kw_meta, outbase, fps):
    name = card["name"]
    phrases = [(t, s, e) for t, s, e in card["phrases"]]
    t0, t1 = card["start"], card["end"]
    kw_char = card["keyword"]
    kw_pi = card["keyword_phrase"]
    right_idx, left_idx = card["right_phrases"], card["left_phrases"]

    right = load(coldir, f"{name}_body_right.png")
    left = load(coldir, f"{name}_body_left.png")
    ch = max(right.height, left.height)
    cw = CARD_W
    total = int(round((t1 - t0) * fps))

    r_phrases = [phrases[i] for i in right_idx]
    l_phrases = [phrases[i] for i in left_idx]

    # 关键词定位
    kw_time = phrases[kw_pi][1]
    side = "right" if kw_pi in right_idx else "left"
    col = right if side == "right" else left
    cx = CX_RIGHT if side == "right" else CX_LEFT
    meta_key = f"{name}_{side}"
    kw_img, kw_xy = None, None
    if meta_key in kw_meta:
        kw_img = load(coldir, kw_meta[meta_key]["kw_file"])
        kx, ky = kw_meta[meta_key]["kw_pos"]
        col_x = int(cx - col.width / 2)
        col_y = int((ch - col.height) / 2)
        kw_xy = (int(col_x + kx), int(col_y + ky))

    r_x = int(CX_RIGHT - right.width / 2)
    r_y = int((ch - right.height) / 2)
    l_x = int(CX_LEFT - left.width / 2)
    l_y = int((ch - left.height) / 2)

    def items_of(idxs):
        out = []
        for idx in idxs:
            c = count_items(phrases[idx][0])
            if idx == kw_pi:
                c -= 1  # 关键词单独弹出，不参与擦除
            out.append(c)
        return out

    r_items, l_items = items_of(right_idx), items_of(left_idx)
    r_full = sum(count_items(phrases[i][0]) for i in right_idx)
    l_full = sum(count_items(phrases[i][0]) for i in left_idx)

    def chars_visible(col_phrases, col_items, audio_t):
        shown = 0
        for (txt, s, e), cnt in zip(col_phrases, col_items):
            if audio_t < s:
                break      # 还没说到：停住
            elif audio_t >= e:
                shown += cnt   # 说完了：全显
            else:
                shown += cnt * (audio_t - s) / max(0.001, e - s)
                break
        return shown

    outdir = child_path(outbase, name)
    os.makedirs(outdir, exist_ok=True)
    for i in range(total):
        at = i / fps  # 字幕开始即旁白开始
        frame = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        rc = chars_visible(r_phrases, r_items, at)
        if rc > 0:
            h = max(1, int(right.height * min(1.0, rc / r_full)))
            frame.alpha_composite(right.crop((0, 0, right.width, h)),
                                  (r_x, r_y))
        lc = chars_visible(l_phrases, l_items, at)
        if lc > 0:
            h = max(1, int(left.height * min(1.0, lc / l_full)))
            frame.alpha_composite(left.crop((0, 0, left.width, h)),
                                  (l_x, l_y))
        if kw_img and at >= kw_time:
            kp = min(1.0, (at - kw_time) / (KW_POP_FRAMES / fps))
            e = ease_out_cubic(kp)
            scale = 0.7 + 0.3 * e
            kw_w = max(1, int(kw_img.width * scale))
            kw_h = max(1, int(kw_img.height * scale))
            kw_s = set_alpha(kw_img.resize((kw_w, kw_h), Image.LANCZOS), e)
            kx, ky = kw_xy
            px = int(kx + (kw_img.width - kw_w) / 2)
            py = int(ky + (kw_img.height - kw_h) / 2)
            frame.alpha_composite(kw_s, (px, py))
        if i >= total - FADE_OUT:
            # 淡出用 alpha 相乘，保持透明区 alpha=0（勿整卡 putalpha）
            a = 1.0 - (i - (total - FADE_OUT)) / FADE_OUT
            frame = set_alpha(frame, max(0.0, a))
        frame.save(child_path(outdir, f"f{i:03d}.png"))
    print(f"{name}: {total}f done")


def main():
    ap = argparse.ArgumentParser(description="语音同步字幕逐帧生成")
    ap.add_argument("--config", required=True, help="reveal.json（见模块 docstring）")
    ap.add_argument("--columns", required=True, help="render_columns.py 输出目录")
    ap.add_argument("--outdir", required=True, help="逐帧 PNG 输出目录")
    a = ap.parse_args()
    with open(a.config, encoding="utf-8") as f:
        cfg = json.load(f)
    fps = cfg.get("fps", 30)
    with open(child_path(a.columns, "kw_meta.json"), encoding="utf-8") as f:
        kw_meta = json.load(f)
    os.makedirs(a.outdir, exist_ok=True)
    for card in cfg["cards"]:
        gen_card(card, a.columns, kw_meta, a.outdir, fps)
    print("done")


if __name__ == "__main__":
    main()
