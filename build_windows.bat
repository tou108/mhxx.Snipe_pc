@echo off
REM build_windows.bat  —  Windows EXE ビルド (PyInstaller)
REM GitHub Actions の windows-latest runner で実行されます

echo [BUILD] Windows EXE ビルド開始...

pip install --quiet pyinstaller

pyinstaller ^
  --onefile ^
  --name mhxx_snipe_pc ^
  --add-data "assets;assets" ^
  --add-data "requirements.txt;." ^
  --hidden-import flask ^
  --hidden-import flask_cors ^
  --hidden-import bt_linux ^
  --hidden-import bt_stub ^
  --hidden-import macro_manager ^
  --collect-all flask ^
  --noconfirm ^
  main.py

echo [BUILD] 完了: dist\mhxx_snipe_pc.exe
