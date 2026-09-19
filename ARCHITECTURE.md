# 構成判断と公式情報

調査：2026-09-18〜19 JST。現在の公式情報を確認して実装しました。リンクやサービス仕様の永続性は保証されないため、取得先変更は異常として検出します。

## 比較

|構成|個人利用・費用|秘密情報・閲覧制御|Python/PDF・保守|判断|
|---|---|---|---|---|
|GitHub Actions + Pages|公開リポジトリ・標準runnerを無料枠で利用。AI従量課金|SecretsをActionsだけに渡す。通常Pagesは公開閲覧|通常のPython環境でPDF処理。DBも常駐サーバーも不要|公開レポートなら第一候補を採用|
|Actions + Cloudflare Pages + Access|静的配信は無料枠あり。アカウント・認証設定が増える|Access等で本人だけの閲覧に対応可能。全配信ドメインを保護する設定が必要|PythonはActionsに置くと単純。公開先の接続情報が追加|非公開閲覧が必須なら候補|
|Cloudflare Workers Cron + ストレージ|Cronは可能だがCPU・ストレージなど別の制約がある|Worker secretsを使える|Python PDF処理をそのまま移すより設計変更が増える|Phase 1で複雑化するため不採用|
|Vercel Functions + Cron|Hobbyはcronごとに1日1回、時刻精度は1時間幅。朝夕は別cronで構成可能|環境変数は使える。閲覧制御は別途検討|PDF処理時間と成果物保存を設計する必要がある|今回の静的配信用途では優位性が小さい|

静的なGitHub Pagesだけでは取得・PDF処理・OpenAI呼び出しは実行できません。GitHub Actionsに処理を分離することで、要件のクラウド自動実行とスマホ閲覧を実現します。公開範囲はユーザーの回答待ちで、まだ公開していません。

## 気象庁の取得経路

公式の [気象の専門家向け資料集](https://www.jma.go.jp/jma/kishou/know/expert/) に「短期予報解説資料」のリンクがあり、03:40頃・15:40頃の更新と、05時・17時発表の天気予報向け資料であることが説明されています。

実際にリンクをたどって確認した現在のPDFは [kaisetsu_tanki_latest.pdf](https://www.data.jma.go.jp/yoho/data/jishin/kaisetsu_tanki_latest.pdf) です。コードはこのPDF名を組み立てず、毎回公式ページのリンクを読みます。公式ページのパスを設定の起点とし、曖昧な候補や外部ドメインへの遷移は停止します。

この配信は現在利用できる**公式Webページの最新版リンク**です。バージョン付き公開APIや配信SLAがあると確認したものではありません。同じURLの内容が差し替わるため、PDF本文の発表日時とSHA-256の組み合わせで版を区別します。HTTPのLast-Modifiedや取得時刻を発表時刻の代わりにはしません。

公式ページの高層天気図・FAX天気図リンクは現在ともに [数値予報天気図](https://www.jma.go.jp/bosai/numericmap/) へつながります。Phase 1ではリンクを保存して閲覧を案内し、未取得の500/700/850hPa図をAIが見たことにはしません。

## PDFとOpenAI

[OpenAI公式 File inputs](https://developers.openai.com/api/docs/guides/file-inputs) は、Vision対応モデルへのPDF入力では抽出テキストとページ画像をモデルへ渡すと説明しています。このため、1リクエストでPDFをbase64の`input_file`として送り、文字の多い図に向けて`detail=high`を指定します。ローカル抽出したページ別テキストを併記し、原文照合に利用します。PDF画像を別途Visionリクエストで重複送信する方式は採用しません。

ブラウザ表示用にはpypdfium2でページ画像を生成します。原PDFと同じ版を保存し、原資料の図・表とAI解説を見比べられます。

[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) の`text.format`とJSON Schemaを使用します。形式が正しいだけでは気象学的に正しいと保証されないため、根拠一致・日付・全14航空コード等をローカルでも検証します。本文・図の解釈の意味的な検証と実モデルの品質評価は、API接続後の実データ検証が必要です。

初期モデル候補 [GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini) は画像入力対応で、確認時の標準単価は入力$0.40 / 出力$1.60（各100万token）です。モデルは環境変数で変更でき、利用不可時に勝手な置換はしません。確認時点で実キーによるモデル利用権限の確認は未実行です。

## 運用上の制約

- [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)：Actionsで作った静的成果物をPagesへ公開できます。GitHub FreeのPagesは公開リポジトリを前提とします。
- [GitHub schedule event](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)：高負荷時の遅延・欠落、既定ブランチのみでの実行、公開リポジトリの60日無活動による無効化に注意が必要です。
- [Cloudflare Pages pricing](https://developers.cloudflare.com/pages/functions/pricing/)：静的アセットは無料・無制限とされていますが、FunctionsはWorkersの制約に従います。
- [Cloudflare Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/)：FreeのCPU時間制限、Paidの月額等があります。
- [Vercel Cron pricing](https://vercel.com/docs/cron-jobs/usage-and-pricing)：Hobbyのcronは1日1回、時刻精度に制約があります。

## 秘密情報の境界

1. OpenAIキーはGitHub Secretsに保存し、取得・解析の該当ステップだけに環境変数として渡します。
2. API送信は固定のOpenAI HTTPSエンドポイントのみ。資料に含まれるURLや指示は実行しません。
3. APIエラー本文・HTTPリクエスト・環境変数一覧・応答全文はログへ出しません。API応答に実キーが含まれれば保存を拒否します。
4. 公開は`site/`だけ。ソースコード・`.git`・`.env`・作業ファイル・予約台帳はPages artifactに含めません。公開ファイル種別・キーらしき文字列も検査します。
5. AI生成テキストはHTMLエスケープ。ブラウザはAPIを呼ばず、外部JavaScript・解析SDK・外部フォントも使いません。CSPで接続を禁止します。
6. ただしキーを手動で誤ってコミットした場合の保護は別です。漏えいしたキーは失効・再発行が必要です。設定手順ではキーをコードへ記載しないようにしています。

## 冪等性と課金

予約をコミット→API呼び出し→正常JSONをコミット→公開、という順番です。公開だけ失敗した場合は次回にAPIを再実行せず再構築・公開します。API送信後に通信断が起きた場合は外部サービスの処理有無を断定できないので、exactly-once課金保証をうたわず、**自動再送を止める**方針です。手動再試行は1回まで、月間上限内です。

GitHubの認証、リポジトリの書き込み権限、Pagesの設定、Secretsの登録は未設定です。この資料は設定後の設計を説明しており、クラウド稼働済みという意味ではありません。
