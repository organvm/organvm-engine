"""Extract clipboard items from Paste.app SQLite database."""

from __future__ import annotations

import base64
import json
import sqlite3
import zlib
from datetime import datetime
from pathlib import Path

from organvm_engine.prompts.clipboard.schema import ClipboardItem

APPLE_EPOCH = 978307200  # NSDate epoch (2001-01-01)

DEFAULT_DB_PATH = (
    Path.home()
    / "Library/Containers/com.wiheads.paste/Data/Library/Application Support/Paste/db.sqlite"
)


def decode_blob(blob: bytes) -> str | None:
    """Decode a Paste.app raw pasteboard blob into plain text."""
    if not blob or len(blob) < 2:
        return None
    try:
        data = zlib.decompress(blob[1:], -15)
        items = json.loads(data)
        if not isinstance(items, list):
            return None
        for item in items:
            b64 = item.get("dataByType", {}).get("public.utf8-plain-text")
            if b64:
                return base64.b64decode(b64).decode("utf-8", errors="replace")
    except Exception:
        return None
    return None


def load_items(db_path: Path | None = None) -> list[ClipboardItem]:
    """Load all text clipboard items from the Paste.app database.

    Args:
        db_path: Path to the Paste.app SQLite database.
                 Defaults to the standard macOS location.

    Returns:
        List of ClipboardItem sorted by timestamp ascending.
    """
    path = db_path or DEFAULT_DB_PATH
    conn = sqlite3.connect(str(path))
    rows = conn.execute("""
        SELECT i.Z_PK,
               a.ZNAME,
               a.ZBUNDLEIDENTIFIER,
               i.ZTIMESTAMP,
               d.ZRAWPASTEBOARDITEMS
        FROM ZITEMENTITY i
        LEFT JOIN ZAPPLICATIONENTITY a ON i.ZSOURCEAPPLICATION = a.Z_PK
        LEFT JOIN ZITEMDATAENTITY d ON d.ZITEM = i.Z_PK
        WHERE d.ZRAWPASTEBOARDITEMS IS NOT NULL
          AND i.ZTIMESTAMP IS NOT NULL
        ORDER BY i.ZTIMESTAMP ASC
    """).fetchall()
    conn.close()

    items: list[ClipboardItem] = []
    for pk, app_name, bundle_id, ts, blob in rows:
        text = decode_blob(blob)
        if not text or len(text.strip()) < 10:
            continue
        dt = datetime.fromtimestamp(ts + APPLE_EPOCH)
        items.append(ClipboardItem(
            id=pk,
            app=app_name or "Unknown",
            bundle_id=bundle_id or "",
            timestamp=dt.isoformat(timespec="seconds"),
            date=dt.strftime("%Y-%m-%d"),
            time=dt.strftime("%H:%M:%S"),
            text=text.strip(),
        ))
    return items
