# Windows 11の2台で開発する

GitHubを共通の保管先とし、ラップトップとデスクトップに**別々のclone**を置きます。
実運用は引き続きGitHub Actionsです。ローカルでBot本体を起動する必要はありません。
同じブランチを2台で同時編集せず、引き継ぐときにcommit/pushします。

## 最初のセットアップ（両PCで各1回）

1. 両PCのCodexに同じアカウント/ワークスペースでログインします。
2. [Git for Windows](https://git-scm.com/install/windows) と
   [Python 3.11](https://docs.python.org/3.11/using/windows.html) を用意します。
   Python 3.12もこの開発ツールの対象ですが、Actionsと揃えるなら3.11を使います。
   古いPythonを削除・置換する必要はありません。インストール後はPowerShellを開き直します。
3. OneDrive/Dropboxの同期対象外のフォルダを選びます。次の例は `C:\Dev` です。
   権限がなければ書き込み可能な同期対象外フォルダに置き換えてください。

```powershell
git --version
py -3.11 --version
New-Item -ItemType Directory -Force C:\Dev
Set-Location C:\Dev
git clone https://github.com/hongsan13/discord-market-bot.git
Set-Location discord-market-bot
```

既に同名フォルダがある場合、上書きや削除はせず、そのcloneの変更状況を確認します。
2026-08-29 JST時点で、環境整備PR #3と週報PR #2はmainへマージ済みです。
初期セットアップには最新mainを使い、導入用の旧ブランチへ切り替える必要はありません。
進行中の開発を引き継ぐ場合だけ、最新PRに記録された作業ブランチを使います。
既存cloneに変更があるときは勝手に捨てず停止してください。

```powershell
py -3.11 scripts/setup_dev.py
# Python 3.12を選んだ場合だけ py -3.12 scripts/setup_dev.py
```

このコマンドは当該clone内に `.venv` を作り、開発依存関係をインストールして
構文チェックとオフラインテストを実施します。グローバルPython、BotのJSON、
Discord、運用スケジュールは変更しません。ActivationやExecutionPolicy変更は不要です。
既存 `.venv` が不完全/別バージョンなら削除せず停止します。

直接依存の検証版は `requirements-dev.txt` に固定しています。間接依存まで完全固定した
lockファイルではありません。実際に導入した版は各PCの `.local/installed-packages.txt`
に保存されます。運用の `requirements.txt` は変更していません。

4. Codexでこの `discord-market-bot` フォルダをプロジェクトとして開きます。
   日付付きの一時フォルダや `.venv` をプロジェクトにしないでください。
5. GitHubへの書き込みは各PCで認証します。CodexのGitHub接続と、ターミナルのGit認証は
   別です。Git for Windowsの認証画面を使い、トークンやWebhookをチャットへ貼らないでください。
   初回commitで名前/メールを求められた場合は、自分の値をリポジトリ単位で設定します。

## 毎回の安全なテスト

```powershell
.\.venv\Scripts\python.exe scripts/check_dev.py
```

v7テストを必須とし、`weekly/` があるブランチでは週報テストも実行します。
現在のmainには週報も含まれ、2026-08-29 JSTの検証ではPython 3.12で96テストが成功しました。
通信をブロックし、子プロセス内のDiscord/GitHub/OpenAIの認証用環境変数を外します。
保護対象のJSON/Pages/既存ワークフローのハッシュも実行前後で比較します。
任意の未知のコードに対するセキュリティサンドボックスではないため、未確認のPRを
そのまま実行しないでください。`python market_discord_bot.py` は実行しません。

`Development checks` CIもWindows runner/Python 3.11で同じセットアップを検証します。
PRのPython/依存関係/このCI設定の変更時に動き、Secretsなし・リポジトリ読取権限のみです。
定期実行やBot起動はありません。Windows runnerはWindows 11実機そのものではありません。

## 別PCへ移るとき

作業終了側ではテスト後、変更したファイルだけを指定してstageし、専用ブランチに
commit/pushします。`git add .` は使いません。PRのコメントに以下を記録します。

```text
担当端末: laptop / desktop
ブランチ:
最新commit:
確認済みテスト:
未完了・注意点:
次の1手:
```

push後に `git status --short --branch` で未送信変更がないことを確認します。
未コミットや未pushの変更は他のPCに届きません。移動後は元のPCで編集を続けないでください。

再開側は、まず `git status --short --branch`。未コミット変更があれば停止して確認します。
問題なければ、PRに記録された**同じブランチ名**を選んで更新します。

```powershell
git fetch origin
# 初めて取得する場合:
# git switch --track origin/<引き継ぎブランチ>
# 既に取得済みの場合:
# git switch <引き継ぎブランチ>
git pull --ff-only
.\.venv\Scripts\python.exe scripts/check_dev.py
```

分岐して `--ff-only` が失敗したら、force push/resetせず双方のcommitを確認します。
新しい作業は更新済みmainから新しいfeatureブランチを作成し、PRで反映します。
mainへの直接pushや自動マージはしません。

## データ・秘密情報・定期実行

- `data/reports.json` と `docs/data/reports.json` は運用履歴です。最新mainから取得し、
  古いPCやダウンロード済みJSONで上書きしません。ローカル変更を開発PRに混ぜません。
- `.venv` は各PCで作り直します。`.git`、`.codex`、認証情報も同期サービスでコピーしません。
- Discord WebhookはGitHub ActionsのSecretのまま維持。開発PCへの配布は不要です。
- 土曜09:00 JSTのCodex週次レビューは、現在のラップトップ上の既存設定を1件だけ維持します。
  デスクトップに同じ自動化を作らないでください。移行するなら元の実行を停止し、
  新しい端末での認証/実行を確認する別作業とします。今回は移行していません。
- 土曜10:00 JSTの週報PDF配信はPR #2のマージで導入済みです。
  2026-08-29 JST確認時点でワークフローは有効ですが、実行履歴はなく実配信成功は未確認です。
  初回定期実行後のActions・Discord受信を確認してください。手動送信は別途明示承認が必要です。

## この環境ではRemote接続を使わない

ユーザー環境では `Control other devices` が利用できないため、今回の構成は
GitHubによる引き継ぎです。同じ会話が自動的に同期されることは前提にしません。
別PCのCodexには、対象リポジトリとブランチを伝え、`AGENTS.md`、`HANDOFF.md`、
最新のPRコメントを読ませて再開します。元のPCが停止していても、push済みの作業は
GitHubから取得できます。秘密情報やアプリ設定のフォルダごとコピーは不要です。

Remote機能の提供状況に関する参考:
[OpenAIの公式説明](https://learn.chatgpt.com/docs/remote-connections)
