# Brief: dynamic-detailer-task-combo

## Problem

ComfyUI の通常 COMBO は `DETAILER_PLAN` 接続だけでは自動更新されないため、Selector の `task_id` 候補を手入力する負担が残る。候補が古いままだと workflow 保存・読込時の選択値も不安定になる。

## Current State

Analyzer の `scopes` を JavaScript で解析し、Selector の候補を動的更新する frontend extension の仕様が未確定。直接接続、Reroute、同一グラフ内の範囲と fallback 動作を定義する必要がある。

## Desired Outcome

Analyzer の `scopes` から `main.face`、`main.hair` などの候補が Selector に表示され、現在値維持、候補消失時 fallback、workflow 読込時再計算が動作する。UI 更新に失敗しても Python backend の Plan 検証で実行安全性が保たれる。

## Approach

JavaScript は UI 候補提供に限定し、`extension.js` は登録処理、scope parser、graph source resolver、widget helper を分離する。Python backend の `task_id` validation を前提に、frontend は ergonomic な補助として設計する。

## Scope

- **In**: `web/js/extension.js` 登録、scope parser、Analyzer source resolver、Reroute traversal、Selector widget update、現在値維持、候補消失時 fallback、workflow load 復元、Canvas dirty、frontend unit test。
- **Out**: Backend Plan validation の所有、SetNode/GetNode 探索、サブグラフ探索、LLM 実行結果からの完全な人物別候補同期、動的 output socket、Ollama 通信。

## Boundary Candidates

- scope parser の純粋関数。
- graph source resolver と LiteGraph/ComfyUI API 依存箇所。
- widget update helper と Selector node 表示。
- UI 候補生成と Python validation の責務分離。

## Out of Boundary

- `DETAILER_PLAN` schema 変更。
- `missing_behavior` の backend semantics。
- Analyzer の Ollama request。
- package/Registry release。

## Upstream / Downstream

- **Upstream**: `prompt-detailer-core`、`ollama-prompt-analyzer`、`detailer-plan-selection`。
- **Downstream**: `packaging-and-release`、example workflow UX 検証。

## Existing Spec Touchpoints

- **Extends**: なし。
- **Adjacent**: `detailer-plan-selection` が backend validation を所有し、この spec は frontend 候補表示だけを所有する。

## Constraints

初期対応は Analyzer から Selector への直接接続、Reroute 経由、同一グラフ内に限定する。UI 更新失敗で ComfyUI 全体や workflow 実行を止めない。Node 削除後の参照保持や callback 二重登録を避ける。
