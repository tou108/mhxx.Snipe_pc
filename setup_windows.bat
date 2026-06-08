@echo off
REM setup_windows.bat  —  Windows 初回セットアップ
REM Python 3.10+ が必要です (https://www.python.org/)

echo ========================================
echo   MHXX スナイプツール PC版 - Windows セットアップ
echo ========================================
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python が見つかりません。
    echo   https://www.python.org/downloads/ からインストールしてください。
    pause
    exit /b 1
)

echo [1/2] Python 依存パッケージをインストール...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

echo.
echo [2/2] 起動バッチを生成...
(
echo @echo off
echo cd /d "%%~dp0"
echo start "" "http://localhost:18080"
echo python main.py
echo pause
) > start.bat

echo.
echo ========================================
echo   セットアップ完了!
echo.
echo   [注意] Windows では Switch Bluetooth HID 接続は非対応です。
echo   護石サーチ機能は問題なく使用できます。
echo.
echo   Switch 接続が必要な場合は WSL2 を使用してください。
echo   詳細: BLUETOOTH_SETUP.md
echo.
echo   起動: start.bat をダブルクリック
echo ========================================
pause
