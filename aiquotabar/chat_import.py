"""Import claude.ai and ChatGPT data exports into the ledger as estimates.

Neither web app records token counts in its export, so tokens are estimated
from text length (~4 characters per token). Each assistant reply is assumed to
re-read the whole conversation so far, which is how chat context works, but
system prompts, attachments, tool calls and hidden reasoning are not in the
export, so real usage is higher. Every imported row is flagged `estimated`
and kept out of quota attribution and the menu's "today" numbers.
"""

import json
import os
import zipfile
from datetime import datetime

from aiquotabar import ledger

CHARS_PER_TOKEN = 4


def _tok(text: str) -> int:
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


def _ts(v) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def load_export(path: str):
    """Return the parsed conversations list from a .zip or conversations.json."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            name = next((n for n in z.namelist() if n.endswith("conversations.json")), None)
            if not name:
                raise ValueError("No conversations.json in this export.")
            with z.open(name) as f:
                return json.load(f)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _claude_messages(conv):
    for m in conv.get("chat_messages") or []:
        role = "user" if m.get("sender") == "human" else "assistant"
        text = m.get("text") or ""
        if not text and isinstance(m.get("content"), list):
            text = "\n".join(b.get("text", "") for b in m["content"] if isinstance(b, dict))
        yield role, text, _ts(m.get("created_at")), None


def _chatgpt_messages(conv):
    """Walk the current branch from the leaf back to the root."""
    mapping = conv.get("mapping") or {}
    node_id = conv.get("current_node")
    chain = []
    while node_id and node_id in mapping:
        node = mapping[node_id]
        if node.get("message"):
            chain.append(node["message"])
        node_id = node.get("parent")
    for m in reversed(chain):
        role = (m.get("author") or {}).get("role")
        if role not in ("user", "assistant"):
            continue
        parts = (m.get("content") or {}).get("parts") or []
        text = "\n".join(p for p in parts if isinstance(p, str))
        model = (m.get("metadata") or {}).get("model_slug")
        yield role, text, _ts(m.get("create_time")), model


def import_export(conn, path: str) -> dict:
    data = load_export(path)
    if not isinstance(data, list) or not data:
        raise ValueError("This file has no conversations.")
    first = data[0]
    if "chat_messages" in first:
        source, walker, provider = "claude_chat", _claude_messages, "claude"
    elif "mapping" in first:
        source, walker, provider = "chatgpt_chat", _chatgpt_messages, "chatgpt"
    else:
        raise ValueError("Not a recognised claude.ai or ChatGPT export.")

    prompts, calls = [], []
    for conv in data:
        cid = conv.get("uuid") or conv.get("id") or conv.get("conversation_id")
        if not cid:
            continue
        session = f"{source}:{cid}"
        project = (conv.get("name") or conv.get("title") or "chat")[:60]
        context = 0
        n = 0
        for role, text, ts, model in walker(conv):
            n += 1
            if role == "user":
                if text.strip():
                    prompts.append({
                        "id": f"{session}:{n}", "source": source, "session_id": session,
                        "project": project, "ts": ts, "text": text, "estimated": 1,
                    })
                context += _tok(text)
            else:
                out = _tok(text)
                calls.append({
                    "id": f"{session}:{n}:r", "source": source, "session_id": session,
                    "project": project, "model": model or f"{provider}-web", "ts": ts,
                    "input_tokens": context, "output_tokens": out,
                    "cache_write_tokens": 0, "cache_read_tokens": 0,
                    "reasoning_tokens": 0, "cost_usd": None, "estimated": 1,
                })
                context += out
    ledger._insert(conn, prompts, calls, [])
    ledger.link_prompts(conn)
    conn.commit()
    return {"source": source, "conversations": len(data),
            "prompts": len(prompts), "replies": len(calls),
            "file": os.path.basename(path)}
