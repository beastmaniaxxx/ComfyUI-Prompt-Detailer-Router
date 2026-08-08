# Requirements Document

## Project Description (Input)
画像生成ワークフロー利用者は、元プロンプトから Upscale と Detailer 用の情報を手作業で切り出しており、部位別プロンプトの整合性、再現性、拡張性を保ちにくい。本 spec では、Ollama や ComfyUI を起動しなくてもテストできる Core Domain を定義し、`DETAILER_PLAN` と prompt 構築の契約を安定させる。

Core Domain を最初の spec として切り出し、domain model（`DetailerTask`・`DetailerPlan`）、scope 正規化、`task_id` 生成、`DETAILER_PLAN` JSON Schema、Ollama response Schema の土台、preset 形式、prompt builder、validator、JSON codec をまとめて定義する。「LLM は抽出だけ、Python が最終 prompt と検証を決める」という原則をこの spec の中心契約とする。

**In Scope**: `DetailerTask`、`DetailerPlan`、scope 正規化、`task_id` 生成、`DETAILER_PLAN` JSON Schema、Ollama response Schema の土台、preset 形式、prompt builder、validator、JSON codec、unit/contract/snapshot test。

**Out of Scope**: Ollama 通信（`/api/chat`・timeout・retry・fallback）、ComfyUI node class、frontend dynamic combo、packaging、Registry 対応、複数人物の完全対応、Detailer 自動実行。

**Constraints**: Python 3.10 以上を前提とする。domain は ComfyUI・Ollama・filesystem に依存しない。固定 prompt・schema・preset は resource として扱い、出力変化は snapshot/contract test で確認する。

## Requirements
<!-- Will be generated in /kiro-spec-requirements phase -->
