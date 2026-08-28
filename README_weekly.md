# 週次レビュー・Discord週報・新聞PDF

ペーパートレード用の補助機能です。Bot本体、運用JSON、既存のDiscord投稿、
GitHub Pages、既存Actionsスケジュールは変更しません。v6/v7のどちらのstateも読み取れます。

## 現在の状況

2026-08-29 JST確認。[PR #2](https://github.com/hongsan13/discord-market-bot/pull/2)はmainへマージ済みで、
**Weekly market review newspaper** は有効です。確認時点では週報の実行履歴はなく、
実際のDiscord週報配信成功は未確認です。導入済みと配信成功を区別してください。
v7（PR #1）と開発環境整備（PR #3）もmainへ反映済みです。

## 実行の分担

| 時刻（JST） | 実行場所 | 内容 |
| --- | --- | --- |
| 毎週土曜09:00 | ラップトップ上の既存Codexレビュー1件 | 最新レポート・市場一次資料・不具合を分析。必要なら最小修正とテスト、専用PRを作成 |
| 毎週土曜10:00 | GitHub Actions | 最新stateとPR・週次レビューIssueを読み取り、概要と新聞PDFをDiscordへ配信 |

分析結果は、タイトルが `[週次レビュー YYYY-MM-DD]` で始まるIssueに記録します。
冒頭を日本語の要旨とし、市場背景、修正内容、テスト結果、出典を続けます。
OWNER/MEMBER/COLLABORATORによるIssueだけを週次レビューとして採用します。
当日分がなければ「当日レビュー未確認」と表示します。未実施を「変更なし」と扱いません。

ローカルの定期分析には、PCとアプリの起動、GitHub接続、必要な権限が必要です。
無人実行で承認待ちになる場合もあります。PCが停止していてもGitHub側の配信は動きますが、
当日のAIレビューを実施できたことにはなりません。GitHubの定期実行時刻も遅延する場合があります。

## 初回配信の確認と運用

1. 土曜10:00 JSTの定期実行後、[週報Actions](https://github.com/hongsan13/discord-market-bot/actions/workflows/weekly_market_review.yml)の成否・artifactとDiscord受信を確認します。
2. 配信には既存のRepository secret `DISCORD_WEBHOOK_URL` を使います。開発PCへのコピーや値の公開は不要です。
3. 失敗時はログとDiscord受信状況を確認します。手動実行・再実行は実際に投稿するため、個別の明示承認が必要です。
4. 土曜09:00のCodexレビューはラップトップの既存1件を維持します。cloneやmainへのマージで自動作成されるものではなく、デスクトップへ複製しません。

今後の変更も専用ブランチ・PRで扱い、mainへの直接pushや未承認のマージは行いません。
変更不要の週は理由をレビューIssueに残し、1週間の損益だけで閾値を最適化しません。

## 新聞と集計

- 2ページの日本語PDF: 資産推移、対象期間/累計の損益、現金、売買、セクター、変更状況。
- セクターは最新記録の監視銘柄 `change_5d` を単純平均し、取得数を併記。市場指数ではありません。
- 期間損益は保存済みの基準観測から算出。厳密な7日間でないときは観測時刻の差を明記。
- 基準なし・基準が24時間超離れる・最新記録が36時間超古い場合は週次値を出しません。
- PRは提案中・クローズ・マージ済みを区別し、マージ先も表示。マージ済みと実行成功は別です。
- 外部市場ニュースは、Codexレビューが一次資料を確認してIssueに書いた場合だけ扱います。
  定型のActions集計自体はニュース検索やAI推論を行いません。本文全体・出典はIssueを参照してください。
- GitHub取得失敗・取得上限・データ欠測は警告し、未確認を成功と表示しません。

生成物は `weekly-output/newspaper.pdf`、`summary.txt`、`digest.json`。
Actions artifactとして90日保持し、PDFと概要を既存Discordチャンネルへ送ります。
PDFには日本語フォントを埋め込みます。元JSONと履歴は一切書き換えません。

## 安全性と失敗時の扱い

GitHub権限はcontents/pull-requests/issuesのreadのみ。PRトリガーは設けず、
default branchのコードだけを実行します。Webhook secretは最終送信ステップだけに渡します。
外部の本文はコードやPDFマークアップとして実行せず、メンションは無効化します。

Discord送信は確認応答付きの1回のみ。タイムアウトやサーバーエラー時は受理済みの可能性があるため、
自動再送しません。手動再実行する前にDiscordを確認してください。再実行による重複を完全には防げません。
未設定Webhook・送信エラーではジョブが失敗し、先に作成したartifactは確認できます。
ファイルは8MiB以下、メッセージはDiscordの文字数上限内に制限します。

## ローカル検証（送信なし）

まず[開発手順](DEVELOPMENT.md)に従って `.venv` を作成します。Windowsでは次を使います。

```powershell
.\.venv\Scripts\python.exe scripts/check_dev.py
```

送信なしのPDF見本が必要な場合だけ、既存の生成物を上書きしない新しい出力先を指定します。

```powershell
.\.venv\Scripts\python.exe -m weekly.report --state data/reports.json --output-dir weekly-output/preview-01 --preview
```

このコマンドは元JSONを書き換えず、Discord送信もGitHub情報取得も行いません。
見本の「GitHub変更情報は未取得」は正常です。日本語フォントが必要で、Windowsでは游明朝／メイリオを使用します。
Ubuntuの週報Actionsは `fonts-ipaexfont` を導入します。

テストは既存Botの運用処理や実Discord送信を呼ばず、通信をmockし、PDFを一時フォルダに生成します。
PR #2・#3反映後のmainでPython 3.12による96テスト（週報62件を含む）が成功しました。
開発環境整備のWindows / Python 3.11 CI成功記録はありますが、週報のUbuntu / Python 3.11本番実行・実配信は未確認です。

参考: [定期タスク](https://learn.chatgpt.com/docs/automations?surface=app) /
[Discord Webhook](https://docs.discord.com/developers/resources/webhook) /
[GitHub schedule](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
