# Bus Arrival Notifier

バス到着情報を取得し、LaMetric Time や Alexa に配信する Flask API サーバーです。

## 機能

- GTFS 静的データからバス時刻表を解析
- LaMetric Time への表示連携
- Alexa スキル用 API（音声読み上げ + Echo Show 表示）
- GTFS データの自動更新（毎朝4時）

## エンドポイント

| エンドポイント | 用途 |
|---------------|------|
| `/` | サービスステータス |
| `/bus` | バス情報 JSON |
| `/bus/speech` | Alexa 用音声テキスト + 画面表示データ |
| `/lametric` | LaMetric Poll 用 |
| `/lametric/activate` | LaMetric アプリ表示 + 5分後時計に戻る |
| `/health` | ヘルスチェック |

## セットアップ

### 1. リポジトリをクローン

```bash
git clone https://github.com/your-username/bus-arrival-notifier.git
cd bus-arrival-notifier
```

### 2. Python 仮想環境を作成

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# または
.\venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

### 3. 設定ファイルを作成

```bash
cp config/config.example.yaml config/config.yaml
```

`config/config.yaml` を編集して、以下を設定:

- **lametric**: LaMetric Time の IP アドレス、API キー、アプリ ID
- **odpt**: ODPT API キー（https://developer.odpt.org/ で取得）
- **bus_stops**: 監視するバス停の GTFS stop_id
- **destinations**: 行先のヘッドサイン（方向幕）パターン
- **routes**: 表示する路線の定義

### 4. GTFS データをダウンロード

```bash
python update_gtfs.py
```

### 5. サーバーを起動

```bash
python app.py
```

サーバーは `http://localhost:5000` で起動します。

## Raspberry Pi へのデプロイ

### 1. コードを転送

```bash
scp -r bus-arrival-notifier pi@raspberrypi:/home/pi/
```

### 2. Pi 側でセットアップ

```bash
ssh pi@raspberrypi
cd /home/pi/bus-arrival-notifier

# 仮想環境作成
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 設定ファイルをコピー・編集
cp config/config.example.yaml config/config.yaml
nano config/config.yaml

# GTFS データをダウンロード
python update_gtfs.py
```

### 3. systemd サービスを登録

```bash
# サービスファイルをコピー
sudo cp systemd/bus-arrival-notifier.service /etc/systemd/system/
sudo cp systemd/bus-gtfs-update.service /etc/systemd/system/
sudo cp systemd/bus-gtfs-update.timer /etc/systemd/system/

# サービスを有効化・起動
sudo systemctl daemon-reload
sudo systemctl enable bus-arrival-notifier
sudo systemctl start bus-arrival-notifier

# GTFS 自動更新タイマーを有効化
sudo systemctl enable bus-gtfs-update.timer
sudo systemctl start bus-gtfs-update.timer
```

### 4. ステータス確認

```bash
# サービス状態
sudo systemctl status bus-arrival-notifier

# ログ確認
sudo journalctl -u bus-arrival-notifier -f

# タイマー確認
sudo systemctl list-timers | grep gtfs
```

## 外部公開（Cloudflare Tunnel）

### Quick Tunnel（一時的）

```bash
cloudflared tunnel --url http://localhost:5000
```

### Named Tunnel（固定 URL）

```bash
# トンネル作成（初回のみ）
cloudflared tunnel create bus-notifier

# 設定ファイル作成
cat > ~/.cloudflared/config.yml << EOF
tunnel: bus-notifier
credentials-file: /home/pi/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: bus.your-domain.com
    service: http://localhost:5000
  - service: http_status:404
EOF

# DNS 設定
cloudflared tunnel route dns bus-notifier bus.your-domain.com

# サービスとして実行
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

## 設定ファイルの場所

設定ファイルは以下の順序で検索されます:

1. `config/config.yaml`（プロジェクトディレクトリ）
2. `/etc/bus-arrival-notifier/config.yaml`（システム全体）
3. `~/.config/bus-arrival-notifier/config.yaml`（ユーザーホーム）

## ライセンス

MIT License
