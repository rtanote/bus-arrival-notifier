"""
GTFS データパーサー
小田急バスの時刻表データから次のバス発車時刻を取得する
"""
import csv
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from config import get_config

# データディレクトリ
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# キャッシュ（起動時に一度だけ読み込む）
_cache = {
    "calendar_dates": None,
    "trip_services": None,
    "stop_times": None,
    "loaded": False,
}

# フォールバック状態を追跡
_fallback_info = {
    "is_fallback": False,
    "original_date": None,
    "fallback_date": None,
}


def _get_all_stop_ids() -> set:
    """設定から全バス停IDを取得"""
    config = get_config()
    all_stop_ids = set()
    for stop_config in config.bus_stops.values():
        all_stop_ids.update(stop_config.stop_ids)
    return all_stop_ids


def _find_fallback_date(target_date: str, calendar_dates: dict) -> Optional[str]:
    """
    指定日付がcalendar_datesにない場合、同じ曜日の最新日付を探す

    Args:
        target_date: YYYYMMDD形式の日付
        calendar_dates: {date: [service_ids]} の辞書

    Returns:
        フォールバック用の日付（YYYYMMDD形式）、見つからなければNone
    """
    global _fallback_info

    if target_date in calendar_dates:
        _fallback_info["is_fallback"] = False
        _fallback_info["original_date"] = target_date
        _fallback_info["fallback_date"] = None
        return target_date

    # 対象日の曜日を取得
    try:
        target_dt = datetime.strptime(target_date, "%Y%m%d")
        target_weekday = target_dt.weekday()
    except ValueError:
        return None

    # calendar_datesにある日付から同じ曜日のものを探す
    same_weekday_dates = []
    for date_str in calendar_dates.keys():
        try:
            dt = datetime.strptime(date_str, "%Y%m%d")
            if dt.weekday() == target_weekday:
                same_weekday_dates.append(date_str)
        except ValueError:
            continue

    if not same_weekday_dates:
        return None

    # 最新の日付を返す
    same_weekday_dates.sort(reverse=True)
    fallback_date = same_weekday_dates[0]
    print(f"[GTFS] Date {target_date} not in calendar, using fallback: {fallback_date} (same weekday)")

    # フォールバック情報を更新
    _fallback_info["is_fallback"] = True
    _fallback_info["original_date"] = target_date
    _fallback_info["fallback_date"] = fallback_date

    return fallback_date


def get_fallback_info() -> Dict:
    """
    フォールバック状態を取得

    Returns:
        {
            "is_fallback": bool,
            "original_date": str or None,  # YYYYMMDD
            "fallback_date": str or None,  # YYYYMMDD
            "fallback_date_formatted": str or None,  # "1月27日" 形式
        }
    """
    info = _fallback_info.copy()

    if info["is_fallback"] and info["fallback_date"]:
        try:
            dt = datetime.strptime(info["fallback_date"], "%Y%m%d")
            info["fallback_date_formatted"] = f"{dt.month}月{dt.day}日"
        except ValueError:
            info["fallback_date_formatted"] = None
    else:
        info["fallback_date_formatted"] = None

    return info


