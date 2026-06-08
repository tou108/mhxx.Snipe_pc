#!/usr/bin/env bash
# setup_linux.sh  —  Linux 初回セットアップスクリプト
# Ubuntu 22.04 / 24.04 / Debian 12 対応
set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  MHXX スナイプツール PC版 — Linux セットアップ"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ─── 1. システムパッケージ ─────────────────────────────────────
echo ""
echo "[1/5] システムパッケージをインストール..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    bluetooth bluez bluez-tools \
    libglib2.0-dev

# ─── 2. Python 仮想環境 ────────────────────────────────────────
echo ""
echo "[2/5] Python 仮想環境を作成..."
cd "$(dirname "$0")"
python3 -m venv .venv
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# ─── 3. BT アダプタ設定 ───────────────────────────────────────
echo ""
echo "[3/5] Bluetooth アダプタを設定..."

ADAPTER="hci0"
if hciconfig "$ADAPTER" &>/dev/null; then
    sudo hciconfig "$ADAPTER" up
    sudo hciconfig "$ADAPTER" class 0x002508     # Peripheral / Gamepad
    sudo hciconfig "$ADAPTER" name "Pro Controller"
    sudo hciconfig "$ADAPTER" piscan             # Discoverable + Connectable
    echo "  アダプタ: $ADAPTER"
    echo "  CoD    : 0x002508 (Gamepad)"
    echo "  名前   : Pro Controller"
    echo "  モード : Discoverable + Connectable"
else
    echo "  ⚠ $ADAPTER が見つかりません。Bluetooth アダプタを接続してください。"
fi

# ─── 4. CAP_NET_RAW の付与 ────────────────────────────────────
echo ""
echo "[4/5] L2CAP 権限設定..."
PYTHON_BIN="$(pwd)/.venv/bin/python3"
if [ -f "$PYTHON_BIN" ]; then
    sudo setcap 'cap_net_raw,cap_net_admin+eip' "$PYTHON_BIN" 2>/dev/null \
        && echo "  CAP_NET_RAW を $PYTHON_BIN に付与しました (sudo 不要で起動可能)" \
        || echo "  ⚠ setcap 失敗。sudo python3 main.py で起動してください"
fi

# ─── 5. 起動スクリプト生成 ────────────────────────────────────
echo ""
echo "[5/5] 起動スクリプトを生成..."
cat > start.sh <<'EOF'
#!/usr/bin/env bash
cd "$(dirname "$0")"
source .venv/bin/activate

# アダプタを確実に設定
sudo hciconfig hci0 up          2>/dev/null || true
sudo hciconfig hci0 class 0x002508 2>/dev/null || true
sudo hciconfig hci0 name "Pro Controller" 2>/dev/null || true
sudo hciconfig hci0 piscan      2>/dev/null || true

python3 main.py "$@"
EOF
chmod +x start.sh

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  セットアップ完了!"
echo ""
echo "  起動方法:"
echo "    ./start.sh"
echo ""
echo "  または (sudo が必要な場合):"
echo "    sudo .venv/bin/python3 main.py"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
