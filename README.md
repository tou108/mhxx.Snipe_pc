# MHXX 護石スナイプツール PC版

Android 版「mhxx_Snipe」の PC 移植版です。  
Flask + SSE でブラウザ UI を提供し、Linux BlueZ 経由で Nintendo Switch と
Bluetooth HID 接続します。

## 対応プラットフォーム

| OS | 護石サーチ | Switch BT接続 |
|----|-----------|--------------|
| **Linux** | ✅ | ✅ (BlueZ) |
| **Windows 10/11** | ✅ | ⚠ WSL2 経由のみ |
| **macOS** | ✅ | ⚠ Linux VM 経由のみ |

## クイックスタート

### Linux
```bash
chmod +x setup_linux.sh
./setup_linux.sh   # 初回のみ
./start.sh         # 以降はこれだけ
```

### Windows
```bat
setup_windows.bat  REM 初回のみ
start.bat          REM 以降はこれだけ
```

## リリース版バイナリ (GitHub Actions)

[Releases](../../releases) から OS 対応版をダウンロード:

| ファイル | OS |
|---------|-----|
| `mhxx_snipe_pc.exe` | Windows 10/11 |
| `mhxx_snipe_pc-linux.tar.gz` | Linux (x86_64) |
| `mhxx_snipe_pc-macos.tar.gz` | macOS (arm64) |

## Switch との接続

→ **[BLUETOOTH_SETUP.md](BLUETOOTH_SETUP.md)** を参照

### 接続に必要な PC 側の設定
```bash
# Bluetooth アダプタの CoD を 0x002508 (Gamepad) に設定
sudo hciconfig hci0 class 0x002508
sudo hciconfig hci0 name "Pro Controller"
sudo hciconfig hci0 piscan
```

## プロジェクト構成

```
mhxx_snipe_pc/
├── main.py               # Flask サーバー (REST + SSE)
├── bt_linux.py           # Linux BlueZ HID コントローラー
├── bt_stub.py            # Windows/macOS スタブ
├── macro_manager.py      # マクロファイル管理
├── requirements.txt
├── setup_linux.sh
├── setup_windows.bat
├── build_linux.sh
├── build_windows.bat
├── build_macos.sh
├── BLUETOOTH_SETUP.md
├── assets/
│   ├── snipe_integrated.html   # UI (Android版から移植)
│   └── pc_bridge.js            # window.Android.* → HTTP/SSE 差し替え
├── macros/                     # 保存されたマクロ (.json)
└── .github/workflows/build.yml
```

## 開発者向け

```bash
# 仮想環境で直接実行
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
sudo python3 main.py
```

## 技術仕様

- **Switch 接続方式**: PC の Bluetooth アダプタ CoD を `0x002508` に設定し、  
  Switch 側から「新しいコントローラー」として検出させてペアリング (JoyConDroid 方式)
- **HID プロファイル**: L2CAP PSM 0x11 (Control) / 0x13 (Interrupt)
- **入力レポート**: 0x30 形式、48バイト、15ms 間隔
- **UI**: Android 版 `snipe_integrated.html` をそのまま流用 + `pc_bridge.js` で差し替え
