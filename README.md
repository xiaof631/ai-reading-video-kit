# AI Reading Video Kit · 语音同步字幕工具链

让 AI 读书视频"有呼吸"的核心脚本：豆包 TTS 情绪配音 + 语音节奏驱动的竖排字幕。

完整技术文章：《让 AI 读书视频"有呼吸"》

## 管线

```
旁白文本
  → doubao_tts.py            # 豆包 TTS：自然语言情绪指令配音
  → silencedetect            # ffmpeg 抓停顿点，得短语时间戳
  → render_vsubs.py          # 渲染竖排双栏字幕卡（正文+毛笔关键词）
  → render_columns.py        # 拆成动画图层（正文列 / 关键词单字）
  → gen_reveal.py            # 按语音节奏逐帧揭示 + 关键词弹出
  → ffmpeg overlay           # 烧录进视频（见 assemble_filter.txt）
```

## 安装

需要 Python 3.10+，以及可在命令行运行的 ffmpeg。建议使用虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

需要字体：
- 思源宋体 Regular（`NotoSerifCJK-Regular.ttc`）
- 马善政毛笔体（`MaShanZheng-Regular.ttf`）

字体、音视频和书籍原文不随仓库分发；请自行获取，并遵守各素材的许可。

## 快速开始

```bash
# 1. 配音（Key 在火山引擎控制台 → 大模型语音合成 获取）
# 隐藏输入，避免将真实 Key 写进脚本或 shell 历史（bash / zsh）
export DOUBAO_API_KEY="$(python3 -c 'import getpass; print(getpass.getpass("DOUBAO_API_KEY: "))')"
python3 doubao_tts.py --text "心里早就有了答案" --out s1.wav \
    --speaker zh_female_xinlingjitang_uranus_bigtts \
    --emotion "用深沉温柔的语气，金句处放慢加重" --speed 1.25
unset DOUBAO_API_KEY

# 2. 抓停顿点（得短语时间戳，填进 reveal.json）
ffmpeg -i s1.wav -af silencedetect=noise=-35dB:d=0.25 -f null /dev/null

# 3. 渲染字幕卡
python3 render_vsubs.py --config examples/cards.json --outdir ./cards \
    --serif /path/to/NotoSerifCJK-Regular.ttc \
    --brush /path/to/MaShanZheng-Regular.ttf

# 4. 拆图层
python3 render_columns.py --config examples/cards.json --outdir ./columns \
    --serif /path/to/NotoSerifCJK-Regular.ttc \
    --brush /path/to/MaShanZheng-Regular.ttf

# 5. 生成逐帧
python3 gen_reveal.py --config examples/reveal.json \
    --columns ./columns --outdir ./reveal_frames

# 6. 烧录（见 examples/assemble_filter.txt）
```

示例的 `cards.json` 与 `reveal.json` 演示两张字幕卡；上面的单句配音仅演示 API 调用，不与示例时间戳对应。实际使用需将旁白文本、字幕文本和时间戳换成同一段素材。`start` / `end` 是字幕在成片中的时间，`phrases` 是该段旁白开始后的相对秒数。

本项目是文章配套的核心脚本，不包含自动对齐器或完整视频生产系统。停顿检测结果需整理成短语时间戳；关键词弹出目前按所在短语的开始时间触发，不是词级强制对齐。帧序列会占用磁盘，建议先用短片段检查效果。

## 数据与凭据

- 只有 `doubao_tts.py` 联网：向代码内固定的豆包 HTTPS 接口发送待合成文本、情绪指令、音色配置和 API Key，可能产生 API 费用。
- API Key 只从 `DOUBAO_API_KEY` 环境变量读取，CLI 不接受 `--api-key`；请求拒绝重定向，避免鉴权头被转发到其他地址。
- 错误输出不打印服务端响应正文或异常详情。不要把真实密钥、私人文本、音视频、日志或 `.env` 提交到仓库。
- 其余脚本只进行本地读写，不执行配置中的命令。配置文件名限制为单个名称，并拒绝符号链接；配置与工作目录仍应来自可信来源，不是处理恶意输入的隔离沙箱。
- 输出会覆盖同名结果，先选择专用输出目录。使用前自行确认文件大小、帧数和时间戳合理。

## 离线测试

```bash
python3 -m unittest discover -s tests -v
```

测试模拟 TTS 响应，不使用真实密钥、不发送合成请求。测试覆盖凭据转发限制、错误信息脱敏、配置路径约束及 PCM/WAV 输出。

## 文件说明

| 文件 | 作用 |
|---|---|
| `doubao_tts.py` | 豆包 v3 TTS：chunked JSON 解析、情绪指令、语速控制 |
| `render_vsubs.py` | 竖排双栏字幕卡渲染（白字描边 + 毛笔朱砂红关键词） |
| `render_columns.py` | 图层分离：正文列 / 关键词单字 + `kw_meta.json` |
| `gen_reveal.py` | 语音节奏驱动的逐帧揭示 |
| `examples/` | 示例配置 + ffmpeg 组装 filter 模板 |

## 关键教训

- 豆包返回的是 chunked JSON（base64 PCM），不是 mp3
- `additions` 必须是 JSON 字符串，不能传对象
- 语速参数叫 `speech_rate`（`(speed-1)*100`），没有 `speed_ratio`
- 音色须与 resource ID 匹配：`*_uranus_bigtts` → `seed-tts-2.0`
- 时间轴以 `silencedetect` 为准，别信 Whisper tiny 的中文识别
- 字幕淡出用 alpha 相乘，保持透明区 alpha=0（勿整卡 `putalpha`）
- 峰值电平正常 ≠ 人耳可听，音频以人耳验收为准

## License

MIT
