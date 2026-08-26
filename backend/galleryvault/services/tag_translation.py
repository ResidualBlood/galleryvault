"""Chinese tag translation for ExHentai namespaces and tag names.

Mirrors the behaviour of Ehviewer's bundled translation database: each tag is
rendered as ``<namespace label>: <translated name>`` where a translation is
available.  The data source is the **EhTagTranslation/Database** project (the
same one Ehviewer and 注射器 use):

- The bundled ``data/tag_translations.json`` is generated from the project's
  latest ``db.text.json`` release asset, so it works offline.
- The runtime auto-updater refreshes from the same release on a schedule
  (``tag_translation_update_interval_minutes``).

Multi-value tags (ExHentai joins several with `` | ``) are looked up as a
whole first and then value-by-value, so ``a | b`` renders as the re-joined
translations when the whole string has no entry.  Namespace *labels* follow
Ehviewer's CN convention; tag *names* come from the translation database.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Translation entries from EhTagTranslation may embed markdown images such as
# ``![图标](https://...webp)中文名``.  The image (including its alt text) is an
# icon reference, never part of the tag itself, so it is stripped before the
# value is shown.  A hard cap keeps pathological entries from bloating chips.
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_WHITESPACE = re.compile(r"\s+")
MAX_DISPLAY_LENGTH = 60


def clean_display(text: str) -> str:
    """Strip markdown icon syntax and cap the rendered tag length."""
    text = _MD_IMAGE.sub("", text)
    text = _WHITESPACE.sub(" ", text).strip()
    return text[:MAX_DISPLAY_LENGTH]

# Namespace display labels (Ehviewer CN convention takes precedence over the
# ehsyringe frontmatter labels, e.g. 作者/社团/角色扮演 instead of 艺术家/团队/Coser).
NAMESPACE_LABELS_ZH: dict[str, str] = {
    "artist": "作者",
    "character": "角色",
    "parody": "原作",
    "group": "社团",
    "language": "语言",
    "reclass": "重新分类",
    "female": "女性",
    "male": "男性",
    "mixed": "混合",
    "other": "其他",
    "cosplay": "角色扮演",
    "yuri": "百合",
    "yaoi": "耽美",
    "misc": "其他",
    "location": "地点",
    "rows": "内容索引",
}

# Ehsyringe namespaces that map onto an ExHentai namespace with a different key.
NAMESPACE_ALIASES: dict[str, str] = {
    "cosplayer": "cosplay",
    "other": "misc",
}

_BUNDLED_PATH = Path(__file__).resolve().parent.parent / "data" / "tag_translations.json"
_USER_PATH = Path(__file__).resolve().parent.parent / "tag_translations.json"

_TRANSLATIONS: dict[str, dict[str, str]] = {}


def load_translations(path: str | Path | None = None, *, reset: bool = False) -> int:
    """Merge an ehsyringe-style translation database into the active table.

    Accepts either a flat ``{namespace: {name: zh}}`` mapping or the ehsyringe
    export shape ``{"data": [{"namespace": ..., "data": [{"key": ..., "name": ...}]}]}``.

    Load order (later entries override earlier ones):
    1. bundled ``data/tag_translations.json``
    2. user override ``galleryvault/tag_translations.json``
    3. ``TAG_TRANSLATIONS_FILE`` env var (e.g. a host-mounted file)
    4. explicit ``path`` argument (tests / admin scripts)

    When ``reset`` is set the table is cleared first, which is what the
    automatic updater uses to drop stale entries.  Returns the entry count.
    """
    if reset:
        _TRANSLATIONS.clear()
    candidates: list[Path] = []
    if _BUNDLED_PATH.exists():
        candidates.append(_BUNDLED_PATH)
    if _USER_PATH.exists():
        candidates.append(_USER_PATH)
    env_path = os.environ.get("TAG_TRANSLATIONS_FILE")
    if env_path:
        p = Path(env_path)
        if p.exists():
            candidates.append(p)
        else:
            logger.warning("TAG_TRANSLATIONS_FILE not found", extra={"path": env_path})
    if path is not None:
        candidate = Path(path)
        if candidate.exists():
            candidates.append(candidate)
    for candidate in candidates:
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("failed to read tag translations", extra={"error": str(exc)})
            continue
        merge_translation_data(data)
    return translation_entry_count()


def merge_translation_data(data: object) -> int:
    """Merge already-parsed JSON into the active table, returning entry count."""
    entries = data.get("data") if isinstance(data, dict) and "data" in data else data
    if isinstance(entries, list):
        for group in entries:
            ns = group.get("namespace")
            if not ns:
                continue
            inner = group.get("data") or group.get("tags")
            if isinstance(inner, dict):
                # ehsyringe / EhTagTranslation release form: {name: translation}
                for name, zh in inner.items():
                    if not name:
                        continue
                    display = str(zh.get("name")) if isinstance(zh, dict) else str(zh)
                    if display:
                        _TRANSLATIONS.setdefault(ns, {})[str(name)] = display
                        alias = NAMESPACE_ALIASES.get(ns)
                        if alias:
                            _TRANSLATIONS.setdefault(alias, {})[str(name)] = display
            elif isinstance(inner, list):
                for item in inner:
                    key = item.get("key") or item.get("name")
                    name = item.get("name")
                    if key and name:
                        _TRANSLATIONS.setdefault(ns, {})[str(key)] = str(name)
                        alias = NAMESPACE_ALIASES.get(ns)
                        if alias:
                            _TRANSLATIONS.setdefault(alias, {})[str(key)] = str(name)
    elif isinstance(entries, dict):
        for ns, tags in entries.items():
            if isinstance(tags, dict):
                _TRANSLATIONS.setdefault(ns, {}).update(
                    {str(k): str(v) for k, v in tags.items()}
                )
    return translation_entry_count()


def translation_entry_count() -> int:
    """Number of loaded translations (for status/logging)."""
    return sum(len(v) for v in _TRANSLATIONS.values())


def search_zh(query: str, limit: int = 20) -> list[tuple[str, str, str]]:
    """Reverse-search the translation table for a Chinese query.

    Returns ``(namespace, name, display)`` tuples whose Chinese translation
    contains ``query`` (used for the Chinese tag-autocomplete in the search
    box).  Namespaces are ordered so high-traffic ones come first.
    """
    needle = query.casefold().strip()
    if not needle:
        return []
    order = ["parody", "character", "group", "artist", "female", "male", "language", "misc", "other"]
    scored: list[tuple[int, str, str, str]] = []
    for ns, table in _TRANSLATIONS.items():
        rank = order.index(ns) if ns in order else len(order)
        for name, zh in table.items():
            display = clean_display(str(zh)) if zh else ""
            if needle in display.casefold():
                scored.append((rank, ns, name, display))
    scored.sort(key=lambda item: item[0])
    return [(ns, name, display) for _, ns, name, display in scored[:limit]]


def translate_namespace(namespace: str | None) -> str:
    if not namespace:
        return ""
    return NAMESPACE_LABELS_ZH.get(namespace, namespace)


def translate_tag(namespace: str | None, name: str) -> str:
    if not name:
        return name
    table = _TRANSLATIONS.get(namespace or "")
    if table:
        hit = table.get(name) or table.get(name.lower())
        if hit:
            return clean_display(hit)
    alias = NAMESPACE_ALIASES.get(namespace or "")
    if alias:
        table = _TRANSLATIONS.get(alias)
        if table:
            hit = table.get(name) or table.get(name.lower())
            if hit:
                return clean_display(hit)
    # Multi-value tags (ExHentai joins them with " | ") are stored split in the
    # database, so look each value up separately and re-join the translations.
    if " | " in name:
        parts = [part.strip() for part in name.split(" | ")]
        translated = [translate_tag(namespace, part) for part in parts]
        if any(a != b for a, b in zip(parts, translated)):
            return " | ".join(translated)
    return name


def translated_tag(namespace: str | None, name: str) -> tuple[str, str]:
    """Return ``(namespace_label, display_name)`` with Chinese where available."""
    label = translate_namespace(namespace)
    display = translate_tag(namespace, name)
    return label, display
