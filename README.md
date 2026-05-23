# Discord Market Paper Trading Bot

GitHub Actions上で動作するDiscord市場監視Bot。  
AI、半導体、メモリ/ストレージ、半導体製造装置、データセンター電力/冷却、サイバーセキュリティ、防衛/宇宙関連銘柄を監視し、100万円ペーパートレードの履歴をJSONに保存する。

このBotは実売買を行わない。  

---

## できること

- Discord Webhookへ21時レポートを投稿
- 半導体、メモリ/ストレージ、装置、データセンター電力/冷却、サイバー、防衛/宇宙を監視
- 100万円の仮想ペーパートレードを記録
- 9:00〜翌6:00まで15分ごとに市場監視
- 9:00〜翌6:00まで1時間ごとに仮想売買判断
- 急落条件に該当した場合、Discordへ緊急アラートを投稿
- data/reports.json に履歴保存
- docs/data/reports.json にGitHub Pages用データを保存
- docs/index.html でレポート履歴と資産状況を可視化

---

## 注意

これは投資助言・自動売買ではない。実際の注文は一切出さない。  
値動き予想は保証ではなく、公開データを使った検証用のシナリオ整理である。

勤務先・競合・取引先の個別株売買は、社内規程とインサイダー規制を必ず確認すること。  
特に、Western Digital、SanDisk、Kioxia、Micron、半導体関連企業、防衛関連企業などを監視対象に含むため、実売買への転用は禁止する。

---

## 1. Discord Webhook URLを作る

Discordで投稿したいチャンネルを右クリック  
→ チャンネルの編集  
→ 連携サービス  
→ Webhook  
→ 新しいWebhook  
→ URLをコピー

作成したWebhook URLは、GitHub Secretsに保存する。

---

## 2. GitHub Secretsを設定する

GitHubリポジトリで以下を開く。

```text
Settings
→ Secrets and variables
→ Actions
→ New repository secret
