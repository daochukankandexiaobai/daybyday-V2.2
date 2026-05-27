from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json_file(file_path: str | Path) -> dict[str, Any]:
    path = Path(file_path)
    # 使用 utf-8-sig 兼容带 BOM 的 JSON 文件。
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def save_json_file(file_path: str | Path, payload: dict[str, Any]) -> None:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
