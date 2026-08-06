# Brief: prompt-detailer-core

## Problem

画像生成ワークフロー利用者は、元プロンプトから Upscale と Detailer 用の情報を手作業で切り出しており、部位別プロンプトの整合性、再現性、拡張性を保ちにくい。

## Current State

リポジトリは documentation-first の状態で、`DetailerPlan`、`DetailerTask`、scope 正規化、`task_id`、schema、preset、prompt builder、validator の実装契約がまだ spec として確定していない。

## Desired Outcome

Ollama や ComfyUI を起動しなくてもテストできる Core Domain が定義され、`DETAILER_PLAN` と prompt 構築の契約が安定する。

## Approach

Core Domain を最初の spec として切り出し、domain model、scope、schema、preset、prompt builder、validator、JSON codec をまとめて定義する。LLM は抽出だけ、Python が最終 prompt と検証を決める原則をこの spec の中心契約にする。

## Scope

- **In**: `DetailerTask`、`DetailerPlan`、scope 正規化、`task_id` 生成、`DETAILER_PLAN` JSON Schema、Ollama response Schema の土台、preset 形式、prompt builder、validator、JSON codec、unit/contract/snapshot test。
- **Out**: Ollama 通信、ComfyUI node class、frontend dynamic combo、packaging、Registry 対応、複数人物の完全対応、Detailer 自動実行。

## Boundary Candidates

- domain model と JSON Schema の往復変換。
- prompt builder と preset loader の境界。
- scope validation と unsupported scope の warning/error 変換。
- `task_id = subject_id + "." + scope` の初期規則。

## Out of Boundary

- `/api/chat` 呼び出し、timeout、retry、fallback 通信処理。
- Selector node や Analyzer node の ComfyUI 入出力定義。
- JavaScript による combo 更新。
- 配布、CI、example workflow。

## Upstream / Downstream

- **Upstream**: `.kiro/steering/product.md`、`.kiro/steering/tech.md`、`.kiro/steering/structure.md`、`docs/requirements/requirements-design-reference.md`。
- **Downstream**: `ollama-prompt-analyzer`、`detailer-plan-selection`、`dynamic-detailer-task-combo`、`packaging-and-release`。

## Existing Spec Touchpoints

- **Extends**: なし。
- **Adjacent**: 以降の全 spec がこの Core 契約を参照する。

## Constraints

Python 3.10 以上を前提にする。domain は ComfyUI、Ollama、filesystem に依存しない。固定 prompt、schema、preset は resource として扱い、出力変化は snapshot/contract test で確認する。
