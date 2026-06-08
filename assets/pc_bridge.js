/**
 * pc_bridge.js  —  PC版 Android ブリッジ差し替え
 *
 * Android WebView の window.Android / window.AndroidBridge を
 * Flask REST API + SSE で代替します。
 *
 * ・コントローラー操作 → POST /api/bt/...
 * ・マクロ CRUD       → POST /api/macros/...
 * ・サーバー→ブラウザ  → GET  /api/events (SSE)
 */
(function () {
  'use strict';

  /* ── API ヘルパー ─────────────────────────────────────────── */
  async function post(path, data) {
    try {
      const res = await fetch('/api' + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: data !== undefined ? JSON.stringify(data) : undefined,
      });
      return await res.json().catch(() => ({}));
    } catch (e) {
      console.warn('[pc_bridge] API error:', path, e);
      return {};
    }
  }

  /* ── マクロキャッシュ (起動時にサーバーから同期) ──────────── */
  let _macros = {};   // { name: contentStr }

  async function _syncMacros() {
    try {
      const res  = await fetch('/api/macros');
      _macros = await res.json();
    } catch (e) {
      console.warn('[pc_bridge] マクロ同期失敗:', e);
    }
  }

  /* ── Android ブリッジ本体 ──────────────────────────────────── */
  const bridge = {

    /* --- Bluetooth --- */
    startBluetoothDiscovery: () => {
      post('/bt/start');
    },

    stopBluetoothDiscovery: () => {
      post('/bt/stop');
    },

    disconnectBluetoothSwitch: () => {
      post('/bt/disconnect');
    },

    sendControllerInput: (data) => {
      const parsed = typeof data === 'string' ? _tryParse(data) : data;
      if (parsed) post('/bt/input', parsed);
    },

    /* _parentAb 経由でも呼ばれる */
    pressButton: (button, duration) => {
      post('/bt/press', {
        button:   String(button),
        duration: Number(duration) || 100,
      });
    },

    pressButtons: (buttonsOrJson, duration) => {
      const buttons = Array.isArray(buttonsOrJson)
        ? buttonsOrJson
        : _tryParse(buttonsOrJson) || [];
      post('/bt/press_multi', {
        buttons,
        duration: Number(duration) || 100,
      });
    },

    setStick: (side, x, y) => {
      post('/bt/stick', {
        side: String(side),
        x: Number(x),
        y: Number(y),
      });
    },

    tiltStick: (side, x, y, duration) => {
      post('/bt/tilt', {
        side: String(side),
        x:    Number(x),
        y:    Number(y),
        duration: Number(duration) || 500,
      });
    },

    /* --- マクロ管理 --- */
    getMacros: () => {
      return JSON.stringify(Object.keys(_macros));
    },

    getMacroContent: (name) => {
      return _macros[String(name)] || '[]';
    },

    saveMacro: (name, content) => {
      _macros[String(name)] = content;
      post('/macros/save', { name: String(name), content });
      return 'success';
    },

    deleteMacro: (name) => {
      delete _macros[String(name)];
      post('/macros/delete', { name: String(name) });
      return 'success';
    },

    executeMacro: (name, loops) => {
      const content = _macros[String(name)] || '[]';
      post('/macros/execute', {
        name:    String(name),
        content,
        loops:   Number(loops) || 1,
      });
    },

    stopMacro: () => {
      post('/macros/stop');
    },

    /* --- ML Kit OCR (PC非対応) --- */
    runMlKit: (_base64) => {
      if (typeof showToast === 'function') {
        showToast('⚠ PC版では OCR 機能は使用できません');
      }
    },
  };

  /* _parentAb が参照する両方の名前でセット */
  window.Android       = bridge;
  window.AndroidBridge = bridge;

  /* ── SSE: サーバー → ブラウザ ──────────────────────────────── */
  let _sse       = null;
  let _sseDelay  = 500;

  function _connectSSE() {
    if (_sse) { try { _sse.close(); } catch (_) {} }
    _sse = new EventSource('/api/events');

    _sse.addEventListener('server_info', (e) => {
      const d = _tryParse(e.data);
      if (!d) return;
      if (!d.bt_supported) {
        /* BT 非対応 OS の場合、BT タブにバナーを追加 */
        _showUnsupportedBanner(d.os);
      }
    });

    _sse.addEventListener('bt_status', (e) => {
      if (typeof bluetoothStatus === 'function') {
        bluetoothStatus(e.data);
      }
    });

    _sse.addEventListener('bt_discovery', (e) => {
      if (typeof bluetoothDiscovery === 'function') {
        bluetoothDiscovery(e.data);
      }
    });

    _sse.addEventListener('macro_done', (e) => {
      const d = _tryParse(e.data);
      if (typeof showToast === 'function') {
        showToast('✅ マクロ完了: ' + (d && d.name ? d.name : ''));
      }
    });

    _sse.onerror = () => {
      _sse.close();
      _sse = null;
      _sseDelay = Math.min(_sseDelay * 2, 10000);
      setTimeout(_connectSSE, _sseDelay);
    };

    _sse.onopen = () => { _sseDelay = 500; };
  }

  /* ── BT 非対応バナー (Windows/macOS) ───────────────────────── */
  function _showUnsupportedBanner(os) {
    /* BT タブが開かれたら警告パネルを挿入 */
    const TAB_ID = 'tab-bt';
    let attempts = 0;
    const timer = setInterval(() => {
      const tab = document.getElementById(TAB_ID);
      if (!tab || ++attempts > 20) { clearInterval(timer); return; }

      if (tab.querySelector('#pc-bt-warning')) { clearInterval(timer); return; }

      const div = document.createElement('div');
      div.id = 'pc-bt-warning';
      div.style.cssText = [
        'margin:12px','padding:14px 16px',
        'background:rgba(255,170,0,0.10)',
        'border:1px solid rgba(255,170,0,0.45)',
        'border-radius:6px','font-size:12px',
        'color:#ffaa00','line-height:1.6',
      ].join(';');
      div.innerHTML =
        `<strong>⚠ ${os} では Switch Bluetooth HID 接続は非対応です</strong><br>` +
        'Linux (BlueZ) を使用してください。<br>' +
        'WSL2 経由でも利用可能です — <strong>BLUETOOTH_SETUP.md</strong> を参照。';
      tab.insertBefore(div, tab.firstChild);
      clearInterval(timer);
    }, 300);
  }

  /* ── ユーティリティ ────────────────────────────────────────── */
  function _tryParse(str) {
    try { return JSON.parse(str); } catch (_) { return null; }
  }

  /* ── 初期化 ────────────────────────────────────────────────── */
  function _init() {
    _syncMacros();
    _connectSSE();
    console.log('[pc_bridge] 初期化完了 (OS:',
      navigator.platform, '| SSE:/api/events)');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _init);
  } else {
    _init();
  }

})();
