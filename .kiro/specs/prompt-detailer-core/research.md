# Research & Design Decisions: prompt-detailer-core

## Summary
- **Feature**: `prompt-detailer-core`
- **Discovery Scope**: New Feature（greenfield / documentation-first リポジトリ、実装コードはまだ存在しない）
- **Key Findings**:
  - リポジトリは実装ゼロ。steering（product/tech/structure）と `docs/requirements/requirements-design-reference.md` が設計の正本情報を提供しており、外部探索よりも内部契約の忠実な写経が中心となる。
  - 唯一の実質的な外部技術判断は「JSON Schema 検証をどう実現するか」。`jsonschema` 4.26.0 が Draft 2020-12 を `Draft202012Validator` で完全サポートし、`additionalProperties: false` を含む要求（Req 11, 12）を満たせる。
  - レイヤー分離（domain 純粋 / infrastructure に I/O 隔離）により、Schema 形状検証（infra + jsonschema）とビジネス不変条件検証（domain 純粋）の 2 段構成が自然に成立し、domain 純粋性（steering 必須）を壊さずに Req を満たせる。

## Research Log

### JSON Schema 検証ライブラリ
- **Context**: Req 11（`DETAILER_PLAN` Schema、`additionalProperties: false` 相当、`schema_version` 互換）と Req 12（往復 codec、未知フィールド拒否）を満たすため、Draft 2020-12 相当の検証手段が必要。steering は「標準ライブラリで十分なら依存を増やさない」（tech.md）と明記。
- **Sources Consulted**: [jsonschema PyPI](https://pypi.org/project/jsonschema/)、[jsonschema 4.26.0 docs](https://python-jsonschema.readthedocs.io/)、[JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12)。
- **Findings**:
  - `jsonschema` 4.26.0 は Draft 2020-12/2019-09/7/6/4/3 を完全サポート。`from jsonschema import Draft202012Validator` で明示バージョン指定が可能。Python 3.10+ 対応。
  - `additionalProperties: false`、`$ref`、ネストした配列オブジェクトの検証は標準ライブラリのみでは堅牢に自作困難であり、再実装は誤りを招きやすい。
- **Implications**:
  - `jsonschema` を **runtime 依存**として採用し、利用箇所を infrastructure（`json_codec` / `preset_loader`）に限定する。domain は純粋のまま保つ。
  - Schema ファイルを正本契約とし、runtime も contract test も同一ファイルを検証に使うことで Schema とコードのドリフトを防ぐ。CLAUDE.md §12「外部依存追加は必要性を説明する」に従い、本判断の根拠を design.md へ記載する。

### Ollama response Schema の core 所有範囲
- **Context**: 要件確認で「core は Ollama response Schema + contract test のみを所有し、client / LLM system prompt / retry は analyzer spec へ委譲」と確定（Req 13）。
- **Findings**: core は response を検証する `ollama_response_v1.schema.json` と、検証済み抽出結果を表す domain model `PromptAnalysis` を提供する。実通信・`extract_prompt`/`repair_prompt` テキスト・failure_mode は本 spec 対象外。
- **Implications**: Plan Builder / Upscale Builder は `PromptAnalysis`（検証済みデータ）を入力に取り、供給元（Ollama or fixture or From JSON）を問わない。テストは fixture で全経路を再現できる。

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Layered（採用） | domain / application / infrastructure の一方向依存。steering 既定 | domain を ComfyUI/Ollama/FS 非依存で純粋テスト可能。下流 spec が同契約に安定依存 | 層をまたぐ検証責務の配置を誤ると二重所有になる | steering の依存方向規定と一致。core はこの層構成の下半分（domain + 一部 application/infra）を確立 |
| 単一モジュール集約 | 1 パッケージに全処理 | 初期は速い | domain 純粋性喪失、下流 spec の拡張が困難、テスト分離不可 | steering 違反のため不採用 |
| Schema 検証を全て自作（stdlib のみ） | JSON Schema を使わず手書き検証 | 依存ゼロ | Draft 2020-12 の `additionalProperties:false`/`$ref` 再実装が誤りやすく、Schema ファイルとドリフト | Req 11/12 の堅牢性要求に不足のため不採用 |

## Design Decisions

### Decision: 検証の 2 段構成（Schema 形状検証 + domain 不変条件検証）
- **Context**: Req 11/12 は Schema 適合（必須項目・型・未知フィールド拒否）を、Req 3/5 はビジネス不変条件（`task_id` 一意、`scope ∈ requested_scopes`、`enabled ⇒ prompt_final 非空`、要求 scope ごとに 1 件以上の enabled task）を要求。domain は純粋でなければならない（steering）。
- **Alternatives Considered**:
  1. すべて domain で手書き検証（Schema ファイルは飾り）— ドリフトと再実装リスク。
  2. すべて infra で jsonschema 検証（不変条件も Schema で表現）— `task_id` 一意や「要求 scope ごとに 1 enabled」など JSON Schema で表現しづらい規則があり、ビジネス規則が infra へ漏れる。
- **Selected Approach**:
  - **Tier 1（infra / `json_codec`）**: 生 JSON を `Draft202012Validator` で `detailer_plan_v1.schema.json` に対し形状検証（必須項目・型・`additionalProperties:false`）。
  - **Tier 2（domain / `DetailerPlan` 不変条件）**: 形状検証済みデータから domain オブジェクトを構築し、ビジネス不変条件を検証。違反は domain error。
- **Rationale**: 各検証を最も適切な層へ配置し、Schema ファイルを runtime と test の共通正本にしてドリフトを防止。domain 純粋性を維持。
- **Trade-offs**: 検証が 2 箇所に分かれるが、責務境界が明確。contract test で「Schema 拒否」と「domain 不変条件拒否」を別々に検証できる。
- **Follow-up**: contract test で代表 Plan JSON を Schema と domain の双方に通し、両者の判定が矛盾しないことを確認。

### Decision: `jsonschema` を runtime 依存として infrastructure に限定
- **Context**: 上記 Tier 1 の実現手段。ComfyUI カスタムノードは依存を増やすと配布・互換性に影響。
- **Selected Approach**: `jsonschema>=4.20,<5` を runtime 依存に追加。import は `infrastructure/` のみ。domain / application は `jsonschema` を import しない。
- **Rationale**: Draft 2020-12 の堅牢検証は自作より安全。利用を infra に閉じることで domain 純粋性と層方向を守る。
- **Trade-offs**: 依存が 1 つ増える（推移的に `attrs`/`rpds-py` 等）。ただし JSON Schema 検証はまさに車輪の再発明を避けるべき領域。
- **Follow-up**: `pyproject.toml` に runtime 依存として明記。Registry 配布時の依存解決は `packaging-and-release` spec で確認。

### Decision: 決定論バージョン定数を core が保持
- **Context**: reference §17 のキャッシュキーは prompt builder version / preset version / policy version を含む。キャッシュ自体は analyzer spec 所有だが、version の供給源は core。
- **Selected Approach**: core に `PROMPT_BUILDER_VERSION` と `SCHEMA_VERSION=1` を定数として持たせ、preset/profile/policy は各リソース `version` を保持。builder はこれらを出力の決定性根拠にする。
- **Rationale**: 下流のキャッシュ無効化が core の version 変更を検知できるようにする。
- **Trade-offs**: version 更新の運用規律が必要（snapshot test 差分で検知）。

## Risks & Mitigations
- Schema ファイルと domain 不変条件のドリフト — contract test で双方に同一 fixture を通し判定一致を検証。
- prompt builder の出力揺れ（preset 文言変更） — snapshot test（7 scope + upscale）で差分検出、preset に `version`。
- 禁止語除去が文法を壊す（語の単純除去で二重空白等） — 除去後に空白正規化を適用し、snapshot で確認。
- domain 純粋性の侵食（誤って infra を import） — 層方向を design.md に明記し、review/実装で違反をエラー扱い。

## References
- [jsonschema · PyPI](https://pypi.org/project/jsonschema/) — Draft 2020-12 検証ライブラリ、runtime 依存候補
- [jsonschema 4.26.0 documentation](https://python-jsonschema.readthedocs.io/) — `Draft202012Validator` API
- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) — Schema 仕様の正本
- `docs/requirements/requirements-design-reference.md` — プロジェクト内設計正本情報（データモデル §9、preset §14、prompt §13、order 表 §14.4）
