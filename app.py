from flask import Flask, jsonify, request
from datetime import datetime
import requests
import threading
from config import get_config
from gtfs_parser import get_bus_data as get_gtfs_bus_data, get_next_buses_with_times

app = Flask(__name__)

# Load configuration
config = get_config()


def minutes_to_speech(n):
    """数字を「〜ふん/ぷん」の正しい読みに変換"""
    # 0〜9の読み方
    readings = {
        0: "ぜろふん",
        1: "いっぷん",
        2: "にふん",
        3: "さんぷん",
        4: "よんぷん",
        5: "ごふん",
        6: "ろっぷん",
        7: "ななふん",
        8: "はっぷん",
        9: "きゅうふん",
    }

    if n in readings:
        return readings[n]

    # 10以上はそのまま数字+分
    return f"{n}分"


def activate_lametric_app(package, widget):
    """LaMetricの指定アプリをアクティブにする"""
    url = f"http://{config.lametric.ip}:8080/api/v2/device/apps/{package}/widgets/{widget}/activate"
    try:
        requests.put(url, auth=("dev", config.lametric.api_key), timeout=5)
    except Exception as e:
        print(f"LaMetric activate error: {e}")


def get_bus_data():
    """
    GTFSデータからバス到着情報を取得
    """
    gtfs_data = get_gtfs_bus_data()

    result = {"updated_at": gtfs_data.get("updated_at", datetime.now().isoformat())}

    # Config から動的にキーを生成
    for route in config.routes:
        key = f"{route.stop}_{route.destination}"
        gtfs_key = f"{route.stop}_{route.destination}"
        result[key] = gtfs_data.get(gtfs_key, [])

    return result


@app.route("/")
def index():
    return jsonify({"status": "ok", "service": "bus-arrival-notifier"})


@app.route("/bus")
def get_bus():
    """バス情報をJSON形式で返す"""
    data = get_bus_data()
    return jsonify(data)


@app.route("/bus/speech")
def get_bus_speech():
    """Alexa用の音声テキストと画面表示用テキストを返す"""
    speech_parts = []  # 音声用（ひらがな）
    display_items = []  # 画面表示用（構造化データ）

    # まずデータを収集
    route_data = []
    for route in config.routes:
        buses = get_next_buses_with_times(route.stop, route.destination)
        if buses:
            route_data.append({
                "speech_name": route.speech_name,
                "display_name": route.display_name,
                "buses": buses,
                "first_minutes": buses[0]["minutes"]
            })

    # 最初のバスの残り時間でソート
    route_data.sort(key=lambda x: x["first_minutes"])

    # ソート順でspeech_partsとdisplay_itemsを生成
    for item in route_data:
        times_speech = "、".join(minutes_to_speech(b["minutes"]) for b in item["buses"])
        speech_parts.append(f"{item['speech_name']}は {times_speech}後")

        display_items.append({
            "route": item["display_name"],
            "buses": [{"time": b["time"], "minutes": b["minutes"]} for b in item["buses"]]
        })

    if not route_data:
        speech = "現在バスの情報がありません"
    else:
        speech = "。".join(speech_parts) + "です"

    return jsonify({
        "speech": speech,
        "display_items": display_items
    })


@app.route("/lametric")
def get_lametric():
    """LaMetric用のフォーマットで返す"""
    data = get_bus_data()

    result = {}

    for route in config.routes:
        key = f"{route.stop}_{route.destination}"
        if key in data and data[key]:
            result[key] = " ".join(map(str, data[key]))
        else:
            result[key] = "--"

    return jsonify(result)


@app.route("/lametric/activate", methods=["POST", "GET"])
def activate_bus_app():
    """バスアプリをアクティブにし、5分後に時計に戻す"""
    # バスアプリをアクティブに
    activate_lametric_app(
        config.lametric.bus_app.package,
        config.lametric.bus_app.widget
    )

    # 5分後に時計に戻すタイマーを設定
    def revert_to_clock():
        activate_lametric_app(
            config.lametric.clock_app.package,
            config.lametric.clock_app.widget
        )

    timer = threading.Timer(300, revert_to_clock)  # 300秒 = 5分
    timer.start()

    return jsonify({
        "status": "ok",
        "message": "Bus app activated, will revert to clock in 5 minutes"
    })


@app.route("/health")
def health():
    return jsonify({"status": "healthy"})


if __name__ == "__main__":
    app.run(
        host=config.server.host,
        port=config.server.port,
        debug=config.server.debug
    )
