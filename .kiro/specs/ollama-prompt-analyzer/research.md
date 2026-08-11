# Research & Design Decisions: ollama-prompt-analyzer

## Summary

- **Feature**: `ollama-prompt-analyzer`
- **Discovery Scope**: Extension（上流 spec `prompt-detailer-core` が実装済みの既存レイヤード構成へ、外部通信境界と ComfyUI ノード層を追加する）
- **Key Findings**:
  - core の公開 API は実装済みで、Analyzer が必要とする接続点（`normalize_scopes` / `PromptAnalysis` / `build_upscale_prompt` / `build_detailer_plan` / `encode_plan` / 共有 loader 群）はすべて既存シグネチャのまま利用できる。**core の API 変更は不要**（Requirement Adjacent expectations と一致）。
  - `resources/` の loader は `config_json.py` に共有検証ヘルパ（`read_config_json` / `parse_config_json` / `reject_unknown_keys`）と `resource_ids.safe_resource_id` を持ち、Requirement 10.15 が要求する「prompt リソース専用の検証実装を設けない」を、既存ヘルパの再利用だけで満たせる。
  - Ollama の structured output（`format`）は `$defs` / `$ref` の grammar 変換に既知の順序依存バグがあり、`ollama_response_v1.schema.json` はまさに `$ref` を 2 箇所で使う。`format` へは **`$ref` 解決済みの射影**を渡し、応答の検証は元 Schema ファイルで行う二段構えが必要。
  - `nodes/` と `compat.py` はリポジトリに未だ存在せず、本 spec が初めて ComfyUI 適合層を導入する。`__init__.py` の `NODE_CLASS_MAPPINGS` も本 spec が新設する共有 seam となる。

## Research Log

### 既存 core 実装の API 面確認

- **Context**: requirements は「core を再実装せずそのまま用いる」と宣言しているが、design を書くには実際の関数シグネチャと戻り値型を確定する必要がある。
- **Sources Consulted**: `prompt_detailer_router/` 実装コード、`.kiro/specs/prompt-detailer-core/design.md`（Boundary Commitments、Non-Goals）。
- **Findings**:
  - `domain/scopes.normalize_scopes(raw) -> ScopeNormalizationResult(requested_scopes, dropped_scopes, warnings)`。破棄 scope と warning がすでに構造化されて返る（Requirement 8.1 / 11.3 の「破棄した未対応 scope 列」をそのまま利用可能）。
  - `domain/prompt_analysis.PromptAnalysis(global_features, scoped_features, warnings)` は frozen dataclass で、構築時に `MappingProxyType` + tuple 化される。Analyzer は検証済み抽出結果をこの型で core へ渡す。
  - `application/build_upscale_prompt.build_upscale_prompt(analysis, upscale_preset_id) -> UpscaleBuildResult(upscale_prompt, warnings)`。global feature を `UPSCALE_GLOBAL_ORDER`（medium/style/lighting/camera/material/texture/environment/subject）の順に連結し、preset 結合と禁止語検査まで内包する。
  - `application/build_detailer_plan.build_detailer_plan(PlanBuildInput(requested_scopes, analysis, profile_id, subject_id)) -> DetailerPlan`。**抽出特徴が空の scope に対して preset ベースの fallback task を自動生成し**、`enabled=True` / `extracted_features=()` / 非空 `prompt_final` を保証したうえで `validate_plan` を通す。
  - `infrastructure/json_codec.encode_plan(plan) -> str` は Tier1 Schema → Tier2 不変条件の順に検証してから直列化する。
  - `infrastructure/schema_loader.get_ollama_response_validator()` が Draft 2020-12 validator を lru_cache 付きで返す。`load_schema(OLLAMA_RESPONSE_SCHEMA)` で生の Schema dict も取得できる。
  - 既存 loader は id/version の取得元が不統一: `UpscalePreset.preset_id` と `DetailerProfile.profile_id` はファイル内に持つが、**detailer preset・禁止語ポリシー・detailer builder template はファイル内 id を持たず、ファイル名（= 要求 id）が id** である。
