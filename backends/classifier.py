"""Phân loại tin nhắn: gọi AI service rồi kết hợp với bảng từ khóa của phụ huynh."""
import os
import re
import unicodedata

import httpx

from store import CATEGORIES

AI_URL = os.getenv("AI_URL", "http://127.0.0.1:8000/predict")
AI_TIMEOUT = float(os.getenv("AI_TIMEOUT", "3"))


def normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text).strip()


def match_rules(text: str, rules: list[dict]) -> int | None:
    """Nhãn cao nhất khớp với từ khóa của phụ huynh (so khớp nguyên từ), hoặc None."""
    lower = normalize(text).lower()
    best = None
    for rule in rules:
        keyword = re.escape(normalize(rule["keyword"]).lower())
        if re.search(rf"(?<!\w){keyword}(?!\w)", lower):
            level = 2 if rule["level"] == "Danger" else 1
            best = level if best is None else max(best, level)
    return best


async def call_ai(text: str) -> tuple[int, float] | None:
    """Gọi AI service; trả về (label, confidence) hoặc None nếu AI không phản hồi đúng."""
    try:
        async with httpx.AsyncClient(timeout=AI_TIMEOUT) as client:
            resp = await client.post(AI_URL, json={"text": text})
            resp.raise_for_status()
            data = resp.json()
            label = int(data["label"])
            if label not in CATEGORIES:
                return None
            return label, float(data["confidence"])
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return None


def decide_action(label: int, confidence: float | None, settings: dict) -> str:
    if label == 2:
        sure = confidence is None or confidence >= settings["danger_threshold"]
        return "Blocked" if settings["block_danger"] and sure else "Warned"
    if label == 1:
        return "Warned" if settings["warn_notify"] else "Logged"
    return "Allowed"


async def classify(text: str, rules: list[dict], settings: dict) -> dict:
    """Trả về {label, category, confidence, source, action}.

    confidence chỉ có giá trị khi nhãn đến từ mô hình AI. Nếu nhãn do từ khóa
    quyết định hoặc AI không chạy thì confidence = None (không bịa số).
    """
    text = normalize(text)
    ai = await call_ai(text)
    rule_label = match_rules(text, rules)

    if ai is not None:
        label, confidence, source = ai[0], ai[1], "ai"
    else:
        label, confidence, source = 0, None, "rules"

    if rule_label is not None and rule_label > label:
        label, confidence, source = rule_label, None, "rules"

    return {
        "label": label,
        "category": CATEGORIES[label],
        "confidence": confidence,
        "source": source,
        "action": decide_action(label, confidence, settings),
    }