def _load_all_data():
    """全データを一度に読み込んでキャッシュ"""
    if _cache["loaded"]:
        return

    print("Loading GTFS data...")

    # calendar_dates.txt
    calendar_path = os.path.join(DATA_DIR, "calendar_dates.txt")
    service_dates = {}
    with open(calendar_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            service_id = row["service_id"]
            date = row["date"]
            exception_type = row.get("exception_type", "1")
            if exception_type == "1":
                if date not in service_dates:
                    service_dates[date] = []
                service_dates[date].append(service_id)
    _cache["calendar_dates"] = service_dates

    # trips.txt
    trips_path = os.path.join(DATA_DIR, "trips.txt")
    trip_services = {}
    with open(trips_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            trip_services[row["trip_id"]] = row["service_id"]
    _cache["trip_services"] = trip_services

    # stop_times.txt（必要なバス停のみ）
    all_stop_ids = _get_all_stop_ids()

    stop_times_path = os.path.join(DATA_DIR, "stop_times.txt")
    stop_times = []
    with open(stop_times_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["stop_id"] in all_stop_ids:
                stop_times.append({
                    "trip_id": row["trip_id"],
                    "departure_time": row["departure_time"],
                    "stop_id": row["stop_id"],
                    "headsign": row.get("stop_headsign", ""),
                })
    _cache["stop_times"] = stop_times

    _cache["loaded"] = True
    print(f"GTFS data loaded: {len(stop_times)} stop times for target stops")


def parse_time(time_str: str) -> Optional[timedelta]:
    """時刻文字列をtimedeltaに変換（24時超え対応）"""
    try:
        parts = time_str.split(":")
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2]) if len(parts) > 2 else 0
        return timedelta(hours=hours, minutes=minutes, seconds=seconds)
    except:
        return None


def get_next_buses(
    stop_location: str,
    destination: str,
    now: Optional[datetime] = None,
    limit: int = 3
) -> List[int]:
    """
    指定バス停から指定行き先への次のバスを取得

    Args:
        stop_location: bus_stops config key (e.g., "stop_a")
        destination: destinations config key (e.g., "destination_1")
        now: 現在時刻（省略時は現在時刻）
        limit: 取得する本数

    Returns:
        あと何分のリスト（例: [3, 8, 15]）
    """
    # データ読み込み（初回のみ）
    _load_all_data()

    config = get_config()

    if now is None:
        now = datetime.now()

    # 今日の日付（YYYYMMDD形式）
    today = now.strftime("%Y%m%d")

    # 現在時刻をtimedelta に変換
    current_time = timedelta(hours=now.hour, minutes=now.minute, seconds=now.second)

    # バス停情報
    stop_config = config.bus_stops.get(stop_location)
    if not stop_config:
        return []

    # 行き先パターン
    dest_patterns = config.destinations.get(destination, [])
    if not dest_patterns:
        return []

    # キャッシュからデータ取得
    calendar_dates = _cache["calendar_dates"]
    trip_services = _cache["trip_services"]
    stop_times = _cache["stop_times"]

    # 今日運行するservice_id（フォールバック対応）
    effective_date = _find_fallback_date(today, calendar_dates)
    if effective_date is None:
        return []
    today_services = set(calendar_dates.get(effective_date, []))

    # 該当するバスを抽出
    candidates = []
    target_stop_ids = set(stop_config.stop_ids)

    for st in stop_times:
        # バス停チェック
        if st["stop_id"] not in target_stop_ids:
            continue

        # 行き先チェック
        headsign = st["headsign"]
        if not any(pattern in headsign for pattern in dest_patterns):
            continue

        # service_idチェック（今日運行するか）
        service_id = trip_services.get(st["trip_id"])
        if service_id not in today_services:
            continue

        # 発車時刻
        dep_time = parse_time(st["departure_time"])
        if dep_time is None:
            continue

        # 現在時刻以降のみ
        if dep_time < current_time:
            continue

        # あと何分
        diff = dep_time - current_time
        minutes = int(diff.total_seconds() / 60)
        candidates.append(minutes)

    # ソートして上位を返す
    candidates.sort()
    return candidates[:limit]


def get_next_buses_with_times(
    stop_location: str,
    destination: str,
    now: Optional[datetime] = None,
    limit: int = 3
) -> List[Dict]:
    """
    指定バス停から指定行き先への次のバスを取得（絶対時刻付き）

    Returns:
        [{"minutes": 3, "time": "07:15"}, {"minutes": 8, "time": "07:20"}, ...]
    """
    _load_all_data()

    config = get_config()

    if now is None:
        now = datetime.now()

    today = now.strftime("%Y%m%d")
    current_time = timedelta(hours=now.hour, minutes=now.minute, seconds=now.second)

    stop_config = config.bus_stops.get(stop_location)
    if not stop_config:
        return []

    dest_patterns = config.destinations.get(destination, [])
    if not dest_patterns:
        return []

    calendar_dates = _cache["calendar_dates"]
    trip_services = _cache["trip_services"]
    stop_times = _cache["stop_times"]

    # フォールバック対応
    effective_date = _find_fallback_date(today, calendar_dates)
    if effective_date is None:
        return []
    today_services = set(calendar_dates.get(effective_date, []))
    candidates = []
    target_stop_ids = set(stop_config.stop_ids)

    for st in stop_times:
        if st["stop_id"] not in target_stop_ids:
            continue

        headsign = st["headsign"]
        if not any(pattern in headsign for pattern in dest_patterns):
            continue

        service_id = trip_services.get(st["trip_id"])
        if service_id not in today_services:
            continue

        dep_time = parse_time(st["departure_time"])
        if dep_time is None:
            continue

        if dep_time < current_time:
            continue

        diff = dep_time - current_time
        minutes = int(diff.total_seconds() / 60)

        # 時刻を HH:MM 形式に変換（24時超え対応）
        total_minutes = int(dep_time.total_seconds() / 60)
        hours = (total_minutes // 60) % 24
        mins = total_minutes % 60
        time_str = f"{hours:02d}:{mins:02d}"

        candidates.append({"minutes": minutes, "time": time_str})

    candidates.sort(key=lambda x: x["minutes"])
    return candidates[:limit]


def get_bus_data(now: Optional[datetime] = None) -> Dict[str, List[int]]:
    """
    全てのバス情報を取得

    Returns:
        {
            "stop_a_destination_1": [3, 8, 15],
            "stop_a_destination_2": [5, 12],
            ...
        }
    """
    config = get_config()

    if now is None:
        now = datetime.now()

    data = {
        "updated_at": now.isoformat(),
    }

    # 設定されたルートごとにデータ取得
    for route in config.routes:
        key = f"{route.stop}_{route.destination}"
        data[key] = get_next_buses(route.stop, route.destination, now)

    return data


if __name__ == "__main__":
    # テスト
    data = get_bus_data()
    config = get_config()

    print("=== バス情報 ===")
    print(f"取得時刻: {data['updated_at']}")
    print()

    for route in config.routes:
        key = f"{route.stop}_{route.destination}"
        print(f"  {route.display_name}: {data.get(key, [])}")
