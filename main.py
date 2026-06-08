"""
MHXX スナイプツール PC版 - メインサーバー
Flask REST API + Server-Sent Events でブラウザ UI と通信する
"""

import sys
import os
import platform
import threading
import time
import webbrowser
import json
import queue
import logging
from pathlib import Path

from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS

# ─── 基本設定 ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mhxx_snipe")

OS = platform.system()          # 'Linux' / 'Windows' / 'Darwin'
BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
MACROS_DIR = BASE_DIR / "macros"
MACROS_DIR.mkdir(exist_ok=True)

app = Flask(__name__, static_folder=str(ASSETS_DIR))
CORS(app)

# SSE イベントキュー (複数クライアント対応)
_sse_clients: list[queue.Queue] = []
_sse_lock = threading.Lock()

# ─── BT コントローラー (遅延インポート) ─────────────────────────────
_controller = None
_ctrl_lock = threading.Lock()

def get_controller():
    global _controller
    with _ctrl_lock:
        if _controller is None:
            if OS == "Linux":
                from bt_linux import LinuxSwitchController
                _controller = LinuxSwitchController(push_event)
            else:
                from bt_stub import StubSwitchController
                _controller = StubSwitchController(push_event)
    return _controller


def push_event(event_type: str, data: dict):
    """全 SSE クライアントへイベントをプッシュ"""
    payload = f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    with _sse_lock:
        dead = []
        for q in _sse_clients:
            try:
                q.put_nowait(payload)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _sse_clients.remove(q)


# ─── Web ルート ───────────────────────────────────────────────────────

@app.route("/")
def index():
    """HTML にPC ブリッジスクリプトを注入して配信"""
    html_path = ASSETS_DIR / "snipe_integrated.html"
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    # </head> の直前に pc_bridge.js を挿入
    bridge_tag = '<script src="/pc_bridge.js"></script>'
    if "</head>" in html:
        html = html.replace("</head>", f"{bridge_tag}\n</head>", 1)
    else:
        html = bridge_tag + html

    return Response(html, mimetype="text/html; charset=utf-8")


@app.route("/pc_bridge.js")
def bridge_js():
    return send_from_directory(str(ASSETS_DIR), "pc_bridge.js")


# ─── SSE エンドポイント ───────────────────────────────────────────────

@app.route("/api/events")
def sse_events():
    q: queue.Queue = queue.Queue(maxsize=64)
    with _sse_lock:
        _sse_clients.append(q)

    def stream():
        try:
            # 接続直後に OS 情報を送る
            yield f"event: server_info\ndata: {json.dumps({'os': OS, 'bt_supported': OS == 'Linux'})}\n\n"
            while True:
                try:
                    payload = q.get(timeout=25)
                    yield payload
                except queue.Empty:
                    yield ": keepalive\n\n"
        except GeneratorExit:
            pass
        finally:
            with _sse_lock:
                if q in _sse_clients:
                    _sse_clients.remove(q)

    return Response(
        stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ─── Bluetooth API ────────────────────────────────────────────────────

@app.route("/api/bt/start", methods=["POST"])
def bt_start():
    threading.Thread(target=get_controller().start_discovery, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/bt/stop", methods=["POST"])
def bt_stop():
    get_controller().stop_discovery()
    return jsonify({"ok": True})


@app.route("/api/bt/disconnect", methods=["POST"])
def bt_disconnect():
    get_controller().disconnect()
    return jsonify({"ok": True})


@app.route("/api/bt/input", methods=["POST"])
def bt_input():
    get_controller().send_input(request.json or {})
    return jsonify({"ok": True})


@app.route("/api/bt/press", methods=["POST"])
def bt_press():
    d = request.json or {}
    get_controller().press_button(d.get("button", ""), int(d.get("duration", 100)))
    return jsonify({"ok": True})


@app.route("/api/bt/press_multi", methods=["POST"])
def bt_press_multi():
    d = request.json or {}
    get_controller().press_buttons(d.get("buttons", []), int(d.get("duration", 100)))
    return jsonify({"ok": True})


@app.route("/api/bt/stick", methods=["POST"])
def bt_stick():
    d = request.json or {}
    get_controller().set_stick(d.get("side", "L"), float(d.get("x", 0)), float(d.get("y", 0)))
    return jsonify({"ok": True})


@app.route("/api/bt/tilt", methods=["POST"])
def bt_tilt():
    d = request.json or {}
    get_controller().tilt_stick(
        d.get("side", "L"),
        float(d.get("x", 0)),
        float(d.get("y", 0)),
        int(d.get("duration", 500)),
    )
    return jsonify({"ok": True})


# ─── Macro API ────────────────────────────────────────────────────────

@app.route("/api/macros", methods=["GET"])
def get_macros():
    from macro_manager import MacroManager
    mgr = MacroManager(MACROS_DIR)
    return jsonify(mgr.get_all())


@app.route("/api/macros/save", methods=["POST"])
def save_macro():
    d = request.json or {}
    from macro_manager import MacroManager
    MacroManager(MACROS_DIR).save(d.get("name", ""), d.get("content", ""))
    return jsonify({"ok": True})


@app.route("/api/macros/delete", methods=["POST"])
def delete_macro():
    d = request.json or {}
    from macro_manager import MacroManager
    MacroManager(MACROS_DIR).delete(d.get("name", ""))
    return jsonify({"ok": True})


@app.route("/api/macros/execute", methods=["POST"])
def execute_macro():
    d = request.json or {}
    threading.Thread(
        target=get_controller().execute_macro,
        args=(d.get("name", ""), d.get("content", ""), int(d.get("loops", 1))),
        daemon=True,
    ).start()
    return jsonify({"ok": True})


@app.route("/api/macros/stop", methods=["POST"])
def stop_macro():
    get_controller().stop_macro()
    return jsonify({"ok": True})


# ─── 起動 ─────────────────────────────────────────────────────────────

def _print_banner(port: int):
    url = f"http://localhost:{port}"
    print("━" * 50)
    print("  MHXX 護石スナイプツール PC版")
    print(f"  起動: {url}")
    print(f"  OS  : {OS}")
    if OS == "Linux":
        print("  BT  : BlueZ (完全対応)")
        print("  ⚠ Bluetoothにはroot権限が必要な場合があります")
        print("    → sudo python3 main.py")
    elif OS == "Windows":
        print("  BT  : ⚠ Windows は Switch BT HID 非対応")
        print("    → BLUETOOTH_SETUP.md を参照 (WSL2 推奨)")
    elif OS == "Darwin":
        print("  BT  : ⚠ macOS は限定サポート")
        print("    → BLUETOOTH_SETUP.md を参照")
    print("━" * 50)


if __name__ == "__main__":
    PORT = 18080

    _print_banner(PORT)

    def _open_browser():
        time.sleep(1.8)
        webbrowser.open(f"http://localhost:{PORT}")

    threading.Thread(target=_open_browser, daemon=True).start()

    try:
        app.run(host="127.0.0.1", port=PORT, threaded=True, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        logger.info("終了")
