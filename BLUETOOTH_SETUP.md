# Bluetooth セットアップガイド

## 概要

Nintendo Switch は Classic Bluetooth (BR/EDR) HID プロファイルでコントローラーと通信します。
PC を「Pro Controller」として Switch に認識させるには、Bluetooth アダプタを特定の
**Class of Device (CoD) = 0x002508** に設定する必要があります。

```
0x002508 の内訳:
  Bits 2-7  (Minor Class) : 0b000010 = 2 = Gamepad
  Bits 8-12 (Major Class) : 0b00101  = 5 = Peripheral
  Bits 13-23 (Services)   : 0x000    = なし
```

---

## Linux (完全対応 ✅)

### 必要条件
- BlueZ 5.x (`bluetoothd`)
- Python 3.10+
- Bluetooth アダプタ (USB ドングル可)
- root 権限 または `CAP_NET_RAW`

### クイックスタート
```bash
# 1. セットアップスクリプト実行 (初回のみ)
chmod +x setup_linux.sh
./setup_linux.sh

# 2. 起動
./start.sh
```

### 手動セットアップ
```bash
# BT アダプタを Pro Controller として設定
sudo hciconfig hci0 up
sudo hciconfig hci0 class 0x002508      # CoD = Gamepad
sudo hciconfig hci0 name "Pro Controller"
sudo hciconfig hci0 piscan              # Discoverable + Connectable

# アプリ起動
sudo python3 main.py
# または setup_linux.sh 実行後:
./start.sh
```

### Switch との接続手順
1. `./start.sh` を実行 → ブラウザが開く
2. 「Bluetooth」タブ → **「ペアリング開始」** ボタンをクリック
3. Switch 本体:
   - ホームメニュー → コントローラー → 「持ちかた/順番を変える」
   - 「新しいコントローラーの追加」を選択
4. Switch 画面に **Pro Controller** が表示される → 選択
5. ペアリング完了 → 「接続しました」と表示される

### トラブルシューティング

**`[Errno 1] Operation not permitted` が出る場合**
```bash
# Python に CAP_NET_RAW を付与
sudo setcap 'cap_net_raw,cap_net_admin+eip' .venv/bin/python3
# または sudo で実行
sudo .venv/bin/python3 main.py
```

**Switch が PC を発見できない場合**
```bash
# 現在の設定を確認
hciconfig -a

# bluetoothd が PSM を占有していないか確認
sudo systemctl stop bluetooth
sudo hciconfig hci0 piscan
python3 main.py  # 直接起動
```

**SDP レコードが必要な場合 (古いBlueZ)**
```bash
# sdptool で HID レコードを登録
sudo sdptool add --handle 0x00010001 HID
```

---

## Windows (非対応 ⚠)

Windows の標準 Bluetooth スタック (Microsoft BT Stack) は
**Classic Bluetooth HID ホストエミュレーション** をサポートしていません。

### 代替方法: WSL2 + usbip

```powershell
# 1. WSL2 に Ubuntu をインストール
wsl --install -d Ubuntu-22.04

# 2. usbipd をインストール (PowerShell 管理者)
winget install usbipd

# 3. BT アダプタを WSL2 に渡す
#    デバイスマネージャーで Bluetooth アダプタの BUSID を確認
usbipd list
usbipd bind --busid <BUSID>
usbipd attach --wsl --busid <BUSID>

# 4. WSL2 (Ubuntu) 内で
sudo apt-get install -y bluez
sudo hciconfig hci0 up
cd /mnt/c/path/to/mhxx_snipe_pc
./setup_linux.sh
./start.sh
```

### Windowsでの用途 (BT接続なし)
- 🔍 **護石サーチ** → 完全動作
- 📋 **マクロ作成・編集** → 完全動作
- 📡 **Switch BT 接続** → 非対応 (WSL2 で解決)

---

## macOS (限定対応 ⚠)

macOS の CoreBluetooth は BLE のみ対応。Classic Bluetooth HID は非対応です。

### 代替方法: UTM (Linux VM)

1. [UTM](https://mac.getutm.app/) をインストール
2. Ubuntu 22.04 VM を作成、USB Bluetooth アダプタをパススルー
3. VM 内で `setup_linux.sh` を実行

---

## BT アダプタ推奨品

| アダプタ | チップ | Linux 対応 |
|---------|--------|-----------|
| ASUS USB-BT500 | RTL8761B | ✅ |
| TP-Link UB500 | RTL8761B | ✅ |
| Plugable USB-BT4LE | BCM20702 | ✅ |
| 内蔵 Intel BT | Intel | ✅ |

> ⚠ Mediatek 系アダプタは Linux で動作しない場合があります。

---

## 接続フロー詳細

```
PC (Pro Controller)          Nintendo Switch
       |                            |
       |  BT Discoverable (0x002508)|
       |<-- Connection Request ---  |  (Switch が PC を発見)
       |                            |
  L2CAP PSM 0x11 (HID Control)     |
       |--- Accept ---------------→ |
  L2CAP PSM 0x13 (HID Interrupt)   |
       |--- Accept ---------------→ |
       |                            |
       |<-- Subcommand 0x01 ------  |  (BT Manual Pairing)
       |--- ACK 0x81 -----------→  |
       |<-- Subcommand 0x02 ------  |  (Device Info Request)
       |--- Device Info --------→  |
       |<-- Subcommand 0x03 ------  |  (Set Report Mode)
       |--- ACK 0x80 -----------→  |
       |--- 0x30 Input Report (15ms)|  (定期入力レポート開始)
       |--- 0x30 Input Report ---→  |
       |         ...                |
```
