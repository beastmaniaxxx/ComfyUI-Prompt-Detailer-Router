# Brief: ollama-prompt-analyzer

## Problem

利用者は元画像の生成プロンプトから、Upscale と Detailer に必要な情報を手作業で抽出している。LLM を使う場合も、未指定情報の追加や出力揺れにより再現性と安全性が下がる。

## Current State

Ollama `/api/chat`、Structured Output、timeout、retry、fallback、diagnostics、Analyzer node の具体的な仕様がまだ確定していない。Core Domain の契約を前提に、外部通信と node adapter を分離して定義する必要がある。

## Desired Outcome

`PDR_OllamaPromptAnalyzer` が元プロンプトと scopes と Ollama 設定を受け取り、構造化抽出結果を検証し、Python 側で `upscale_prompt`、`DETAILER_PLAN`、`detailer_json`、`warning`、`diagnostics` を生成できる。

## Approach

Ollama 通信を infrastructure に隔離し、Analyzer node は ComfyUI 入出力 adapter に限定する。LLM には明記された事実の抽出だけを求め、最終 prompt、維持指示、fallback、diagnostics は Core Domain と application 層で決定する。

## Scope

- **In**: Ollama `/api/chat` client、Structured Output/JSON Schema request、`stream: false`、`think: false` 初期値、timeout、HTTP/model/connection/empty response/error handling、JSON retry 上限、safe fallback、diagnostics、Analyzer node、fixture integration test。
- **Out**: Core Domain 契約の再定義、Selector/Inspector/From JSON、frontend combo 更新、cloud LLM、Ollama 以外の backend、実 Ollama 必須の通常 CI。

## Boundary Candidates

- `infrastructure/ollama_client.py` と application use case。
- Ollama raw response と validated prompt analysis。
- failure mode と fallback strategy。
- diagnostics に出す情報と secret を含めない logging。

## Out of Boundary

- `DETAILER_PLAN` schema 自体の設計変更。
- Selector の `missing_behavior`。
- JavaScript graph traversal。
- package metadata と Registry 対応。

## Upstream / Downstream

- **Upstream**: `prompt-detailer-core`。
- **Downstream**: `dynamic-detailer-task-combo`、`packaging-and-release`、example workflow 検証。

## Existing Spec Touchpoints

- **Extends**: なし。
- **Adjacent**: `detailer-plan-selection` は Analyzer 出力を消費するが、Ollama 通信は所有しない。

## Constraints

LLM は元プロンプトに明記された事実だけを抽出する。最終 `prompt_final` は LLM に自由生成させない。timeout と retry は無制限にしない。実 Ollama が必要なテストは環境変数などで明示的に分離する。
