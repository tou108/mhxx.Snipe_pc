"""
bt_stub.py — Windows / macOS 用スタブ

Windows/macOS は Classic Bluetooth HID ホストエミュレーションが
標準 API で提供されていないため、BT 接続機能はサポートしません。

【代替手段】
  ・Windows: WSL2 + usbip で BT アダプタを Linux に渡す → BLUETOOTH_SETUP.md 参照
  ・macOS   : 将来対応予定 (IOBluetooth 経由)

それ以外の機能 (護石サーチ・マクロ作成) はそのまま使用できます。
"""

import json
import logging
import platform
import threading
import time

logger = logging.getLogger("bt_stub")

_OS = platform.system()

_UNSUPPORTED_MSG = (
    f"⚠ {_OS} では Nintendo Switch Bluetooth HID 接続は非対応です。\n"
    "Linux (BlueZ) を使用してください。\n"
    "詳細: BLUETOOTH_SETUP.md"
)


class StubSwitchController:
    """接続機能なし — UI とマクロ管理のみ有効"""

    def __init__(self, send_event_func):
        self.send_event  = send_event_func
        self.connected   = False
        self._stop_macro = False

    # ── BT API (すべて「非対応」通知) ─────────────────────────────

    def start_discovery(self):
        logger.warning("BT HID 非対応環境での start_discovery 呼び出し")
        self.send_event("bt_status", {
            "status": "error",
            "message": _UNSUPPORTED_MSG,
        })

    def stop_discovery(self):
        self.send_event("bt_discovery", {
            "status": "stopped",
            "message": "（BT 非対応環境）",
        })

    def disconnect(self):
        self.send_event("bt_status", {
            "status": "disconnected",
            "message": "（BT 非対応環境）",
        })

    def send_input(self, data: dict):
        pass   # noop

    def press_button(self, button: str, duration_ms: int):
        pass

    def press_buttons(self, buttons: list, duration_ms: int):
        pass

    def set_stick(self, side: str, x: float, y: float):
        pass

    def tilt_stick(self, side: str, x: float, y: float, duration_ms: int):
        pass

    # ── マクロ (ステップのみ解釈・実行はしない) ───────────────────

    def execute_macro(self, name: str, content: str, loops: int):
        """BT 接続なしのため実行不可 — ログに記録のみ"""
        logger.info(f"[stub] execute_macro: {name} x{loops} (BT 未接続)")
        self.send_event("bt_status", {
            "status": "error",
            "message": "BT 未接続: Switch に接続してからマクロを実行してください",
        })

    def stop_macro(self):
        self._stop_macro = True