- **Implications**:
  - Requirement 7.1–7.4 の fallback は、**core の Plan Builder が既に持つ「特徴なし scope → preset fallback task」経路をそのまま通す**ことで実現でき、Analyzer 側に独自の Plan 構築を書く必要がない。Requirement 7.2 の「自前で実装しない」がそのまま設計になる。
  - Requirement 9.2 / 11.3 が要求する「各リソースの id と version」の収集は、id の在り処が資源種別ごとに異なるため、**Analyzer 側に単一の資源記述子収集点**（`ResourceFingerprint`）を置いて差異を吸収する必要がある。

### Ollama `/api/chat` の structured output と `$ref`

- **Context**: Requirement 2.2 は「core の response Schema の実際の `properties` / `required` / 未知フィールド方針を渡し、空 Schema や簡略化した Schema を渡さない」と定める。渡し方の具体を確定する必要がある。
- **Sources Consulted**:
  - [Structured Outputs — Ollama Docs](https://docs.ollama.com/capabilities/structured-outputs)
  - [Structured outputs — Ollama Blog](https://ollama.com/blog/structured-outputs)
  - [ollama/ollama#8444 — Ollama not respecting structured outputs with some ordering of refs](https://github.com/ollama/ollama/issues/8444)
  - [ollama/ollama#13184 — Formatted Outputs's Schemas](https://github.com/ollama/ollama/issues/13184)
- **Findings**:
  - `format` には JSON Schema オブジェクトをそのまま渡せる。`stream: false` との併用が推奨される。
  - `json_schema_to_grammar` の `$defs` / `$ref` 解決には binding 問題があり、**定義名のアルファベット順によって生成される grammar が壊れる**ケースが報告されている。
  - `ollama_response_v1.schema.json` は `#/$defs/stringArray` を 9 箇所、`#/$defs/scope` を `propertyNames` で 1 箇所参照しており、この不具合パターンに正面から該当する。
  - grammar 変換が解釈できないキーワード（`propertyNames`、`additionalProperties: false` の一部扱い）は制約として反映されないことがある。`format` は**出力を誘導する最善努力**であり、適合性の保証ではない。
- **Implications**:
  - `format` へは `$ref` を解決（インライン展開）し、`$schema` / `$id` / `title` / `description` を除いた射影を渡す。これは Requirement 2.2 が禁じる「簡略化」ではなく**意味を保存する機械的変換**であり、`properties` / `required` / `additionalProperties: false` はすべて保持される。
  - 単一の正本はあくまで `ollama_response_v1.schema.json` であり、射影は毎回そこから導出する。射影が元 Schema と同じインスタンス集合を受理・拒否することを contract test で保証する。
  - `format` が最善努力である以上、**分類 (g) Schema 違反は到達可能な経路として残る**。Requirement 12.5 / 12.7 の Schema 違反 fixture は死んだテストにならない。

### Ollama `think: false` の互換性

- **Context**: Requirement 2.1 は思考出力の無効化を必須とする。全モデルで安全に送れるかを確認する必要がある。
- **Sources Consulted**:
  - [Thinking — Ollama Blog](https://ollama.com/blog/thinking)
  - [ollama/ollama#15029 — /v1/chat/completions not support think:true](https://github.com/ollama/ollama/issues/15029)
  - [claude-code-router#1046 — Ollama models fail with "does not support thinking"](https://github.com/musistudio/claude-code-router/issues/1046)
- **Findings**:
  - `/api/chat` は `think` を受け付け、`false` で思考過程を抑止して `content` に直接出力させる。
  - 一部の Ollama バージョン / モデル組合せでは、`think` を送ること自体が `does not support thinking` エラー（HTTP 400）になる報告がある。
- **Implications**:
  - 本 spec は Requirement 2.1 に従い `think: false` を常に送る。当該エラーは HTTP 400 として **分類 (d) 再試行不可の HTTP エラー**に落ち、エラー本文の要約が `diagnostics` / エラーメッセージへ出る（Requirement 4.4 / 4.8）ため、利用者が原因を特定できる。
  - 「本文テキストに `does not support thinking` を見つけたら `think` を外して再送する」案は採らない。Requirement 4.4 が**エラー本文のテキスト一致による判定を明示的に禁止**しており、かつ Requirement 6.1 の再試行上限 1 回と組み合わせると再試行予算の意味が経路依存になるため。残存リスクとして design の Risks へ記載する。

### HTTP クライアントの選定

- **Context**: Requirement 4.3（リダイレクト自動追従の無効化）、4.5（読み込み時 1 MiB 上限）、6.6（総待機時間 ≤ `timeout` × 2）を満たす transport が要る。`pyproject.toml` の現行依存は `jsonschema>=4.20,<5` のみ。
- **Sources Consulted**: 既存 `pyproject.toml`、AGENTS.md §12（標準ライブラリで十分なら依存を増やさない）、Python 3.10 `urllib.request` の仕様。
- **Findings**:
  - `urllib.request` で全要件を満たせる。リダイレクトは `HTTPRedirectHandler.redirect_request` が `None` を返す派生クラスを opener に組むことで抑止でき、3xx は `HTTPError` として捕捉できるため**ステータスコードを保ったまま分類 (d) に落とせる**。
  - 応答本文は `response.read(n)` のチャンク読みで上限を強制でき、**全量をメモリへ読んでから判定する経路を作らない**（Requirement 4.5）。
  - `urllib` の `timeout` 引数は個々のソケット操作に適用されるため、低速に送り続ける応答では 1 回の要求が `timeout` を超え得る。Requirement 6.6 の厳密な上限には、**単調時計による試行ごとの deadline** をチャンク読みの境界で評価する必要がある。
- **Implications**:
  - `requests` / `httpx` を新規依存として追加しない。AGENTS.md §12 の方針、および `packaging-and-release` spec が所有する依存宣言へ本 spec が新しい制約を持ち込まないことを優先する。
  - transport は Protocol として抽象化し、fixture テストが要求を記録できるようにする（Requirement 12.4 / 12.9）。

### 設定リソース検証の共有経路

- **Context**: Requirement 10.13–10.15 は、新規 prompt リソース 3 種を preset / profile / policy と**同一の共有検証経路**で検証することを要求する。
- **Sources Consulted**: `infrastructure/config_json.py`、`infrastructure/resource_ids.py`、`infrastructure/policy_loader.py`、`infrastructure/prompt_template_loader.py`、AGENTS.md §22.2。
- **Findings**:
  - `read_config_json` が UTF-8 デコード失敗・JSON 構文エラー・重複キー・非 object ルート・読み込み失敗をすべて `ConfigurationError` へ変換する。
  - `reject_unknown_keys` が未知フィールドを拒否し、`safe_resource_id` が `^[A-Za-z0-9_-]+$` でパスを閉じる。
  - `policy_loader` / `prompt_template_loader` は「必須キー確認 → 未知キー拒否 → 型確認 → 意味的確認」という同一の並びを踏襲している。
- **Implications**:
  - 新規 loader（`llm_prompt_loader`）は既存 3 ヘルパを呼ぶだけでよく、Requirement 10.13 が列挙する 10 種の異常系のうち**「空白のみの必須文字列」だけが共有ヘルパ未提供**である。`preset_loader._require_str_fields` に同等処理があるが private である。共有ヘルパへ昇格させ、`preset_loader` からも同一実装を使う形にして重複実装を避ける。

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| 既存レイヤード構成の踏襲（採用） | `nodes → application → domain` / `application → infrastructure` に Analyzer を載せる | steering・AGENTS.md §4 と完全一致。core の依存方向を壊さない | application の use case が肥大しやすい | 失敗分類・設定検証・根拠照合・キャッシュキーを純粋 domain module へ分解して肥大を抑える |
| Ollama client を application に置く | 通信を use case 内に直書き | ファイル数が減る | AGENTS.md §3.4 / steering「Ollama 通信は infrastructure へ隔離」に違反。fixture 差し替え点が消える | 不採用 |
| 失敗分類を infrastructure の例外階層で表現 | transport 例外の型で (a)–(h) を表す | 変換が減る | 分類 (f)/(g)/(h) は通信層の外で起きるため、分類の正本が 2 箇所に割れる | 不採用。分類は純粋 domain の単一 enum に閉じる |
| キャッシュを永続化（ファイル / SQLite） | 実行をまたいで再利用 | 再起動後も効く | requirements にキャッシュの寿命・格納先・無効化の定義がなく、§21.3 が禁じる未仕様挙動の発明になる | 不採用。プロセス内メモリに限定する |

## Design Decisions

### Decision: `format` へ渡す Schema は `$ref` 解決済みの射影とする

- **Context**: Requirement 2.2 は実際の Schema を渡すことを求めるが、Ollama の grammar 変換は `$defs` / `$ref` に既知バグを持つ。
- **Alternatives Considered**:
  1. Schema ファイルをそのまま渡す — 仕様文言に最も素直だが、参照解決バグにより grammar が壊れ、構造化出力の誘導が実質無効化される環境が生じる。
  2. `format` を使わず prompt だけで JSON を要求する — Requirement 2.2 に正面から違反する。
  3. `$ref` を解決した射影を渡す（採用）。
- **Selected Approach**: `ollama_response_v1.schema.json` を読み、`$defs` の定義を参照箇所へインライン展開し、`$schema` / `$id` / `title` / `description` を除いた dict を `format` に渡す。`properties` / `required` / `additionalProperties: false` / `propertyNames` の enum はすべて保持する。
- **Rationale**: 意味を保存する機械的変換であり、「空 Schema や簡略化した Schema」には該当しない。正本は Schema ファイル 1 つのままで、射影は毎回そこから導出されるため二重管理が生じない。
- **Trade-offs**: 射影ロジックという新たなコードが増える。これは「射影が元 Schema と同一のインスタンス集合を受理・拒否する」ことを検証する contract test で担保する。
- **Follow-up**: 応答の検証は必ず**元の Schema ファイル**の validator で行い、射影を検証に使わない。

### Decision: 応答適合性の正本は自前の validator であり、`format` は誘導に過ぎない

- **Context**: `format` が制約として効かないキーワードがあるため、`format` を渡したからといって応答が Schema 適合するとは限らない。
- **Selected Approach**: `format` は出力誘導の最善努力と位置付け、適合性の判定は Requirement 3.3–3.5 の validator のみが行う。
- **Rationale**: Requirement 3.4 の「黙って補正・部分採用しない」を成立させるには、判定点が 1 つでなければならない。
- **Trade-offs**: 分類 (g) が実運用でも発生し得る。`retry_once` の修復指示 prompt 経路（Requirement 6.2）がその受け皿になる。

### Decision: 試行ごとの単調時計 deadline で総待機時間を閉じる

- **Context**: Requirement 6.6 は総待機時間 ≤ `timeout` × 2 を要求するが、`urllib` の `timeout` はソケット操作単位である。
- **Alternatives Considered**:
  1. ソケット timeout のみに依存 — 低速に送り続ける応答で上限を超え得る。
  2. 全体を別スレッドで走らせて強制中断 — 中断の副作用（ソケットリーク）と複雑さに見合わない。
  3. 試行ごとの deadline をチャンク読み境界で評価（採用）。
- **Selected Approach**: 試行開始時に `deadline = monotonic() + effective_timeout` を確定し、ソケット timeout には**残り時間**を渡す。1 MiB 上限のためのチャンク読みループの各反復で `monotonic() >= deadline` を確認し、超過時は分類 (b) タイムアウトとして中断する。
- **Rationale**: 1 MiB 上限のためにどのみちチャンク読みが必要であり、その境界を deadline 評価点として再利用できる。追加の並行機構が要らない。
- **Trade-offs**: 単一チャンクの読み込み中は中断できないため、上限は厳密には「`timeout` + 1 チャンク分の待ち」となる。ソケット timeout に残り時間を渡すことでこの誤差はソケット層でも抑えられる。
- **Follow-up**: 実効 timeout は Requirement 10.12 の小数第 3 位切り捨て値を使う。

### Decision: キャッシュはプロセス内の容量上限付き LRU とする

- **Context**: Requirement 11 はキーの構成・対象・再利用時の挙動を定めるが、格納先・寿命・容量に言及がない。
- **Alternatives Considered**:
  1. 上限なしの dict — 長時間稼働する ComfyUI プロセスでプロンプトごとにエントリが増え続ける。
  2. 永続キャッシュ — 寿命と無効化の規則が未仕様であり、§21.3 が禁じる発明になる。
  3. 容量上限付きの LRU（採用）。
- **Selected Approach**: プロセス内メモリの LRU。容量は名前付き定数で定義する。
- **Rationale**: **退避が観測可能な契約を変えない**ことが決め手。退避が起きたときの挙動は「キャッシュ未命中 → 抽出要求を再実行」であり、これは Requirement 11.11 が既に定義済みの経路と同一である。したがって容量の選択は未仕様分岐の発明ではなく、既定義の経路へ落ちる頻度の調整にすぎない。
- **Trade-offs**: 容量を超えると再実行が起きる。Requirement 11.1 の同一性契約は「Ollama が同一の応答を返す状況において」という前提付きであるため、再実行しても契約違反にならない。
- **Follow-up**: 容量定数を design に明記し、キャッシュ命中を検証する統合テスト（Requirement 12.11 / 12.24）が容量に依存しないよう、テストは 2 回連続実行で行う。

### Decision: fallback 抽出結果は `global_features["subject"]` に `original_prompt` を格納する

- **Context**: Requirement 7.1 は「`original_prompt` を記述部とする抽出結果を組み立て、通常出力と同一の core Upscale Prompt Builder へ渡す」と定めるが、`PromptAnalysis.global_features` のどのカテゴリへ入れるかは定めていない。
- **Alternatives Considered**:
  1. `medium` など先頭カテゴリへ入れる。
  2. `subject` へ入れる（採用）。
  3. 全カテゴリへ分散させる — 元プロンプトを分類する行為であり、fallback は抽出ができない状況そのものなので矛盾する。
- **Selected Approach**: `PromptAnalysis(global_features={"subject": (original_prompt,)}, scoped_features={})`。
- **Rationale**: **カテゴリ選択は出力に影響しない**。`_global_descriptor` は `UPSCALE_GLOBAL_ORDER` 順に全カテゴリを連結するため、非空カテゴリが 1 つだけなら結果文字列はどのカテゴリを選んでも同一である。したがってこれは未仕様分岐の発明ではなく、出力同値な選択肢からの表明である。意味論的には、抽出前の元プロンプト全文は被写体を含む記述全体であり `subject` が最も近い。
- **Trade-offs**: Requirement 7.10 が明記するとおり、`original_prompt` 全文が記述部となる。
- **Follow-up**: `scoped_features` を空にすることで、core の Plan Builder が全要求 scope に対し preset ベース fallback task を生成する（Requirement 7.3 / 7.4）。

### Decision: 失敗分類の判定順序を transport → status → body に固定する

- **Context**: Requirement 4.12 は「HTTP ステータスによる分類を応答本文の状態による分類より優先する」と定める。
- **Selected Approach**: (1) 例外送出（接続不能 → (a)、deadline 超過 → (b)）、(2) ステータスが 2xx 以外 → Requirement 4.2 の表、(3) 2xx のみ本文状態を評価 → (e) / (f) / (g)。設定検証 (h) はそもそも通信前に確定する。
- **Rationale**: 空本文の 404 が (d) と (e) の双方に該当する曖昧さを消し、`retry_once` の通信回数を実装非依存にする。
- **Trade-offs**: 2xx 以外の応答では本文が分類に寄与しない。本文は `diagnostics` へ要約として出力されるため、情報自体は失われない（Requirement 4.4 / 4.8）。

### Decision: 空白のみの必須文字列検証を共有ヘルパへ昇格する

- **Context**: Requirement 10.13 は prompt リソースの「空白のみの必須文字列」拒否を求め、Requirement 10.15 は preset と同一の共有検証経路を要求する。現状この処理は `preset_loader._require_str_fields` に private として存在する。
- **Selected Approach**: `config_json.py` へ `require_str_fields`（公開）を移し、`preset_loader` と新規 `llm_prompt_loader` の双方がそれを呼ぶ。`preset_loader._require_str_fields` は共有ヘルパへの委譲に置き換える。
- **Rationale**: AGENTS.md §22.2「新しい loader は既存 loader と同じ検証を共有ヘルパ経由で適用する」を、コピーではなく実際の共有で満たす。
- **Trade-offs**: core spec が所有する `preset_loader.py` を 1 箇所変更する。振る舞いは同一（純粋な移設）であり、core の公開 API・Schema・preset 形式は変わらないため、requirements の「core の API 変更を必要としない」に反しない。
- **Follow-up**: 既存の `tests/unit/test_preset_loader.py` が空白のみ文字列の拒否を検証しているため、移設後も同テストが通ることを確認する。

### Decision: `compat.py` は ComfyUI 適合の唯一の seam として最小構成で導入する

- **Context**: AGENTS.md §3.4 は ComfyUI API の import を `compat.py` へ集約することを求める。Analyzer ノード自体は ComfyUI API を import せずに成立する（`INPUT_TYPES` などは素の Python 規約）。
- **Selected Approach**: `compat.py` には ComfyUI 向けの型名定数（`DETAILER_PLAN`）と、将来 ComfyUI API を要する場合の唯一の import 地点である旨の規約を置く。存在しない import を形式的に書かない。
- **Rationale**: 空の抽象を作らずに §3.4 の意図（依存の集約点を 1 つに定める）を満たす。ノードモジュールが ComfyUI なしで import 可能である性質が保たれ、Requirement 12.4 のテスト容易性に直結する。

### Decision: リソース差し替えの seam を `analyze_prompt` の注入点に一本化する（設計レビュー由来）

- **Context**: Requirement 12.12 は「キャッシュキー構成要素それぞれの単独変更で再実行されること」を代表 1 件で済ませずに検証することを求め、Requirement 12.21 は既存 core リソース（各 detailer preset、禁止語ポリシー、builder template、各 JSON Schema）の異常系を要求する。どちらもバンドル済みリソースの差し替えを必要とするが、core の `resource_paths.resource_file` はパッケージアンカー固定で、`schema_loader.get_validator` は `lru_cache` 付きであり、差し替えの入口が無かった。
- **Alternatives Considered**:
  1. **A. 全 loader を注入可能にする**（採用）— `ResourceLoaders` 束を `analyze_prompt` の引数として渡す。
  2. B. リソースルート（ディレクトリ）だけを注入可能にする — core の `resource_paths` に seam を作る必要が生じ、Boundary の例外が 2 つ目になる。
  3. C. テストでの monkeypatch を許容する — 設計変更は不要だが、テストが core 内部（`resource_paths` / `lru_cache`）に依存し、core 側のリファクタで壊れる。
- **Selected Approach**: `infrastructure/resource_loaders.py` に `ResourceLoaders`（preset / profile / detailer preset / policy / template / prompt / 定義 / response schema の各 loader と、`prompt_builder_version` / `plan_schema_version` の 2 定数）を定義し、既定を `DEFAULT_RESOURCE_LOADERS` とする。`analyze_prompt` は `transport` / `cache` / `loaders` の 3 つだけを外部接点として受け取る。
- **Rationale**: 利用者判断（方針 A）。Boundary を跨がず、既に `transport` / `cache` で採用済みの注入パターンと一貫する。version 定数を束に含めることで、定数変更によるキャッシュ無効化も注入だけで検証できる。
- **Trade-offs**: `analyze_prompt` の引数が 3 つになり、`ResourceLoaders` という束の型が増える。代わりに core 内部へ依存するテストがゼロになる。
- **Follow-up**: Schema 自体を差し替えるテストは注入した `load_response_schema` を使い、`get_validator` のキャッシュ済み validator を経由させない。

### Decision: COMBO 入力の組み込み検証を `VALIDATE_INPUTS` で無効化する（設計レビュー由来）

- **Context**: Requirement 1.10 は preset 候補を COMBO として提示することを認め、Requirement 1.11 は Python 側が任意 STRING として受け取り実行時に照合することを求める。ComfyUI は COMBO 入力の値を宣言済み候補リストに対してサーバ側で検証し、リスト外の値をワークフロー実行前に拒否する。
- **Selected Approach**: `VALIDATE_INPUTS` に `upscale_preset` / `detailer_preset_profile` を引数として宣言し、当該入力の組み込み検証を無効化する。判定は `analyze_prompt` 内の Requirement 10.10 照合のみが行う。
- **Rationale**: これがないと、preset ファイルを持たない環境でワークフローを読み込んだ際にノードが実行前に弾かれ、Requirement 10.10 の分類 (h) 報告経路へ到達できない。requirements の確定判断（COMBO 単独に固定すると値が失われる）が想定したシナリオそのものである。
- **Trade-offs**: `failure_mode` は 3 値固定で候補外の値に意味がないため対象に含めず、組み込み検証へ委ねる。
- **Follow-up**: 統合テストは `analyze_prompt` を直接叩くためこの欠落を検出できない。ノード層のテストで `VALIDATE_INPUTS` が候補外の値に真を返すことを直接検証する。

## Risks & Mitigations

- **`think: false` が一部の Ollama / モデル組合せで 400 を返す** — 分類 (d) として扱われ、エラー本文の要約が利用者へ届く。本文テキストによる自動回避は Requirement 4.4 が禁じるため実装しない。運用上の回避策（Ollama の更新、対応モデルの利用）は README へ記載する。
- **`format` の grammar 変換が制約を完全には反映しない** — 適合性の正本を自前 validator に置き、分類 (g) と `retry_once` の修復 prompt 経路を実運用の受け皿とする。
- **逐語照合（Requirement 3.8）により有用な特徴が破棄され fallback task が増える** — Requirement 3.15 が受容済みのトレードオフ。破棄件数・カテゴリ・scope を `warning` に出して利用者が気付けるようにする（Requirement 3.9）。
- **`ollama_url` の宛先を制限しない方針と、元プロンプトの外部送信** — リダイレクト自動追従を無効化（Requirement 4.3）することで、利用者が指定していない宛先へ本文が再送される経路を塞ぐ。
- **キャッシュキーの構成要素漏れ** — Requirement 11.13 の閉じる規則に従い、資源記述子の収集を単一の `ResourceFingerprint` に集約し、キー構成要素の網羅を contract test（Requirement 12.12）で個別に検証する。
- **`preset_loader.py` への変更が core spec の boundary を跨ぐ** — 純粋な移設に限定し、core の公開 API・Schema・preset 形式を変えない。既存 core テストが無改変で通ることを完了条件に含める。

## References

- [Structured Outputs — Ollama Docs](https://docs.ollama.com/capabilities/structured-outputs) — `format` に JSON Schema を渡す方式の一次情報。
- [Structured outputs — Ollama Blog](https://ollama.com/blog/structured-outputs) — `stream: false` との併用と基本形。
- [Thinking — Ollama Blog](https://ollama.com/blog/thinking) — `think` パラメータの意味と `false` の効果。
- [ollama/ollama#8444](https://github.com/ollama/ollama/issues/8444) — `$ref` の順序依存 grammar 生成バグ。
- [ollama/ollama#13184](https://github.com/ollama/ollama/issues/13184) — structured output の Schema 対応範囲に関する議論。
- [claude-code-router#1046](https://github.com/musistudio/claude-code-router/issues/1046) — `does not support thinking` エラーの実例。
- `.kiro/specs/prompt-detailer-core/design.md` — 上流の Boundary Commitments と Non-Goals。
- `docs/requirements/requirements-design-reference.md` §12 / §16 — Ollama 連携と `safe_fallback` の参照定義。
