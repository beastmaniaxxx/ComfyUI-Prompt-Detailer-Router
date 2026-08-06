# 技術スタック

## アーキテクチャ

Python バックエンドのレイヤード構成と、小さな ComfyUI フロントエンド拡張を組み合わせます。

中核ルールは「LLM は構造化された事実を抽出し、Python が判断、検証、プロンプト構築、フォールバック、タスクルーティングを行う」です。

依存方向は一方向に保ちます。

```text
nodes -> application -> domain
application -> infrastructure
```

`domain` は ComfyUI、Ollama、ファイルシステムの関心事から独立させ、主要ロジックを ComfyUI 起動なしでテストできる状態にします。

## 主要技術

- **言語**: バックエンドのカスタムノード、domain、application ロジックには Python 3.10 以上を使う。
- **フロントエンド**: ComfyUI UI 拡張には JavaScript を使う。
- **実行環境**: ComfyUI カスタムノード環境。
- **LLM バックエンド**: Ollama `/api/chat` を `stream: false`、Structured Output または JSON Schema で利用する。
- **ワークフロー連携**: Ultimate SD Upscale と Impact Pack Detailer 系の Detailer 段階を想定する。

## 重要な技術判断

- `DETAILER_PLAN` を、可変数の Detailer タスクを扱う中心的な出力契約とする。
- `task_id` は初期仕様では `subject_id + "." + scope` とし、例として `main.face` を使う。
- scope はカンマ区切り入力を分割し、前後空白削除、小文字化、空要素除去、初出順を維持した重複除去、対応 scope 検証の順に正規化する。
- Python 側の Selector は `task_id` を文字列として受け取り、実行時に Plan と照合する。
- JavaScript は動的 combo 候補を提供してよいが、利便性レイヤーに限定する。
- ComfyUI API の import は互換境界に閉じ込め、domain ロジックへ持ち込まない。
- Ollama 通信は infrastructure 層へ隔離する。
- 固定プロンプト文、schema、preset は Python 文字列へ直書きせず resource ファイルで管理する。

## 開発標準

### 型安全性

公開関数と複雑な内部関数には型ヒントを付けます。`DetailerTask` や `DetailerPlan` などの domain モデルは、可能な限り不変 dataclass を優先します。

### コード品質

ノードクラスは薄く保ちます。ComfyUI 入出力の変換、application use case の呼び出し、ユーザー向け warning/error の整形に責務を限定します。

プロンプト生成、Plan 検証、Ollama リクエスト、preset 読み込み規則をノードクラスへ集約しないでください。

広い例外捕捉でエラーを握りつぶさないでください。ユーザー向けエラーと内部例外を分け、不正 JSON、schema 違反、missing task、未対応 scope、Ollama 障害は明示的に扱います。

### テスト

変更時は、影響するレイヤーに応じてテストを追加または更新します。

- scope 解析、task_id、Plan 検証、Selector、prompt builder、preset、JSON codec は unit test で確認する。
- Ollama response schema、`DETAILER_PLAN` schema、preset 必須キー、schema version 互換性は contract test で確認する。
- fixture response から Analyzer 出力まで、および JSON から Plan 選択までの流れは integration test で確認する。
- scope parser、候補生成、現在値の維持、fallback、直接接続、Reroute 探索は frontend test で確認する。
- 最終的な upscale/detailer prompt は snapshot test で差分を確認する。

実 Ollama を必要とするテストは通常 CI から分離し、明示的に有効化された場合だけ実行します。

## 開発環境

共通コマンドはまだリポジトリ内で確立されていません。実装の雛形を追加するときに、Python test、frontend test、format、lint、schema 検証、preset 検証を再現可能なコマンドとして定義してください。

## セキュリティと信頼性

- model output や user input に対して `eval` や `exec` を使わない。
- LLM response を raw HTML として描画しない。
- timeout や retry loop を無制限にしない。
- secret、機密 URL、ローカル private path、credential を含み得る model 設定をログへ出さない。
- malformed JSON、schema mismatch、empty response、unsupported scope は、明示的な error または diagnostics 付きの明示的 fallback として扱う。
