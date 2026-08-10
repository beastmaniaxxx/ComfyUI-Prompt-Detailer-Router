# Requirements Document

## Project Description (Input)

### 問題を抱えている人

ComfyUI で元画像を Upscale / Detailer 処理する利用者。元画像の生成プロンプトから、Upscale と Detailer に必要な情報を手作業で抽出している。LLM を使う場合も、未指定情報の追加や出力揺れにより再現性と安全性が下がる。

### 現状

Ollama `/api/chat`、Structured Output、timeout、retry、fallback、diagnostics、および `PDR_OllamaPromptAnalyzer` node の具体的な仕様がまだ確定していない。上流 spec `prompt-detailer-core` の Core Domain 契約（`DETAILER_PLAN`、scope 正規化、preset、prompt builder）を前提に、外部通信と node adapter を分離して定義する必要がある。

### あるべき姿

`PDR_OllamaPromptAnalyzer` が元プロンプト・`scopes`・Ollama 設定を受け取り、Ollama から得た構造化抽出結果を検証したうえで、Python 側で `upscale_prompt`、`detailer_plan`（`DETAILER_PLAN`）、`detailer_json`、`warning`、`diagnostics` を生成できる。

### アプローチ

Ollama 通信を `infrastructure/ollama_client.py` に隔離し、Analyzer node は ComfyUI 入出力 adapter に限定する。LLM には元プロンプトに明記された事実の抽出のみを求め、最終 prompt・維持指示・fallback・diagnostics は Core Domain と application 層で決定する。

### スコープ

- **In**: Ollama `/api/chat` client、Structured Output / JSON Schema request、`stream: false`、`think: false` 初期値、timeout、HTTP / model / connection / empty response のエラー処理、不正 JSON の retry 上限、safe fallback、diagnostics、`PDR_OllamaPromptAnalyzer` node、fixture ベースの integration test。
- **Out**: Core Domain 契約の再定義、`PDR_DetailerPlanSelect` / `PDR_DetailerPlanInspector` / `PDR_DetailerPlanFromJSON`、frontend の動的コンボ更新、cloud LLM、Ollama 以外の backend、実 Ollama を必須とする通常 CI。

### 境界候補

- `infrastructure/ollama_client.py` と application use case。
- Ollama raw response と検証済み prompt analysis。
- failure mode と fallback strategy。
- diagnostics に出す情報と、secret を含めない logging。

### 境界外

- `DETAILER_PLAN` schema 自体の設計変更。
- Selector の `missing_behavior`。
- JavaScript graph traversal。
- package metadata と Registry 対応。

### 上流 / 下流

- **Upstream**: `prompt-detailer-core`。
- **Downstream**: `dynamic-detailer-task-combo`、`packaging-and-release`、example workflow 検証。

### 既存 spec との関係

- **Extends**: なし。
- **Adjacent**: `detailer-plan-selection` は Analyzer 出力を消費するが、Ollama 通信は所有しない。

### 制約

- LLM は元プロンプトに明記された事実だけを抽出する。
- 最終 `prompt_final` を LLM に自由生成させない。
- timeout と retry を無制限にしない。
- 実 Ollama が必要なテストは環境変数などで明示的に分離する。

## Requirements
<!-- Will be generated in /kiro-spec-requirements phase -->
