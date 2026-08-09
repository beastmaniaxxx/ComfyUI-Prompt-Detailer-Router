# Roadmap

## Overview

ComfyUI-Prompt-Detailer-Router は、元画像の生成プロンプトを Ollama で構造化解析し、Ultimate SD Upscale 用の `upscale_prompt` と、複数の Detailer 処理を格納する `DETAILER_PLAN` を生成する ComfyUI カスタムノードです。

仕様駆動開発は、巨大な単一 spec ではなく、責務境界と依存関係に沿った複数 spec で進めます。Core Domain を土台にし、Ollama Analyzer、Plan Selection、Dynamic Combo、Packaging の順に積み上げます。

## Approach Decision

- **Chosen**: 境界別 multi-spec 分割。Core Domain を共有契約として先に定義し、その上に Analyzer、Selection、Frontend、Packaging を載せる。
- **Why**: `DETAILER_PLAN`、scope、schema、preset、prompt builder は全機能の土台であり、Ollama 通信や ComfyUI UI と分けてレビュー・テストできる。JavaScript は UI 候補提供だけ、Python は実行時整合性保証という境界も維持しやすい。
- **Rejected alternatives**: 単一巨大 spec は 20+ tasks になり、LLM、Python domain、ComfyUI node、frontend、CI が混ざるため却下。最初から完全な垂直 MVP spec だけにする案は早く見えるが、Core 契約が曖昧なまま Analyzer/UI 実装へ進むため却下。

## Scope

- **In**: Core Domain、Ollama Prompt Analyzer、Detailer Plan Selection、Dynamic Detailer Task Combo、Packaging and Release の初期 MVP 範囲。
- **Out**: cloud LLM、Ollama 以外の LLM backend、複数人物の完全対応、SetNode/GetNode 探索、サブグラフ探索、Detailer 自動実行、SEGS と人物の完全自動対応、LLM 結果による動的 output ソケット、GUI 上での preset 編集。

## Constraints

- Python 3.10 以上を前提にする。
- ComfyUI 依存は node/compat 境界へ隔離し、domain は ComfyUI、Ollama、filesystem に依存しない。
- LLM は元プロンプトに明記された事実の抽出だけを担当し、最終プロンプト、維持指示、局所ディテール、禁止語検査、`task_id` 生成、検証、fallback は Python が決定する。
- Frontend JavaScript は UI 候補の提供だけを担当し、Python backend が `DETAILER_PLAN` との整合性を保証する。
- 固定 prompt、schema、preset は resource ファイルで管理し、Python コードへ大量に直書きしない。
- 実 Ollama を必要とするテストは通常 CI から分離する。

## Boundary Strategy

- **Why this split**: Core Domain は全 spec の共有契約であり、単体・contract・snapshot test で安定させる必要がある。Ollama Analyzer は外部通信と fallback を含むため独立 spec にする。Plan Selection は JSON 互換の垂直スライスを Ollama なしで成立させる。Dynamic Combo は ComfyUI frontend API 依存が強いため backend validation と切り離す。Packaging は実装完了後の配布・CI・Registry 対応に集中する。
- **Shared seams to watch**: `DETAILER_PLAN` schema、scope 定義、`task_id` 規則、preset version、prompt builder output、node input/output 互換性、frontend candidate と backend validation の不一致。

## Specs (dependency order)

- [x] prompt-detailer-core -- `DetailerPlan`、scope、schema、preset、prompt builder、validator を定義する共有 domain/application 基盤。Dependencies: none
- [ ] ollama-prompt-analyzer -- Ollama `/api/chat` による構造化解析、retry、fallback、diagnostics、Analyzer node を実装する。Dependencies: prompt-detailer-core
- [ ] detailer-plan-selection -- `DETAILER_PLAN` から task を選択する Select、Inspector、From JSON、`missing_behavior` を実装する。Dependencies: prompt-detailer-core
- [ ] dynamic-detailer-task-combo -- Analyzer の `scopes` から Selector の `task_id` 候補を動的更新する frontend extension を実装する。Dependencies: prompt-detailer-core, ollama-prompt-analyzer, detailer-plan-selection
- [ ] packaging-and-release -- `pyproject.toml`、example workflows、CI、documentation、ComfyUI Registry 対応を整える。Dependencies: prompt-detailer-core, ollama-prompt-analyzer, detailer-plan-selection, dynamic-detailer-task-combo
