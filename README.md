# Discord Market Paper Trading Bot

日本株・米国株の27銘柄を監視し、初期資金100万円のペーパートレード、
Discordへの日次・急落通知、週報PDF、GitHub Pagesのダッシュボードを提供します。
**実際の注文は出しません。運用はGitHub Actions、各PCは開発・検証用です。**

## 現在の導入状況

2026-08-29 JST確認。導入済みであることと、配信が成功したことは区別します。

| 項目 | 状況 |
| --- | --- |
| 売買戦略v7 | [PR #1](https://github.com/hongsan13/discord-market-bot/pull/1)でmainへ反映済み。戦略名は `v7_scale_in_profit_guard` |
| 日次Bot・Discord・履歴保存 | v7反映後の[実行成功記録](https://github.com/hongsan13/discord-market-bot/actions/runs/33172233620)あり。最新の成否はActionsで確認 |
| 週報PDF・Discord配信 | [PR #2](https://github.com/hongsan13/discord-market-bot/pull/2)でmainへ反映済み。ワークフローは有効。確認時点では実行履歴がなく、実配信成功は未確認 |
| Windows開発環境 | [PR #3](https://github.com/hongsan13/discord-market-bot/pull/3)でmainへ反映済み。Python 3.11 / 3.12対応 |
| オフライン検証 | PR #2・#3反映後のmainで96テスト成功。開発環境CIのWindows / Python 3.11成功記録もあり |
| 週次Codexレビュー | ラップトップ上の既存1件を維持。週報配信とは別の仕組み。デスクトップへ複製しない |

最新状態は[Actions](https://github.com/hongsan13/discord-market-bot/actions)、
[PR](https://github.com/hongsan13/discord-market-bot/pulls)、[引き継ぎメモ](HANDOFF.md)を確認してください。
初回の週報配信は定期実行後にActionsとDiscordの両方で確認します。

## できること

### 市場監視・仮想売買

- 半導体・AI、メモリ／ストレージ、データセンター、サイバー、防衛・宇宙などを監視。
- 株価・騰落率・USD/JPYを取得し、円換算の資産、現金、保有銘柄、実現損益、判断履歴を保存。
- 相場・セクターの強弱、モメンタム、過熱、反発条件から買付候補を選ぶ。
- 最大5銘柄、銘柄・セクター別の上限、相場に応じた現金確保、買付回数制限を適用。
- 売却後の再購入待機、損切り、一部利確、建値保護、トレーリング売却に対応。
- v7では条件を満たすS/A銘柄へ最大3回の段階的な買い増しと、中間的な利益保護を追加。
- 仮想約定にはスプレッド・約定ずれ・為替コストの概算を反映。

詳細は[v7の仕様](README_v7.md)と[基盤となるv6の仕様](README_v6.md)を参照してください。
格付けと監視対象はコード内の設定です。戦略の収益性や損失抑制効果は保証されません。

### 通知・ダッシュボード・週報

- 日次Discordレポートと、急落条件に該当したときの緊急アラート。
- `docs/index.html` のダッシュボードで総資産、損益、現金、保有銘柄、監視銘柄、最近の判断を表示。
- 2ページの日本語週報PDFと概要をDiscordへ配信。資産推移、期間／累計損益、売買、セクター、PR・レビュー状況を掲載。
- 週報生成物は `newspaper.pdf`、`summary.txt`、`digest.json`。Actions artifactとして90日保存。

週報のセクター値は監視銘柄の集計で、市場指数ではありません。履歴不足・古いデータ・取得失敗を警告し、
当日のレビューIssueがない場合は「当日レビュー未確認」と表示します。
外部ニュースやAI分析を週報ワークフロー自体が行うわけではありません。
詳しくは[週報の仕様・確認手順](README_weekly.md)を参照してください。

## 実行スケジュール

すべて日本時間（JST）です。GitHubの定期実行には遅延があり、定刻の実行・配信は保証されません。

| 時刻・条件 | 実行場所 | 内容 |
| --- | --- | --- |
| 毎日09:00〜翌05:45の15分刻み＋06:00 | GitHub Actions | 市場・急落監視 |
| 各時間帯で最初に実行されたとき | 日次Bot内 | 1時間枠につき1回の仮想売買判断 |
| 毎日21時台 | 日次Bot内 | 当日未送信なら通常Discordレポート |
| 急落条件に該当したとき | 日次Bot内 | 再通知の待機時間を考慮してアラート |
| 毎週土曜09:00 | ラップトップの既存Codexレビュー | 分析、必要に応じた修正提案・PR。PCとアプリの起動・認証等が必要 |
| 毎週土曜10:00 | GitHub Actions | 最新state・PR・週次レビューIssueから週報PDFを生成・配信 |

設定は[日次ワークフロー](.github/workflows/daily_discord_report.yml)と
[週報ワークフロー](.github/workflows/weekly_market_review.yml)を参照してください。
PCが停止していてもActions側の処理は実行できますが、ラップトップのレビュー実施を意味しません。

## Windowsで開発を始める

最初に[AGENTS.md](AGENTS.md)、[DEVELOPMENT.md](DEVELOPMENT.md)、[HANDOFF.md](HANDOFF.md)と最新PRコメントを読みます。
Git for WindowsとPython 3.11（なければ3.12）を用意し、OneDrive等の同期対象外に独立したcloneを作成してください。
以下は**同名フォルダが存在しない場合だけ**の例です。既存cloneや未コミット変更は削除・上書きしません。

```powershell
git --version
py -3.11 --version
New-Item -ItemType Directory -Force C:\Dev
Set-Location C:\Dev
git clone https://github.com/hongsan13/discord-market-bot.git
Set-Location discord-market-bot
py -3.11 scripts/setup_dev.py
```

Python 3.12を選ぶ場合は `py -3.12 scripts/setup_dev.py` を使います。
版を省略した `py` で古いPythonを起動しないでください。`C:\Dev` に権限がなければ、書き込み可能な同期対象外の場所を選びます。
環境整備・週報はmainに含まれるため、導入用の旧ブランチへ切り替える必要はありません。

セットアップはclone内の `.venv` に依存を導入し、構文チェックとオフラインテストを実行します。
既存の不完全な `.venv` は削除せず停止します。ActivationやExecutionPolicyの変更は不要です。
Codexではcloneのルートフォルダをプロジェクトとして開きます。

### 毎回の安全なテスト

```powershell
.\.venv\Scripts\python.exe scripts/check_dev.py
```

ネットワーク接続をブロックし、認証用環境変数を除いた状態でv7・週報・開発ツールを検証します。
保護対象のJSON・ダッシュボード・既存日次ワークフローのハッシュも比較します。
未知のコードを隔離する完全なサンドボックスではないため、取得した変更は実行前に確認してください。
開発依存の直接バージョンは `requirements-dev.txt`、実際の導入一覧は各cloneの `.local/installed-packages.txt` にあります。

**開発確認のために `market_discord_bot.py` を起動したり、運用Actionsを手動実行したりしないでください。**
Discord Webhookは開発PCへ配布せず、既存のGitHub Actions Secretを使います。

## PC切替・運用データの保護

- 各PCに独立cloneを置き、`.git`、`.venv`、`.codex`、`.env`、認証情報を同期サービスで共有しない。
- 作業終了側でテストし、確認した変更ファイルだけをcommit・作業ブランチへpushして、PRに残り作業を記録する。
- 再開側はdirty状態と最新PRを確認し、同じ作業ブランチを `git pull --ff-only` で更新する。同じブランチを2台で同時編集しない。
- mainへ直接pushせず、変更は専用ブランチとPRで扱う。マージはPRごとの明示承認後に行う。
- `data/reports.json` と `docs/data/reports.json` は保護対象の運用履歴。古い添付JSONや別PCのコピーで戻さず、stateをリセットしない。
- 通常の履歴更新は日次Actionsが行う。週報は読み取り専用で、売買・state更新を行わない。
- 週報のタイムアウト後は受理済みの可能性がある。Discord受信状況を確認せず再実行しない。
- CodexのGitHub接続とターミナルのGit認証は別。各PCで認証し、トークン・パスワード・WebhookをGitやチャットへ貼らない。

## 主なファイル

| ファイル／ディレクトリ | 役割 |
| --- | --- |
| `market_discord_bot.py` | 市場監視・v7仮想売買・日次通知 |
| `data/reports.json` / `docs/data/reports.json` | 運用履歴とPages用データ |
| `docs/index.html` | ダッシュボード（Pagesは既存の `main / docs` 構成を維持） |
| `weekly/` | 週報集計・PDF生成・明示的なDiscord配信・テスト |
| `scripts/setup_dev.py` / `scripts/check_dev.py` | 開発環境作成・安全な検証 |
| `tests/` | v7・開発ツールのテスト |
| `.github/workflows/` | 日次運用、週報配信、開発チェック |
| `README_v6.md` / `README_v7.md` | 戦略の設計記録。記載された導入時の検証状況は過去のもの |
| `README_weekly.md` / `DEVELOPMENT.md` / `HANDOFF.md` | 週報仕様・開発手順・最新の引き継ぎ記録 |

このプロジェクトはペーパートレード専用です。証券会社API・実注文・注文用APIキーは扱いません。
