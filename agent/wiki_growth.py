"""Shadow-trial Wiki growth candidate extraction.

This module is intentionally conservative: it never edits the user's Wiki pages
or Memory directly. It appends per-turn candidate notes to a date-stamped queue
file so a later dreaming/review job can promote only stable, verified facts.
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from hermes_time import now as hermes_now

_LOCK = threading.Lock()

_DEFAULT_VAULT_PATH = "/mnt/e/rfugqiyu/予欲无言联盟/XWideChaos"
_MAX_TEXT = 4000
_STABLE_SIGNAL_RE = re.compile(
    r"(记住|以后|偏好|我叫|我是|女友|妹妹|项目|规则|约定|不要|必须|主动|wiki|obsidian|todoist|飞书|微信)",
    re.IGNORECASE,
)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _cfg_get(cfg: Dict[str, Any], dotted: str, default: Any = None) -> Any:
    cur: Any = cfg or {}
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def is_enabled(cfg: Optional[Dict[str, Any]] = None) -> bool:
    """Return whether Wiki-growth candidate capture is enabled."""
    env = os.getenv("HERMES_WIKI_GROWTH_ENABLED", "")
    if env:
        return _truthy(env)
    return _truthy(_cfg_get(cfg or {}, "wiki_growth.enabled", False))


def resolve_vault_path(cfg: Optional[Dict[str, Any]] = None) -> Optional[Path]:
    """Resolve the target Obsidian vault path for candidate files."""
    raw = (
        os.getenv("HERMES_WIKI_GROWTH_VAULT", "").strip()
        or str(_cfg_get(cfg or {}, "wiki_growth.vault_path", "") or "").strip()
        or _DEFAULT_VAULT_PATH
    )
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.exists() and path.is_dir() else None


def should_capture_turn(
    *,
    user_message: Any,
    assistant_response: str,
    platform: str = "",
    lean_mode: bool = False,
    parent_session_id: str = "",
    interrupted: bool = False,
) -> bool:
    """Cheap gate to avoid writing noise into the candidate queue."""
    if interrupted or lean_mode or parent_session_id:
        return False
    if (platform or "").lower() == "cron" or (
        os.getenv("HERMES_CRON_SESSION") == "1" and (platform or "").lower() in {"", "cron"}
    ):
        return False
    text = _stringify(user_message)
    if not text.strip() or not assistant_response.strip():
        return False
    return bool(_STABLE_SIGNAL_RE.search(text))


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(value)


def _truncate(text: str, limit: int = _MAX_TEXT) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 20].rstrip() + "\n...[truncated]"


def _safe_block(text: str) -> str:
    return _truncate(text).replace("```", "`\u200b``")


def append_candidate(
    *,
    vault_path: Path,
    user_message: Any,
    assistant_response: str,
    session_id: str,
    platform: str,
    model: str,
    turn_exit_reason: str = "",
    timestamp: Optional[datetime] = None,
) -> Path:
    """Append one shadow-trial candidate block and return the file path."""
    ts = timestamp or hermes_now()
    queries_dir = vault_path / "_wiki" / "queries"
    queries_dir.mkdir(parents=True, exist_ok=True)
    out_path = queries_dir / f"wiki-growth-candidates-{ts.strftime('%Y-%m-%d')}.md"

    user_text = _stringify(user_message)
    digest = hashlib.sha256(
        (session_id + "\n" + user_text + "\n" + assistant_response).encode("utf-8", "ignore")
    ).hexdigest()[:16]

    entry = f"""
---
候选ID: {digest}
时间: {ts.isoformat()}
会话: {session_id or 'unknown'}
平台: {platform or 'unknown'}
模型: {model or 'unknown'}
状态: shadow-trial
出口: {turn_exit_reason or 'unknown'}
---

## 候选说明

本条由 Hermes turn-end Wiki growth hook 自动捕获。它只是候选，不代表已写入正文 Wiki；后续 dreaming/review 需要按 `_wiki/concepts/wiki-growth-rule.md` 判断是否晋升、修正或标记 ⚠️待确认。

## 用户原文

```text
{_safe_block(user_text)}
```

## 助手回应

```text
{_safe_block(assistant_response)}
```

## 待评估动作

- [ ] 判断是否是稳定信息
- [ ] 定位应修改的 entity / concept / log / index
- [ ] 如有冲突，标记 ⚠️待确认，不静默覆盖
- [ ] 晋升后在 `_wiki/log.md` 记录

""".lstrip()

    with _LOCK:
        if out_path.exists():
            existing = out_path.read_text(encoding="utf-8", errors="ignore")
            if f"候选ID: {digest}" in existing:
                return out_path
            content = existing.rstrip() + "\n\n---\n\n" + entry
        else:
            content = f"# Wiki Growth Candidates {ts.strftime('%Y-%m-%d')}\n\n" + entry
        out_path.write_text(content, encoding="utf-8")
    return out_path


def capture_turn_candidate(
    *,
    cfg: Optional[Dict[str, Any]] = None,
    user_message: Any,
    assistant_response: str,
    session_id: str,
    platform: str,
    model: str,
    turn_exit_reason: str = "",
    lean_mode: bool = False,
    parent_session_id: str = "",
    interrupted: bool = False,
) -> Optional[Path]:
    """Best-effort turn-end candidate capture. Returns path or None."""
    if not is_enabled(cfg):
        return None
    if not should_capture_turn(
        user_message=user_message,
        assistant_response=assistant_response,
        platform=platform,
        lean_mode=lean_mode,
        parent_session_id=parent_session_id,
        interrupted=interrupted,
    ):
        return None
    vault = resolve_vault_path(cfg)
    if not vault:
        return None
    return append_candidate(
        vault_path=vault,
        user_message=user_message,
        assistant_response=assistant_response,
        session_id=session_id,
        platform=platform,
        model=model,
        turn_exit_reason=turn_exit_reason,
    )
