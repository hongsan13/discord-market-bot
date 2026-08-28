# 開発引き継ぎ

確認日: 2026-08-29 JST。以下は確認時点の記録です。再開時に最新GitHubを再確認してください。

## 運用

- 対象: https://github.com/hongsan13/discord-market-bot
- ペーパートレードのみ。実売買コードは追加しません。
- mainの戦略: `v7_scale_in_profit_guard`。
- v7は [PR #1](https://github.com/hongsan13/discord-market-bot/pull/1) で反映済み。
- merge commit: `40a0abfe6b2c5264fc20dea1f667d385cc692b4f`。
- その後の [Actions実行](https://github.com/hongsan13/discord-market-bot/actions/runs/33172233620)
  でBot・日次Discord送信・state保存の成功を確認済み。Pagesも成功。
- 確認時のmain: `61a9bd9b4df869ab6ee4e8dd50d0eb38d6d3dcfc`。
- 運用stateはActionsが進めます。古い添付JSONで戻さないでください。

## 保留中

- [PR #2: 週次レビューの新聞PDFとDiscord配信を追加](https://github.com/hongsan13/discord-market-bot/pull/2)
  は未マージ。branch: `codex/weekly-market-newspaper-20260828`。
  head: `4ee0745751f2f32085c69316c9ec83852856c8d8`。62テスト成功、PDFの2ページ描画確認済み。
  実Discord週報配信は未確認。v7の日次Discord成功と混同しないこと。
- mainへの反映はPRごとにユーザー承認が必要です。PR #2を自動マージしません。
- 週次Codexレビューは既存ラップトップで土曜09:00 JSTの1件だけ。
  デスクトップへの移行/複製はしていません。PCとアプリの起動が必要です。

## 2台での再開

1. `AGENTS.md` と `DEVELOPMENT.md` を読む。
2. GitHubの最新main/PR/Actionsとローカルのdirty状態を確認。
3. 作業対象のfeatureブランチを選ぶ。運用stateを手動同期しない。
4. `scripts/check_dev.py` で安全に検証する。
5. 終了時はPRコメントにブランチ/commit/テスト/残り/次の1手を残す。

チャット履歴が別PCで見えなくても、このファイルとPRから作業を再開できます。
