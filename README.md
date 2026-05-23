# Discord Market Paper Trading Bot

AI/半導体インフラ系の監視レポートを毎日Discordへ投稿し、100万円ペーパートレードの履歴をJSONに保存する最小構成。

## できること

- Discord Webhookへ21時レポートを投稿
- 半導体、メモリ/ストレージ、装置、データセンター電力/冷却、サイバー、防衛/宇宙を監視
- 100万円の仮想ペーパートレードを記録
- 9:00〜翌6:00の間、15分ごとに急落監視
- 9:00〜翌6:00の間、1時間ごとに仮想売買判断
- 急落条件に該当した場合、Discordへ緊急アラートを投稿
- data/reports.json に履歴保存
- docs/data/reports.json にGitHub Pages用データを保存
- docs/index.html でレポート履歴と資産状況を可視化

## 注意

これは投資助言・自動売買ではない。実際の注文は一切出さない。
値動き予想は保証ではなく、公開情報ベースのシナリオ整理である。
勤務先・競合・取引先の個別株売買は社内規程とインサイダー規制を必ず確認すること。

---

## 1. Discord Webhook URLを作る

Discordで投稿したいチャンネルを右クリック  
→ 編集  
→ 連携サービス  
→ Webhook  
→ 新しいWebhook  
→ URLをコピー

## 2. ローカル実行

```bash
conda create -n marketbot python=3.11 -y
conda activate marketbot
pip install -r requirements.txt
```

PowerShellでDiscord Webhook URLを環境変数に入れる。

```powershell
$env:DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/xxxxx/yyyyy"
```

実行:

```bash
python market_discord_bot.py
```

Discordへの投稿条件を満たす場合はDiscordに投稿され、`data/reports.json` と `docs/data/reports.json` が更新される。

ただし、通常レポートは21時枠のみ投稿する。  
21時以外の実行では、監視・急落アラート・ペーパートレード更新のみ行われる。

---

## 3. GitHub Actionsで自動実行

1. このフォルダをGitHubリポジトリにアップロード
2. GitHubの Settings → Secrets and variables → Actions → New repository secret
3. `DISCORD_WEBHOOK_URL` という名前でWebhook URLを登録
4. Actionsを有効化
5. `.github/workflows/daily_discord_report.yml` が自動実行

現在の実行スケジュール:

```yaml
on:
  schedule:
    - cron: "*/15 0-20 * * *"
    - cron: "0 21 * * *"
  workflow_dispatch:
```

これはUTC基準なので、日本時間では以下の動作になる。

- 9:00〜翌6:00まで15分ごとに監視
- 毎時00分ごろに仮想売買判断
- 21:00ごろに通常レポート投稿
- 急落条件に該当した場合は緊急アラート投稿

手動実行も可能。GitHub Actionsの画面から `Run workflow` を押す。

---

## 4. ダッシュボード

GitHub Pagesで公開する場合は、Pagesの公開元を `main / docs` にする。

表示用ファイル:

```text
docs/index.html
```

表示用データ:

```text
docs/data/reports.json
```

ダッシュボードでは、以下を表示する。

- 総資産
- 損益
- 損益率
- 前回比
- 現金
- 保有評価額
- USD/JPY
- 最終更新時刻
- 監視銘柄一覧
- 保有銘柄
- 最近の判断

うまく読めない場合は、`docs/data/reports.json` のパスやGitHub Pagesの公開元設定を確認する。

---

## 5. 監視銘柄

デフォルト:

- WDC
- SNDK
- 285A.T
- 8035.T
- 6857.T
- 6146.T
- ASML
- AMAT
- MU
- NVDA
- TSM
- VRT
- ETN
- CRWD
- PANW
- 7011.T
- 7012.T
- 7013.T
- STX
- AMD
- AVGO
- SMCI
- DELL
- MSFT
- GOOGL
- AMZN
- ANET

変更したい場合は `market_discord_bot.py` の `WATCHLIST` を編集。

---

## 6. ファイル構成

```text
discord-market-bot/
├── market_discord_bot.py
├── requirements.txt
├── README.md
├── data/
│   └── reports.json
├── docs/
│   ├── index.html
│   └── data/
│       └── reports.json
└── .github/
    └── workflows/
        └── daily_discord_report.yml
```

---

## 7. requirements.txt

```txt
requests
yfinance
```

---

## 8. 実売買について

このBotは実売買を行わない。

以下は扱わない。

- 証券会社API
- kabuステーションAPI
- 自宅PC常駐Bot
- 自動注文
- 半自動注文
- 注文用APIキー
