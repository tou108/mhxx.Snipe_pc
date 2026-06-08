"""
bt_linux.py — Linux BlueZ AF_BLUETOOTH/L2CAP による
Nintendo Switch Pro Controller HID エミュレーター

必要権限:
  - hciconfig でデバイス名・クラスを変更 → sudo が必要
  - L2CAP PSM 0x11/0x13 へのバインド → CAP_NET_RAW が必要
    → sudo python3 main.py で起動するか、事前に setup_linux.sh を実行してください

接続フロー:
  1. BT アダプタを "Pro Controller" / CoD 0x002508 に設定
  2. Discoverable/Connectable にする
  3. Switch 側: 「コントローラーの持ちかた/順番を変える」→「新しいコントローラーの追加」
  4. Switch が PC を発見してペアリング → L2CAP PSM 0x11/0x13 へ接続
  5. サブコマンドを処理し、0x30 レポートを 15ms 毎に送信
"""

import socket
import subprocess
import threading
import time
import re
import json
import logging
import os

logger = logging.getLogger("bt_linux")

# ──────────────────────────────────────────────────────────────────────
# 定数
# ──────────────────────────────────────────────────────────────────────
AF_BLUETOOTH   = socket.AF_BLUETOOTH
BTPROTO_L2CAP  = socket.BTPROTO_L2CAP
SOCK_SEQPACKET = socket.SOCK_SEQPACKET

HID_CTRL_PSM = 0x11   # HID Control  (L2CAP PSM)
HID_INTR_PSM = 0x13   # HID Interrupt (L2CAP PSM)

BT_NAME  = "Pro Controller"
BT_CLASS = "0x002508"   # Peripheral / Gamepad

# ボタンマップ  name → (byte_index, bitmask)
BUTTON_MAP: dict[str, tuple[int, int]] = {
    "Y": (0, 0x01), "X": (0, 0x02), "B": (0, 0x04), "A": (0, 0x08),
    "R": (0, 0x40), "ZR": (0, 0x80),
    "MINUS": (1, 0x01), "PLUS": (1, 0x02),
    "R_STICK": (1, 0x04), "L_STICK": (1, 0x08),
    "HOME": (1, 0x10), "CAPTURE": (1, 0x20),
    "DPAD_DOWN": (2, 0x01), "DPAD_UP": (2, 0x02),
    "DPAD_RIGHT": (2, 0x04), "DPAD_LEFT": (2, 0x08),
    "L": (2, 0x40), "ZL": (2, 0x80),
}


def _set_center(buf: bytearray, offset: int = 3):
    """スティック中立値を書き込む (12bit packed: 0x800)"""
    buf[offset]     = 0x00
    buf[offset + 1] = 0x08
    buf[offset + 2] = 0x80


def _to_12bit(v: float) -> int:
    """[-127, 127] → [0, 4095] の 12bit 値へ変換"""
    clamped = max(-127.0, min(127.0, float(v)))
    return max(0, min(4095, int((clamped + 127.0) * 4096.0 / 254.0)))


def build_button_state(
    buttons: list[str],
    lx: float = 0, ly: float = 0,
    rx: float = 0, ry: float = 0,
) -> bytearray:
    """9バイトのボタン/スティック状態を構築"""
    state = bytearray(9)
    b0 = b1 = b2 = 0
    for btn in buttons:
        m = BUTTON_MAP.get(btn.upper().strip())
        if m:
            idx, mask = m
            if idx == 0: b0 |= mask
            elif idx == 1: b1 |= mask
            elif idx == 2: b2 |= mask
    state[0], state[1], state[2] = b0, b1, b2

    lxv, lyv = _to_12bit(lx), _to_12bit(ly)
    rxv, ryv = _to_12bit(rx), _to_12bit(ry)
    state[3] = lxv & 0xFF
    state[4] = ((lxv >> 8) & 0x0F) | ((lyv & 0x0F) << 4)
    state[5] = (lyv >> 4) & 0xFF
    state[6] = rxv & 0xFF
    state[7] = ((rxv >> 8) & 0x0F) | ((ryv & 0x0F) << 4)
    state[8] = (ryv >> 4) & 0xFF

    return state


# ──────────────────────────────────────────────────────────────────────
# メインコントローラークラス
# ──────────────────────────────────────────────────────────────────────

