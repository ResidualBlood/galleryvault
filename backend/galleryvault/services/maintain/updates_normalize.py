"""Title normalization for re-upload matching (gallery updates)."""

from __future__ import annotations

import re

__all__ = ["normalize_update_title"]

_UPDATE_TITLE_VARIANTS = (
    "中国翻訳", "中国翻译", "中文翻譯", "中文翻译", "中文", "中国語", "汉化", "漢化",
    "汉化组", "漢化組", "翻译", "翻訳", "english", "chinese", "dl版", "無修正", "无修正",
    "デジタル版", "デジタル", "digital", "colorized", "color", "スキャナー",
    "修正版", "未修正", "翻訳版", "翻譯版", "アニメ", "実写", "総集編", "全話",
    "uncensored", "uncenseored", "decensored", "ai generated", "ongoing", "進行中", "连载中",
    "連載中", "完結", "完结",
)


def normalize_update_title(title: str) -> str:
    """Normalize a gallery title for re-upload matching, supporting multi-chapter series and bilingual variants."""
    text = title.strip().lower()
    text = re.sub(r"^\d+[\s\-]+", "", text)

    # Normalize full-width brackets to standard brackets
    text = re.sub(r"[【［〖〔]", "[", text)
    text = re.sub(r"[】］〗〕]", "]", text)
    text = re.sub(r"[（]", "(", text)
    text = re.sub(r"[）]", ")", text)

    # If bilingual title separated by | or ／, take primary part
    if "|" in text:
        parts = [p.strip() for p in text.split("|") if p.strip()]
        if parts:
            text = parts[0]

    # Strip metadata tags inside brackets (languages, translation groups, formats)
    meta_bracket_pattern = r"\[(?:[^\]]*(?:中国|中文|翻訳|翻译|漢化|汉化|english|chinese|dl版|無修正|无修正|uncensor|decensor|デジタル|digital|color|スキャナー|修正|未修正|アニメ|実写|総集編|全話|特典|リーフレット|小冊子|おまけ|進行中|连载中|連載中|ongoing|ai generated|\d+p|\d+話|\d+话|個人|机翻|組|组)[^\]]*)\]"
    text = re.sub(meta_bracket_pattern, "", text, flags=re.IGNORECASE)

    variants = "|".join(_UPDATE_TITLE_VARIANTS)
    text = re.sub(rf"\[(?:{variants})\]", "", text, flags=re.IGNORECASE)
    text = re.sub(rf"\((?:{variants})\)", "", text, flags=re.IGNORECASE)

    # Strip bonus / leaflet additions
    text = re.sub(r"\+\s*[^\[\]()]*?(?:リーフレット|特典|おまけ|小冊子|設定資料)[^\[\]()]*", "", text, flags=re.IGNORECASE)

    # Strip date ranges and timestamps before general number regexes
    text = re.sub(r"\(\s*[\d./\-]+\s*[-~～至到]\s*[\d./\-]+\s*\)", "", text)
    text = re.sub(r"\[\s*[\d./\-]+\s*[-~～至到]\s*[\d./\-]+\s*\]", "", text)
    text = re.sub(r"\b\d{2,4}[./\-]\d{1,2}(?:[./\-]\d{1,2})?\s*[-~～至到]\s*\d{2,4}[./\-]\d{1,2}(?:[./\-]\d{1,2})?\b", "", text)
    text = re.sub(r"\b20\d{2}[./\-]\d{1,2}(?:[./\-]\d{1,2})?\b", "", text)
    text = re.sub(r"\b20\d{6}\b", "", text)

    # Strip chapter / volume / episode markers:
    # "第1-12話+2体目-第1-4話", "第22-38話", "第1-8話", "第8話", "第3話", "最後話"
    text = re.sub(r"第?\s*\d+(?:[-~～/、,]\s*(?:第?\s*)?\d+)*\s*(?:話|话|巻|卷|章|回|篇)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:最後話|最终话|最終話|前編|後編|前篇|後篇|番外編|番外篇|総集編|総集篇|全話)", "", text, flags=re.IGNORECASE)

    # Numbers with symbols / chapter ranges: "①〜⑨", "(01-06)", "1-4", "1-5", "t1-t21", "m1-m50", "#1-4"
    text = re.sub(r"[①-⑳㈠-㈩]\s*[-~～至到]\s*[①-⑳㈠-㈩]", "", text)
    text = re.sub(r"[①-⑳㈠-㈩]", "", text)
    text = re.sub(r"(?:[#t]|vol\.?|part\.?|set\.?|pt\.?)\s*\d+(?:\s*[-~～/]\s*(?:[#t]|vol\.?|part\.?|set\.?|pt\.?)?\s*\d+)?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\(\s*0*\d+\s*[-~～/]\s*0*\d+\s*\)", "", text)
    text = re.sub(r"\[\s*0*\d+\s*[-~～/]\s*0*\d+\s*\]", "", text)
    text = re.sub(r"\b0*\d+\s*[-~～]\s*0*\d+\b", "", text)

    # Subtitle separation with multi-spaces
    sub_parts = re.split(r"\s{2,}", text)
    if len(sub_parts) > 1 and len(sub_parts[0]) > 4:
        text = sub_parts[0]

    text = re.sub(r"[\s\[\](){}“”\"'`,.。、:：;；!！?？\-—_/\\|·・〜～+♥♡⭐]+", "", text)
    return text
