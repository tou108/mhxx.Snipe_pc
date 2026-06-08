#!/usr/bin/env bash
# build_linux.sh  —  Linux 単体バイナリビルド (PyInstaller)
set -e

echo "[BUILD] Linux バイナリビルド開始..."

pip install --quiet pyinstaller

pyinstaller \
  --onefile \
  --name mhxx_snipe_pc \
  --add-data "assets:assets" \
  --add-data "requirements.txt:." \
  --hidden-import flask \
  --hidden-import flask_cors \
  --hidden-import bt_linux \
  --hidden-import bt_stub \
  --hidden-import macro_manager \
  --collect-all flask \
  --noconfirm \
  main.py

echo "[BUILD] 完了: dist/mhxx_snipe_pc"
echo ""
echo "実行方法:"
echo "  sudo ./dist/mhxx_snipe_pc"
echo "  または setup_linux.sh で CAP_NET_RAW を付与後:"
echo "  ./dist/mhxx_snipe_pc"
