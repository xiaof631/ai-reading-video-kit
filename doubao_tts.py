#!/usr/bin/env python3
"""豆包语音合成（火山引擎大模型 TTS v3 单向流式）。

API: POST https://openspeech.bytedance.com/api/v3/tts/unidirectional
鉴权: Header X-Api-Key（仅从环境变量 DOUBAO_API_KEY 读取）
返回: chunked JSON，每片含 base64 PCM，解码拼接后写 WAV。

情绪控制：--emotion 传入自然语言指令，经 additions.context_texts 下发。
语速：speech_rate = (speed-1)*100，区间 [-50, 100]。

示例：
    # 先通过安全提示设置 DOUBAO_API_KEY，见 README
    python3 doubao_tts.py --text "你好，世界" --out hello.wav \\
        --speaker zh_female_xinlingjitang_uranus_bigtts \\
        --emotion "用温柔治愈的语气说" --speed 1.25
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error
import wave

API_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Do not forward the API key to a redirected destination."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _extract_audio(obj):
    """从 JSON chunk 里抠 base64 音频，字段名兼容多种可能。"""
    if isinstance(obj, dict):
        for key in ("data", "audio", "audio_data", "payload"):
            v = obj.get(key)
            if isinstance(v, str) and len(v) > 100:
                return v
        for key in ("result", "response"):
            v = obj.get(key)
            if isinstance(v, dict):
                r = _extract_audio(v)
                if r:
                    return r
    return None


def synth(text, out, api_key, speaker,
          resource_id="seed-tts-2.0", sample_rate=24000,
          speed=1.0, emotion=None, uid="tts-client"):
    speech_rate = int(round((speed - 1.0) * 100))
    speech_rate = max(-50, min(100, speech_rate))

    req_params = {
        "text": text,
        "speaker": speaker,
        "audio_params": {
            "format": "pcm",
            "sample_rate": sample_rate,
        },
    }
    if speech_rate != 0:
        req_params["audio_params"]["speech_rate"] = speech_rate
    if emotion:
        # additions 必须是 JSON 字符串，不能传对象！
        req_params["additions"] = json.dumps(
            {"context_texts": [emotion]}, ensure_ascii=False)

    body = json.dumps(
        {"user": {"uid": uid}, "req_params": req_params},
        ensure_ascii=False,
    ).encode("utf-8")

    last_err = None
    pcm_chunks = []
    for attempt in range(3):
        # 每次重试新建 Request 对象（复用会导致断连）
        req = urllib.request.Request(
            API_URL, data=body, method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": api_key,
                "X-Api-Resource-Id": resource_id,
                "User-Agent": "doubao-tts/1.0",
            },
        )
        try:
            with urllib.request.build_opener(NoRedirect()).open(req, timeout=120) as r:
                raw = r.read()
                pcm_chunks = []
                for line in raw.decode("utf-8", "replace").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("data:"):  # SSE 风格前缀
                        line = line[5:].strip()
                    if not line or line in ("[DONE]",):
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(obj, dict) and obj.get("code", 0) != 0 \
                            and "data" not in obj:
                        last_err = "API 返回错误状态（未输出服务端响应，避免泄露敏感信息）"
                        pcm_chunks = []
                        break
                    b64 = _extract_audio(obj)
                    if b64:
                        pcm_chunks.append(base64.b64decode(b64))
                if pcm_chunks:
                    break
                if not last_err:
                    last_err = "未解析到音频数据（未输出服务端响应）"
        except urllib.error.HTTPError as e:
            e.close()
            sys.exit(f"HTTP {e.code}：请求失败，请检查凭据和资源配置；未输出响应正文")
        except Exception as e:
            last_err = type(e).__name__
        time.sleep(2 * (attempt + 1))

    if not pcm_chunks:
        sys.exit(f"TTS 请求失败: {last_err}")

    pcm = b"".join(pcm_chunks)
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    print(f"OK {out} ({len(pcm)} bytes pcm)")


def main():
    ap = argparse.ArgumentParser(description="豆包大模型 TTS（支持自然语言情绪指令）")
    ap.add_argument("--text", required=True, help="合成文本")
    ap.add_argument("--out", required=True, help="输出 wav 路径")
    ap.add_argument("--speaker", default="zh_female_xinlingjitang_uranus_bigtts",
                    help="音色 ID")
    ap.add_argument("--resource-id", default="seed-tts-2.0",
                    help="资源 ID（须与音色后缀匹配，如 *_uranus_bigtts → seed-tts-2.0）")
    ap.add_argument("--speed", type=float, default=1.0, help="语速倍率，如 1.25")
    ap.add_argument("--emotion", default="",
                    help="自然语言情绪指令，如“用温柔治愈的语气说”")
    ap.add_argument("--uid", default="tts-client")
    a = ap.parse_args()
    api_key = os.environ.get("DOUBAO_API_KEY", "").strip()
    if not api_key:
        sys.exit("缺少 API Key：请设置环境变量 DOUBAO_API_KEY\n"
                 "Key 在火山引擎控制台 → 大模型语音合成 → API Key 管理中获取")
    synth(a.text, a.out, api_key, a.speaker, a.resource_id,
          speed=a.speed, emotion=a.emotion or None, uid=a.uid)


if __name__ == "__main__":
    main()
