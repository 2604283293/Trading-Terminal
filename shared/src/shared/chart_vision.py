"""K线图截图识别 — 使用阿里云百炼 Qwen-VL 将图表形态映射为选股条件。

Endpoint: DashScope 兼容模式 (OpenAI-compatible)
API Key: 从 DASHSCOPE_API_KEY 环境变量读取
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

import httpx

DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 系统提示词 — 告诉模型如何分析 K 线图并输出结构化条件
SYSTEM_PROMPT = """You are a professional A-share stock chart analyst. A user will give you a screenshot of a candlestick (K-line) chart. Your job:

1. Read the chart: identify price action, moving averages (MA5/MA10/MA20/MA60 if visible), volume bars, and any visible technical patterns.
2. Translate what you see into quantifiable screening conditions from the list below.

Available condition types and their parameters:
- daily_change: {"min_pct": float, "max_pct": float} — today's price change %. Range -10~10.
- n_day_change: {"days": int, "min_pct": float} — cumulative N-day change %.
- volume_ratio: {"days": int, "min_ratio": float} — today's volume / N-day avg volume. Common: days=5, min_ratio=1.5~3.0.
- consecutive_days: {"min_days": int, "direction": "阳线"|"阴线"} — consecutive bullish/bearish candles.
- price_range: {"min_price": float, "max_price": float} — price range in RMB. Common: 5~200.
- n_day_high: {"days": int} — today's close breaks N-day high. Common: 20, 60, 120.
- n_day_low: {"days": int} — today's close breaks N-day low.
- avg_volume: {"days": int, "min_amount": float} — N-day avg turnover in RMB. Common: days=5, min_amount=5e7.
- ma_cross: {"short": int, "long": int, "direction": "up"|"down"} — MA crossover. Common: short=5, long=20.
- gap: {"direction": "up"|"down", "min_pct": float} — price gap. Common: min_pct=1.0.
- engulfing: {"direction": "bullish"|"bearish"} — candlestick engulfing pattern.
- ma5_pullback: {"trend_days": int, "clean_days": int, "near_pct": float} — first pullback to MA5 in uptrend. Common: trend_days=5, clean_days=2, near_pct=2.0.

Rules:
- Only output conditions you can actually see evidence for in the chart.
- Always include a price_range condition (default min_price=5, max_price=200) unless the chart shows extreme prices.
- Be conservative with parameters — don't make them too narrow unless the chart clearly shows it.
- For volume-related conditions, estimate from the volume bars if visible.
- If you see MA lines and price crossing them, use ma_cross or ma5_pullback.

Respond with ONLY a valid JSON object (no markdown, no extra text):
{
  "description": "Brief Chinese description of the identified chart pattern.",
  "conditions": [
    {"type": "condition_name", "params": {"param_name": value, ...}},
    ...
  ]
}"""


def analyze_chart_image(
    image_bytes: bytes,
    api_key: str | None = None,
    model: str = "qwen3-vl-plus",
) -> dict[str, Any]:
    """分析 K 线图截图，返回筛选条件。

    Args:
        image_bytes: PNG/JPEG 图片字节数据
        api_key: 阿里云百炼 API Key。默认从 DASHSCOPE_API_KEY 环境变量读取。
        model: 模型名。qwen-vl-max (最强) / qwen-vl-plus (经济)。

    Returns:
        {"success": True, "description": "...", "conditions": [...], "usage": {...}}
        或 {"success": False, "error": "..."}
    """
    key = api_key or os.environ.get("DASHSCOPE_API_KEY", "")
    if not key:
        return {"success": False, "error": "未设置 DASHSCOPE_API_KEY 环境变量，且未传入 api_key"}

    media_type = _guess_media_type(image_bytes)
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{media_type};base64,{b64}"

    payload = {
        "model": model,
        "max_tokens": 1024,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    },
                    {
                        "type": "text",
                        "text": "请分析这张K线图截图，识别其中的技术形态，并输出对应的选股筛选条件JSON。",
                    },
                ],
            },
        ],
    }

    try:
        with httpx.Client(timeout=httpx.Timeout(30.0, read=120.0)) as cli:
            r = cli.post(
                f"{DASHSCOPE_BASE}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
            )
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] if exc.response is not None else str(exc)
        return {"success": False, "error": f"API HTTP {exc.response.status_code if exc.response else ''}: {detail}"}
    except Exception as exc:
        return {"success": False, "error": f"API 调用失败: {exc}"}

    # 提取文本响应 (OpenAI 兼容格式)
    choices = body.get("choices", [])
    if not choices:
        return {"success": False, "error": "模型返回了空响应", "raw": body}

    text = choices[0].get("message", {}).get("content", "")
    if not text:
        return {"success": False, "error": "模型返回了空内容", "raw": body}

    # 解析 JSON（模型可能包在 ```json ... ``` 里）
    json_text = text.strip()
    if json_text.startswith("```"):
        lines = json_text.split("\n")
        json_text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

    try:
        result = json.loads(json_text)
    except json.JSONDecodeError:
        return {"success": False, "error": f"模型返回无法解析为 JSON:\n{text[:500]}", "raw_text": text}

    conditions = result.get("conditions", [])
    valid_types = {
        "daily_change", "n_day_change", "volume_ratio", "consecutive_days",
        "price_range", "n_day_high", "n_day_low", "avg_volume",
        "ma_cross", "gap", "engulfing", "ma5_pullback",
    }
    clean_conds = []
    for c in conditions:
        ctype = c.get("type", "")
        if ctype not in valid_types:
            continue
        clean_conds.append({"type": ctype, "params": c.get("params", {})})

    usage = body.get("usage", {})

    return {
        "success": True,
        "description": result.get("description", ""),
        "conditions": clean_conds,
        "model": body.get("model", model),
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }


def _guess_media_type(data: bytes) -> str:
    if data[:4] == b"\x89PNG":
        return "image/png"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:3] == b"GIF":
        return "image/gif"
    return "image/png"
