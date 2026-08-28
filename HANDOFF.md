# 開発引き継ぎ

確認日: 2026-08-29 JST。再開時は最新main・PRコメント・Actionsを確認してください。
この文書は確認時点の記録で、以後の定期実行成功を保証するものではありません。

## mainへの反映状況

対象: https://github.com/hongsan13/discord-market-bot

| 内容 | PR | マージcommit |
| --- | --- | --- |
| v7段階買い増し・利益保護 | [#1](https://github.com/hongsan13/discord-market-bot/pull/1) | `40a0abfe6b2c5264fc20dea1f667d385cc692b4f` |
| Windows開発環境・安全な検証 | [#3](https://github.com/hongsan13/discord-market-bot/pull/3) | `10fe0bfd123a6eb9407ce95f6445a16765ae0cec` |
| 週報PDF・Discord定期配信 | [#2](https://github.com/hongsan13/discord-market-bot/pull/2) | `9e45167e4b77858624b350b4d849e86bb382b29a` |

機能導入後の確認対象mainは `9e45167e4b77858624b350b4d849e86bb382b29a`。
戦略は `v7_scale_in_profit_guard`、ペーパートレード専用です。
今後もマージはPRごとの明示承認後に行います。以前の「PR #2・#3未マージ」という記録は過去の状態です。

## 確認済みのこと

- v7反映後の[日次Actions](https://github.com/hongsan13/discord-market-bot/actions/runs/33172233620)で
  Bot・日次Discord送信・state保存の成功記録があります。
- [開発環境CI](https://github.com/hongsan13/discord-market-bot/actions/runs/33214469050)のWindows / Python 3.11が成功。
  これは週報マージ前の検証です。
- 週報・開発環境の統合後mainでPython 3.12の `scripts/setup_dev.py --skip-install` が成功。
  依存関係チェック、96オフラインテスト、日本語PDF生成テストが成功しています。
- 導入前後でBot本体・運用JSON・全履歴・ダッシュボード・既存日次ワークフローに差分なし。
- **Weekly market review newspaper** のワークフロー状態は `active`。
  毎週土曜10:00 JSTの設定がmainに反映されています。

## 未確認・次の確認

- 確認時点では週報の実行履歴はありません。週報のUbuntu / Python 3.11本番実行と、
  実際のDiscord週報配信成功は未確認です。日次Discord成功と混同しないでください。
- 土曜10:00 JSTの定期実行後、[週報Actions](https://github.com/hongsan13/discord-market-bot/actions/workflows/weekly_market_review.yml)の
  成否・artifactとDiscord受信を確認します。手動実行・送信は別途明示承認が必要です。
- タイムアウト等では投稿済みの可能性があるため、受信状況を確認せず再実行しません。
- 週次Codexレビューはラップトップの既存1件（土曜09:00 JST）のままです。
  デスクトップへの複製・移行はしていません。PC・アプリの起動、認証・権限等が必要です。
- テスト成功は戦略の収益性や無人配信の成功を示すものではありません。

## 2台での再開

1. [AGENTS.md](AGENTS.md)、[DEVELOPMENT.md](DEVELOPMENT.md)、最新PRコメントを読む。
2. `git status --short --branch` とGitHubの最新main・PR・Actionsを確認。
3. 新規開発は最新mainから専用ブランチを作成。進行中の作業は引き継ぎPRの同じブランチを使う。
4. dirty状態での上書き・自動stash・強制更新は行わず、更新には `git pull --ff-only` を使う。
5. `.venv/Scripts/python.exe scripts/check_dev.py` で検証。Bot起動や運用ワークフローの試験実行はしない。
6. 終了時は確認した変更だけをcommit・作業ブランチへpushし、PRにcommit・テスト・残り・次の1手を記録。

運用stateは日次Actionsが更新します。古いJSONで上書きせず、手動同期・リセットしないでください。
秘密情報・端末固有のパス・認証設定を公開ドキュメントやPRへ記録する必要はありません。
