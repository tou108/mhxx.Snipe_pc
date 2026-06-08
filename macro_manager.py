"""
macro_manager.py — マクロのファイルベース永続化

Android 版の内部ストレージ相当を macros/ ディレクトリで代替します。
フォーマット: JSON (steps 配列) をそのまま .json ファイルに保存
"""

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger("macro_mgr")


def _safe_name(name: str) -> str:
    """ファイル名として安全な文字列に正規化"""
    return re.sub(r"[^\w\-. ]", "_", name).strip()[:80]


class MacroManager:

    def __init__(self, macros_dir: Path):
        self.dir = macros_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    def get_all(self) -> dict[str, str]:
        """全マクロを {name: content_json_str} で返す"""
        result: dict[str, str] = {}
        for f in sorted(self.dir.glob("*.json")):
            try:
                result[f.stem] = f.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"マクロ読み込みエラー {f.name}: {e}")
        return result

    def save(self, name: str, content: str):
        """content は steps 配列の JSON 文字列"""
        safe = _safe_name(name)
        if not safe:
            logger.warning("マクロ名が空です")
            return
        path = self.dir / f"{safe}.json"
        try:
            # JSON として有効か検証してから保存
            json.loads(content)
            path.write_text(content, encoding="utf-8")
            logger.info(f"マクロ保存: {safe}")
        except json.JSONDecodeError:
            # 生テキストとして保存 (HTML 側が生テキストを渡す場合)
            path.write_text(content, encoding="utf-8")
            logger.info(f"マクロ保存 (生テキスト): {safe}")
        except Exception as e:
            logger.error(f"マクロ保存エラー: {e}")

    def delete(self, name: str):
        safe = _safe_name(name)
        path = self.dir / f"{safe}.json"
        if path.exists():
            path.unlink()
            logger.info(f"マクロ削除: {safe}")

    def get(self, name: str) -> str | None:
        safe = _safe_name(name)
        path = self.dir / f"{safe}.json"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None
