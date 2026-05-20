# Discord Market Paper Trading Bot

AI/半導体インフラ系の監視レポートを毎日Discordへ投稿し、100万円ペーパートレードの履歴をJSONに保存する最小構成。

## できること

- Discord Webhookへ21時レポートを投稿
- 半導体、メモリ/ストレージ、装置、データセンター電力/冷却、サイバー、防衛/宇宙を監視
- 100万円の仮想ペーパートレードを記録
- 10:00 / 13:00 / 16:00の仮想判断をレポート化
- 翌営業日の方向感を「強気/中立/弱気/高ボラ警戒」で出力
- data/reports.json に履歴保存
- web/index.html でレポート履歴を可視化

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

`.env.example` を `.env` にコピーして、Discord Webhook URLを入れる。

```bash
copy .env.example .env
```

`.env`:

```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxxxx/yyyyy
STARTING_CAPITAL_JPY=1000000
```

実行:

```bash
python market_discord_bot.py
```

Discordに投稿され、`data/reports.json` が更新される。

---

## 3. GitHub Actionsで毎日21時に自動実行

1. このフォルダをGitHubリポジトリにアップロード
2. GitHubの Settings → Secrets and variables → Actions → New repository secret
3. `DISCORD_WEBHOOK_URL` という名前でWebhook URLを登録
4. Actionsを有効化
5. `.github/workflows/daily_discord_report.yml` が毎日21:00 JSTに実行

手動実行も可能。GitHub Actionsの画面から `Run workflow` を押す。

---

## 4. ダッシュボード

ローカルなら `web/index.html` をブラウザで開く。  
GitHub Pagesで公開する場合は、Pagesの公開元を `main / web` にする。

ただし、GitHub Pagesから `../data/reports.json` を読むには、リポジトリ構成やPages設定によってパス調整が必要な場合がある。
うまく読めない場合は `data/reports.json` の中身を画面のJSONインポート欄へ貼り付ければよい。

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

変更したい場合は `market_discord_bot.py` の `WATCHLIST` を編集。
