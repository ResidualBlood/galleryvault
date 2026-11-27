"""Inline Keyboard markup generators and helpers for Telegram Bot."""

from __future__ import annotations

from typing import Any


def inline_button(
    text: str,
    callback_data: str | None = None,
    url: str | None = None,
) -> dict[str, str]:
    """Build a single InlineKeyboardButton dict."""
    btn: dict[str, str] = {"text": text}
    if callback_data is not None:
        btn["callback_data"] = str(callback_data)
    elif url is not None:
        btn["url"] = str(url)
    return btn


def inline_keyboard(rows: list[list[dict[str, Any]]]) -> dict[str, list[list[dict[str, Any]]]]:
    """Wrap row arrays into Telegram's InlineKeyboardMarkup structure."""
    return {"inline_keyboard": rows}


def build_pagination_row(
    current_page: int,
    total_pages: int,
    callback_prefix: str,
    prev_text: str = "⬅️",
    next_text: str = "➡️",
) -> list[dict[str, str]]:
    """Build a pagination control row: [Prev] [Page/Total] [Next]."""
    row: list[dict[str, str]] = []
    if current_page > 1:
        row.append(
            inline_button(
                prev_text,
                callback_data=f"{callback_prefix}:p:{current_page - 1}",
            )
        )
    row.append(
        inline_button(
            f"{current_page}/{max(total_pages, 1)}",
            callback_data=f"{callback_prefix}:noop",
        )
    )
    if current_page < total_pages:
        row.append(
            inline_button(
                next_text,
                callback_data=f"{callback_prefix}:p:{current_page + 1}",
            )
        )
    return row