class LinuxSwitchController:

    def __init__(self, send_event_func):
        self.send_event = send_event_func
        self.connected  = False
        self._running   = False
        self._stop_macro = False
        self._full_mode = False
        self._timer     = 0
        self._btn_state = bytearray(9)
        _set_center(self._btn_state)
        self._adapter   = self._find_adapter()
        self._original_name: str | None = None

        # ソケット
        self._ctrl_srv: socket.socket | None = None
        self._intr_srv: socket.socket | None = None
        self._ctrl_cli: socket.socket | None = None
        self._intr_cli: socket.socket | None = None

    # ── アダプタ設定 ────────────────────────────────────────────────

    def _find_adapter(self) -> str:
        try:
            out = subprocess.check_output(["hciconfig"], text=True, stderr=subprocess.DEVNULL)
            m = re.search(r"(hci\d+)", out)
            return m.group(1) if m else "hci0"
        except Exception:
            return "hci0"

    def _run(self, *args, sudo: bool = False) -> tuple[str, str, int]:
        cmd = (["sudo"] if sudo else []) + list(args)
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r.stdout, r.stderr, r.returncode

    def _get_mac(self) -> str:
        try:
            out, _, _ = self._run("hciconfig", self._adapter)
            m = re.search(r"BD Address: ([0-9A-Fa-f:]{17})", out)
            return m.group(1) if m else "00:00:00:00:00:00"
        except Exception:
            return "00:00:00:00:00:00"

    def _setup_adapter(self):
        # 元の名前を保存
        try:
            out, _, _ = self._run("hciconfig", self._adapter, "name")
            self._original_name = out.strip()
        except Exception:
            pass

        self._run("hciconfig", self._adapter, "name", BT_NAME,  sudo=True)
        self._run("hciconfig", self._adapter, "class", BT_CLASS, sudo=True)
        self._run("hciconfig", self._adapter, "piscan",           sudo=True)
        logger.info(f"アダプタ設定: {self._adapter} name={BT_NAME} class={BT_CLASS}")

    def _restore_adapter(self):
        if self._original_name:
            self._run("hciconfig", self._adapter, "name", self._original_name, sudo=True)
        self._run("hciconfig", self._adapter, "noscan", sudo=True)

    # ── L2CAP サーバーソケット ───────────────────────────────────────

    def _make_server(self, psm: int) -> socket.socket:
        sock = socket.socket(AF_BLUETOOTH, SOCK_SEQPACKET, BTPROTO_L2CAP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            # BT_SECURITY_LOW (1) を設定 — ペアリング不要
            sock.setsockopt(274, 4, 1)   # SOL_BLUETOOTH=274, BT_SECURITY=4
        except Exception:
            pass
        sock.bind(("00:00:00:00:00:00", psm))
        sock.listen(1)
        return sock

    # ── 接続メインループ ─────────────────────────────────────────────

    def start_discovery(self):
        """Switch からの接続を待機"""
        self._running = True
        try:
            self._setup_adapter()
            self.send_event("bt_discovery", {
                "status": "scanning",
                "duration": 90,
                "message": "Switch からの接続を待機中... (90秒)\n"
                           "Switch: 「コントローラーの持ちかた→新しいコントローラーの追加」",
            })

            self._ctrl_srv = self._make_server(HID_CTRL_PSM)
            self._intr_srv = self._make_server(HID_INTR_PSM)
            self._ctrl_srv.settimeout(95)
            self._intr_srv.settimeout(10)

            logger.info("Switch からの接続を待機中 (PSM 0x11/0x13)...")
            self._ctrl_cli, addr = self._ctrl_srv.accept()
            logger.info(f"HID Control 接続: {addr}")
            self._intr_cli, _ = self._intr_srv.accept()
            logger.info("HID Interrupt 接続")

            self.connected = True
            self.send_event("bt_status", {
                "status": "connected",
                "address": addr[0] if addr else "",
                "message": f"Switch と接続しました ({addr[0] if addr else '?'})",
            })

            self._full_mode = True
            threading.Thread(target=self._report_loop, daemon=True).start()
            self._recv_loop()   # ブロック — 切断まで

        except OSError as e:
            if self._running:
                msg = str(e)
                if "Permission denied" in msg or "EACCES" in msg:
                    msg = ("権限エラー: sudo python3 main.py で起動してください\n"
                           "または setup_linux.sh を実行して CAP_NET_RAW を付与してください")
                self.send_event("bt_status", {"status": "error", "message": msg})
        except Exception as e:
            if self._running:
                self.send_event("bt_status", {"status": "error", "message": str(e)})
        finally:
            self._cleanup()
            self._restore_adapter()
            if self._running:
                self.send_event("bt_status", {
                    "status": "disconnected",
                    "message": "切断されました",
                })

    # ── 受信ループ ───────────────────────────────────────────────────

    def _recv_loop(self):
        while self.connected and self._running:
            try:
                self._intr_cli.settimeout(1.0)
                data = self._intr_cli.recv(1024)
                if not data:
                    break
                # Switch → PC パケット: [0xA1, report_id, ...]
                if len(data) >= 2 and data[0] == 0xA1:
                    report_id = data[1]
                    payload   = bytes(data[2:])
                    if report_id == 0x21 and len(payload) >= 10:
                        self._handle_subcommand(payload)
                elif len(data) >= 1:
                    # 0xA1 ヘッダなし (古い BlueZ)
                    report_id = data[0]
                    payload   = bytes(data[1:])
                    if report_id == 0x21 and len(payload) >= 10:
                        self._handle_subcommand(payload)
            except OSError as e:
                if "timed out" not in str(e).lower():
                    logger.warning(f"recv: {e}")
                    break
            except Exception as e:
                logger.error(f"recv error: {e}")
                break
        self.connected = False

    # ── サブコマンド処理 ─────────────────────────────────────────────

    def _handle_subcommand(self, data: bytes):
        """Switch → PC サブコマンドを処理 (Kotlin handleSubcommand 移植)"""
        timer   = data[0] & 0xFF
        sub_cmd = data[9] & 0xFF
        logger.debug(f"SubCmd: 0x{sub_cmd:02X}")

        if sub_cmd == 0x01:
            self._ack(timer, sub_cmd, 0x81)

        elif sub_cmd == 0x02:   # デバイス情報
            mac_str  = self._get_mac()
            mac_bytes = [int(x, 16) for x in mac_str.split(":")]
            mac_rev  = list(reversed(mac_bytes))
            info = bytearray(12)
            info[0], info[1] = 0x04, 0x21
            info[2], info[3] = 0x03, 0x02
            for i, b in enumerate(mac_rev[:6]):
                info[4 + i] = b
            info[10], info[11] = 0x01, 0x01
            self._subcmd_reply(timer, 0x82, sub_cmd, bytes(info))

        elif sub_cmd == 0x03:   # 入力レポートモード設定
            self._ack(timer, sub_cmd, 0x80)
            if not self._full_mode:
                self._full_mode = True

        elif sub_cmd == 0x04:
            self._subcmd_reply(timer, 0x83, sub_cmd, bytes(8))

        elif sub_cmd == 0x08:
            self._ack(timer, sub_cmd, 0x80)

        elif sub_cmd == 0x10:   # SPI Flash 読み出し
            length = data[14] & 0xFF if len(data) >= 15 else 0
            reply  = bytearray(5 + length)
            if len(data) >= 14:
                reply[0:4] = data[10:14]
            if len(data) >= 15:
                reply[4] = data[14]
            self._subcmd_reply(timer, 0x90, sub_cmd, bytes(reply))

        elif sub_cmd == 0x11:
            self._ack(timer, sub_cmd, 0x80)

        elif sub_cmd == 0x21:   # NFC/IR MCU 設定
            self._subcmd_reply(timer, 0xA0, sub_cmd, bytes(34))

        elif sub_cmd in (0x22, 0x30, 0x38, 0x40, 0x41, 0x42, 0x43, 0x48):
            self._ack(timer, sub_cmd, 0x80)

        elif sub_cmd == 0x50:   # 電圧取得
            self._subcmd_reply(timer, 0x80, sub_cmd, bytes([0x08, 0x07, 0x00, 0x00]))

        else:
            self._ack(timer, sub_cmd, 0x80)

    # ── ACK / サブコマンド返信 ───────────────────────────────────────

    def _ack(self, timer: int, sub_cmd: int, ack: int):
        self._subcmd_reply(timer, ack, sub_cmd, b"")

    def _subcmd_reply(self, timer: int, ack: int, sub_cmd: int, extra: bytes):
        buf = bytearray(48)
        buf[0]  = timer & 0xFF
        buf[1]  = 0x8E
        _set_center(buf, 5)
        _set_center(buf, 8)
        buf[11] = 0xB0
        buf[12] = ack  & 0xFF
        buf[13] = sub_cmd & 0xFF
        n = min(len(extra), 34)
        buf[14 : 14 + n] = extra[:n]
        self._raw_send(0x21, bytes(buf))

    # ── 入力レポート送信 ─────────────────────────────────────────────

    def _raw_send(self, report_id: int, data: bytes):
        sock = self._intr_cli
        if sock and self.connected:
            try:
                sock.send(bytes([0xA1, report_id]) + data)
            except Exception as e:
                logger.error(f"send error: {e}")

    def _make_report(self) -> bytes:
        buf = bytearray(48)
        self._timer = (self._timer + 1) & 0xFF
        buf[0]  = self._timer
        buf[1]  = 0x8E
        buf[2:11] = self._btn_state[:9]
        buf[11] = 0xB0
        return bytes(buf)

    def _report_loop(self):
        """15ms ごとに 0x30 フルレポートを送信"""
        while self.connected and self._running:
            self._raw_send(0x30, self._make_report())
            time.sleep(0.015)

    # ── 入力 API ─────────────────────────────────────────────────────

    def send_input(self, data: dict):
        self._btn_state = build_button_state(
            data.get("buttons", []),
            data.get("lx", 0), data.get("ly", 0),
            data.get("rx", 0), data.get("ry", 0),
        )

    def press_button(self, button: str, duration_ms: int):
        self._btn_state = build_button_state([button])
        threading.Timer(duration_ms / 1000.0, self._release).start()

    def press_buttons(self, buttons: list[str], duration_ms: int):
        self._btn_state = build_button_state(buttons)
        threading.Timer(duration_ms / 1000.0, self._release).start()

    def _release(self):
        # 両スティックを中立に戻す (右スティックも 0x800)
        self._btn_state = build_button_state([])

    def set_stick(self, side: str, x: float, y: float):
        st = self._btn_state
        if side.upper() in ("L", "LEFT"):
            tmp = build_button_state([], lx=x, ly=y)
            st[3:6] = tmp[3:6]
        else:
            tmp = build_button_state([], rx=x, ry=y)
            st[6:9] = tmp[6:9]

    def tilt_stick(self, side: str, x: float, y: float, duration_ms: int):
        self.set_stick(side, x, y)
        threading.Timer(duration_ms / 1000.0, lambda: self.set_stick(side, 0, 0)).start()

    # ── マクロ実行 ───────────────────────────────────────────────────

    def execute_macro(self, name: str, content: str, loops: int):
        """JSON ステップ配列マクロを実行"""
        self._stop_macro = False
        try:
            steps = json.loads(content) if content else []
        except Exception:
            steps = []

        for _ in range(max(1, loops)):
            if self._stop_macro:
                break
            for step in steps:
                if self._stop_macro:
                    break
                self._exec_step(step)

        self.send_event("macro_done", {"name": name})

    def _exec_step(self, step: dict):
        t = step.get("type", "")
        dur = int(step.get("duration", 100))

        if t == "pressButton":
            self.press_button(step.get("button", ""), dur)
            time.sleep(dur / 1000.0 + 0.02)

        elif t == "pressButtons":
            btns = step.get("buttons", [])
            self.press_buttons(btns, dur)
            time.sleep(dur / 1000.0 + 0.02)

        elif t == "tiltStick":
            self.tilt_stick(
                step.get("side", "L"),
                step.get("x", 0), step.get("y", 0), dur
            )
            time.sleep(dur / 1000.0 + 0.02)

        elif t == "wait":
            wait_ms = int(step.get("duration", step.get("ms", 500)))
            elapsed = 0
            while elapsed < wait_ms and not self._stop_macro:
                time.sleep(0.05)
                elapsed += 50

    def stop_macro(self):
        self._stop_macro = True

    # ── 切断 & クリーンアップ ────────────────────────────────────────

    def stop_discovery(self):
        self._running = False
        self._cleanup()
        self._restore_adapter()
        self.send_event("bt_discovery", {
            "status": "stopped",
            "message": "ペアリング待機を停止しました",
        })

    def disconnect(self):
        self._running  = False
        self._full_mode = False
        self.connected = False
        self._cleanup()
        self._restore_adapter()
        self.send_event("bt_status", {
            "status": "disconnected",
            "message": "切断されました",
        })

    def _cleanup(self):
        for sock in (self._ctrl_cli, self._intr_cli, self._ctrl_srv, self._intr_srv):
            try:
                if sock:
                    sock.close()
            except Exception:
                pass
        self._ctrl_cli = self._intr_cli = None
        self._ctrl_srv = self._intr_srv = None
