#!/usr/bin/env python3
"""
GTFSデータ自動更新スクリプト
毎朝4時に実行して、新しいデータがあればダウンロード
"""
import os
import sys
import urllib.request
import zipfile
import json
from datetime import datetime

from config import get_config

# 設定
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
VERSION_FILE = os.path.join(DATA_DIR, "version.json")


def get_current_version():
    """現在のデータバージョンを取得"""
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, "r") as f:
            data = json.load(f)
            return data.get("date")
    return None


def save_version(date_str):
    """データバージョンを保存"""
    with open(VERSION_FILE, "w") as f:
        json.dump({
            "date": date_str,
            "updated_at": datetime.now().isoformat()
        }, f, indent=2)


def get_latest_date(config):
    """ODPTから最新のデータ日付を取得（ヘッダーから推測）"""
    from datetime import timedelta
    today = datetime.now()

    for days_ago in range(0, 30):
        check_date = today - timedelta(days=days_ago)
        date_str = check_date.strftime("%Y%m%d")
        url = f"{config.odpt.gtfs_url}?date={date_str}&acl:consumerKey={config.odpt.api_key}"

        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=10) as res:
                if res.status == 200 or res.status == 302:
                    return date_str
        except:
            continue

    return None


def download_gtfs(config, date_str):
    """GTFSデータをダウンロードして解凍"""
    url = f"{config.odpt.gtfs_url}?date={date_str}&acl:consumerKey={config.odpt.api_key}"
    zip_path = os.path.join(DATA_DIR, "OdakyuBus.zip")

    print(f"Downloading GTFS data (date={date_str})...")

    # ダウンロード（リダイレクトに対応）
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=60) as res:
        # リダイレクトの場合
        if res.status == 302 or "Found" in str(res.read(100)):
            # curlでリダイレクトをフォロー
            import subprocess
            result = subprocess.run(
                ["curl", "-L", "-s", "-o", zip_path, url],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                raise Exception(f"Download failed: {result.stderr}")
        else:
            # 直接ダウンロード
            with open(zip_path, "wb") as f:
                f.write(res.read())

    # ファイルサイズチェック
    if os.path.getsize(zip_path) < 1000:
        # 小さすぎる場合はリダイレクトレスポンスの可能性
        import subprocess
        result = subprocess.run(
            ["curl", "-L", "-s", "-o", zip_path, url],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise Exception(f"Download failed: {result.stderr}")

    print(f"Downloaded: {os.path.getsize(zip_path)} bytes")

    # 解凍
    print("Extracting...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(DATA_DIR)

    print("Extraction complete")
    return True


def restart_service():
    """サービスを再起動（systemd使用時）"""
    import subprocess
    try:
        result = subprocess.run(
            ["systemctl", "restart", "bus-arrival-notifier"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("Service restarted")
        else:
            print(f"Service restart failed (may not be running as systemd): {result.stderr}")
    except FileNotFoundError:
        print("systemctl not found (not running on Linux with systemd)")


def main():
    print(f"=== GTFS Update Check: {datetime.now().isoformat()} ===")

    # Load config
    config = get_config()

    # データディレクトリ作成
    os.makedirs(DATA_DIR, exist_ok=True)

    # 現在のバージョン
    current_version = get_current_version()
    print(f"Current version: {current_version or 'None'}")

    # 最新バージョンを確認
    latest_version = get_latest_date(config)
    print(f"Latest version: {latest_version or 'Unknown'}")

    if not latest_version:
        print("Could not determine latest version")
        return 1

    # 更新が必要か確認
    if current_version == latest_version:
        print("Already up to date")
        return 0

    # ダウンロード
    try:
        download_gtfs(config, latest_version)
        save_version(latest_version)
        print(f"Updated to version: {latest_version}")

        # サービス再起動
        restart_service()

        return 0
    except Exception as e:
        print(f"Update failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
