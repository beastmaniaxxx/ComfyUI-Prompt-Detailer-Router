# Brief: packaging-and-release

## Problem

Core、Analyzer、Selection、Frontend が実装されても、ComfyUI custom node として利用・検証・配布できなければユーザーに届かない。example workflow、CI、documentation、Registry 対応を後付けにすると互換性確認が漏れやすい。

## Current State

`pyproject.toml`、README、example workflows、CI、Registry metadata、release documentation の仕様がまだ確定していない。実装前のリポジトリは documentation-first で、共通コマンドも未確立。

## Desired Outcome

ComfyUI custom node としてインストール・テスト・配布でき、MVP workflow が example と CI で検証され、ユーザー向け docs と release 作業の基準が揃う。

## Approach

機能 spec の契約が揃った後に、packaging と release を独立 spec として扱う。Python/frontend/schema/preset/example workflow の検証コマンドを整え、ComfyUI Registry に向けた metadata と documentation をまとめる。

## Scope

- **In**: `pyproject.toml`、README、CHANGELOG、LICENSE 確認、example workflows、GitHub Actions、schema/preset validation scripts、frontend test command、documentation、ComfyUI Registry 対応、release checklist。
- **Out**: Core Domain の再設計、Ollama Analyzer の通信仕様変更、Selector semantics 変更、Dynamic Combo の graph traversal 拡張、cloud LLM 対応。

## Boundary Candidates

- Python package metadata と ComfyUI node registration。
- CI jobs と local validation scripts。
- example workflows と workflow compatibility checks。
- Registry metadata と user-facing documentation。

## Out of Boundary

- 新機能追加。
- 未承認の schema 破壊的変更。
- 実 Ollama を通常 CI に必須化すること。
- 個人環境の Ollama model 名や local path の commit。

## Upstream / Downstream

- **Upstream**: `prompt-detailer-core`、`ollama-prompt-analyzer`、`detailer-plan-selection`、`dynamic-detailer-task-combo`。
- **Downstream**: 初回 release、ComfyUI Registry 登録、将来の互換性維持。

## Existing Spec Touchpoints

- **Extends**: なし。
- **Adjacent**: すべての機能 spec の成果物を検証・配布対象として参照するが、機能 semantics は変更しない。

## Constraints

生成物やローカルモデルを commit しない。Ollama モデル名を固定した個人設定を commit しない。実 Ollama が必要な smoke test は通常 CI から分離する。UI 変更はスクリーンショットまたは短い動作説明を release/PR 文脈で残す。
