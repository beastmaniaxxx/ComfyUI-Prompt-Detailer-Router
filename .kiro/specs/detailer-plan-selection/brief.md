# Brief: detailer-plan-selection

## Problem

生成された `DETAILER_PLAN` から任意の Detailer task を安全に選択し、ComfyUI workflow 内で `detailer_prompt` と関連情報を取り出す必要がある。UI の候補値だけを信頼すると、保存済み workflow や手入力時に不整合が発生する。

## Current State

Select、Inspector、From JSON、`missing_behavior` の仕様が未確定で、LLM Text Processor 互換の JSON 入力から Plan を扱う垂直スライスもまだ定義されていない。

## Desired Outcome

Ollama や frontend dynamic combo がなくても、JSON から `DETAILER_PLAN` を作り、Plan を検査し、`task_id` で Detailer prompt を選択できる。

## Approach

Core Domain の schema/validator/JSON codec を利用し、ComfyUI node は薄い adapter として実装する。`task_id` は Python 側で必ず Plan と照合し、存在しない場合は明示的な `missing_behavior` に従う。

## Scope

- **In**: `PDR_DetailerPlanSelect`、`PDR_DetailerPlanInspector`、`PDR_DetailerPlanFromJSON`、`missing_behavior`、`task_id` validation、Plan の人間向け表示、JSON parse/schema validation、integration test。
- **Out**: Ollama 通信、Analyzer の prompt analysis、frontend combo 候補更新、Plan Override、Plan Executor、固定部位 Unpack node。

## Boundary Candidates

- From JSON node と Core JSON codec/validator。
- Select node と application `select_detailer_task` use case。
- Inspector の read-only 表示と Plan mutation の禁止。
- missing task の error/empty/first_matching_scope/first_available 動作。

## Out of Boundary

- Analyzer からの候補生成。
- ComfyUI frontend graph traversal。
- LLM response repair。
- package release 作業。

## Upstream / Downstream

- **Upstream**: `prompt-detailer-core`。
- **Downstream**: `dynamic-detailer-task-combo`、`packaging-and-release`、example workflows。

## Existing Spec Touchpoints

- **Extends**: なし。
- **Adjacent**: `ollama-prompt-analyzer` は Plan を生成するが、選択 node の missing behavior はこの spec が所有する。

## Constraints

Frontend の候補値を信頼しない。`task_id` は ComfyUI UI 上で combo 表示しても Python では任意 string として受け取り、必ず `DETAILER_PLAN` と照合する。不正 JSON を黙って補正しない。
