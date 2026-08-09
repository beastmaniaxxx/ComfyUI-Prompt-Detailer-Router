# Implementation Plan

> spec: `prompt-detailer-core` / 全タスクは `application → domain`、`application → infrastructure`、`infrastructure → resources` の一方向依存を守る。domain 層は ComfyUI / Ollama / filesystem / jsonschema を import しない。

## 1. Foundation: パッケージ雛形とテスト実行環境

- [x] 1. `prompt_detailer_router` パッケージ骨格と pytest 実行基盤を用意する
  - `prompt_detailer_router/` と `domain/`・`application/`・`infrastructure/`・`resources/`・`utils/` の各 `__init__.py` を作成し、空パッケージが import できる状態にする
  - `tests/` に `conftest.py` と `unit/`・`contract/`・`fixtures/`・`snapshots/` の骨格を置き、`pytest` がエラーなく 0 件収集できる状態にする
  - runtime 依存 `jsonschema>=4.20,<5` と開発依存 `pytest` を導入し、`infrastructure` からのみ `jsonschema` を import する方針を確認する（domain では未導入を保証）
  - 観測可能な完了条件: 何もテストが無い状態で `pytest` が正常終了し、`import prompt_detailer_router` が成功する
  - _Requirements: 14.1_

## 2. リソース定義: JSON Schema・preset・profile・policy

- [x] 2.1 (P) DETAILER_PLAN の JSON Schema を定義する
  - Draft 2020-12 で root と task 双方を `additionalProperties: false` とし、未知フィールドを拒否する
  - root 必須（`schema_version`・`requested_scopes`・`tasks`・`warnings`）、`schema_version` は `const: 1`、`requested_scopes` は 7 scope enum の `uniqueItems`、task は全 9 フィールド必須で `scope` は 7 scope enum とする
  - 観測可能な完了条件: 正例 Plan JSON が適合し、未知フィールド・必須欠落・`schema_version≠1` を含む反例が Draft202012Validator で拒否される
  - _Requirements: 11.1, 11.2, 14.2_
  - _Boundary: resources/schemas/detailer_plan_v1.schema.json_

- [x] 2.2 (P) Ollama response の JSON Schema（土台）を定義する
  - `global` と `scoped_features` を必須、`warnings` を任意とし、`global` はカテゴリ別 `array<string>`、`scoped_features` は scope キーの `array<string>` とする
  - 実通信・LLM system prompt・retry は本 spec 対象外であることを前提に、抽出結果の形状だけを定義する
  - 観測可能な完了条件: 代表的な抽出結果 JSON が適合し、必須欠落の反例が拒否される
  - _Requirements: 13.1, 14.2_
  - _Boundary: resources/schemas/ollama_response_v1.schema.json_

- [x] 2.3 (P) Upscale/Detailer preset と Detailer profile を定義する
  - 7 scope 分の detailer preset（`version`・`scope`・`preservation`・`local_details`・`restrictions`）と 3 種の upscale preset（`version`・`preset_id`・`quality_details`・`preservation`・`restrictions`）を作成する
  - `default_v1` profile に 7 scope すべての mapping を定義し、各 mapping 先 preset の `scope` が key と一致するようにする
  - preset 文言は reference §13 の scope 別方針（顔再設計・美化・scope 外混入を避ける）に沿って記述する
  - 観測可能な完了条件: 7 detailer preset・3 upscale preset・`default_v1` が揃い、profile の全 mapping 先ファイルが存在する
  - _Requirements: 10.1, 10.2, 10.3, 8.4, 14.2_
  - _Boundary: resources/presets_

- [x] 2.4 (P) 禁止語ポリシーリソースを定義する
  - `version`・`terms`（`beautiful`・`perfect`・`symmetrical` を含む）・`match: case_insensitive_literal` を持つ共有 policy を作成する
  - 観測可能な完了条件: `forbidden_terms_v1.json` が読み込み可能で、必須キーが揃っている
  - _Requirements: 9.1, 14.2_
  - _Boundary: resources/policies/forbidden_terms_v1.json_

## 3. Domain 層（純粋ロジック）

- [x] 3.1 (P) scope 正規化と対応 scope 検証を実装する
  - 分割 → 前後空白削除 → 小文字化 → 空要素除去 → 入力初出順を保持した重複除去 → 対応 scope 照合の順で正規化する
  - 未対応 scope は `requested_scopes` から除外して破棄し、破棄した scope 名を含む warning を生成する。処理は失敗させない
  - 空入力・有効 scope ゼロ時は空の scope 列と warning を返す
  - 観測可能な完了条件: `"Face, hair, face,  hands"` が `("face","hair","hands")` に、未対応語入りが破棄 + warning になる unit test が通る
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3_
  - _Boundary: domain/scopes.py_

- [x] 3.2 (P) scope 別既定 order 表を実装する
  - reference §14.4 の既定値（`hair`=20・`face`=30・`hands`=40・`upper_body`=50・`body`=60・`clothing`=70・`generic`=90）を定数として提供する
  - 観測可能な完了条件: 各 scope に対する既定 order が定数から取得でき、unit test で表と一致する
  - _Requirements: 10.7_
  - _Boundary: domain/order_defaults.py_

- [x] 3.3 domain model と Plan 整合の不変条件検証を実装する
  - `DetailerTask`・`DetailerPlan` を不変オブジェクトとして定義し、必須フィールドと `schema_version` を保持する
  - `task_id = subject_id + "." + scope`（既定 `subject_id=main`）を生成し、同一 `subject_id+scope` を 1 件に制限し Plan 内一意にする
  - 不変条件検証（`scope ∈ requested_scopes`／`enabled=true ⇒ prompt_final 非空`／`enabled=false ⇒ 空許容`／要求 scope ごとに 1 件以上の enabled task）を純粋関数で提供し、違反を構造化して列挙する
  - 観測可能な完了条件: 各違反ケースと正例を網羅した unit test が通り、`enabled=false` の空 `prompt_final` が合格する
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5_
  - _Depends: 3.1, 3.2_
  - _Boundary: domain/detailer_plan.py_

- [x] 3.4 (P) 検証済み抽出結果 model（PromptAnalysis）を実装する
  - `global_features`・`scoped_features`（正規化 scope キー）・`warnings` を不変で保持し、scope 別特徴取得のアクセサを提供する
  - 供給元（Ollama／fixture／From JSON）に依存しない domain 型として定義し、実通信は保持しない
  - 観測可能な完了条件: fixture データから `PromptAnalysis` を構築し、指定 scope の特徴を取り出す unit test が通る
  - _Requirements: 6.1, 13.3_
  - _Boundary: domain/prompt_analysis.py_

- [x] 3.5 (P) 禁止語除去と prompt テキストヘルパを実装する
  - 大文字小文字を無視した literal 一致で禁止語を除去し、除去後に空白を正規化し、除去語数と対象語を返す（検出を LLM に委任しない）
  - prompt 結合（空要素除去）・特徴の順序保持重複除去・空白正規化の純粋ヘルパを提供する
  - 観測可能な完了条件: `beautiful/Perfect/SYMMETRICAL` を含む文字列が除去 + 空白正規化され、`removed_count` が正しい unit test が通る
  - _Requirements: 9.2, 9.3, 9.5_
  - _Boundary: domain/forbidden_terms.py, domain/prompt_text.py, utils/collections.py_

- [x] 3.6 (P) error 階層を実装する
  - 基底エラーの下に user 向け（設定不備・JSON 復号失敗・Plan 検証失敗）と内部エラーを区別して定義する
  - 観測可能な完了条件: 各エラー型が基底から派生し、user 向け／内部の区別が unit test で確認できる
  - _Requirements: 14.3_
  - _Boundary: domain/errors.py_

## 4. Infrastructure 層（リソース I/O と形状検証）

- [x] 4.1 (P) Schema loader と Draft202012Validator 生成を実装する
  - `detailer_plan_v1` と `ollama_response_v1` の Schema ファイルを読み込み、`Draft202012Validator` を生成してプロセス内でキャッシュする
  - 観測可能な完了条件: loader が両 Schema の validator を返し、同一 Schema の再取得でキャッシュが再利用される unit test が通る
  - _Requirements: 11.1, 13.2_
  - _Depends: 2.1, 2.2_
  - _Boundary: infrastructure/schema_loader.py_

- [x] 4.2 (P) preset/profile loader を実装する
  - upscale preset・detailer preset・detailer profile を読み込み、必須キーを検証する。未指定時は既定（`default_v1`）を使う
  - 必須キー欠落・profile の mapping 欠落・mapping 先 preset の `scope` 不一致を設定エラーとして報告し、別 preset へ暗黙 fallback しない
  - 観測可能な完了条件: 正常 preset/profile が不変オブジェクトで読め、欠落・不一致で設定エラーが送出される unit test が通る
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_
  - _Depends: 2.3, 3.6_
  - _Boundary: infrastructure/preset_loader.py_

- [x] 4.3 (P) 禁止語 policy loader を実装する
  - `forbidden_terms_v1` を既定として読み込み、term 一覧と match 方式を提供する
  - 観測可能な完了条件: policy が読み込め、term 一覧と match 方式が取得できる unit test が通る
  - _Requirements: 9.1_
  - _Depends: 2.4_
  - _Boundary: infrastructure/policy_loader.py_

- [x] 4.4 JSON codec（直列化・復号・2 段検証）を実装する
  - `DetailerPlan` を全フィールド保持で直列化し、キー順序を安定させ往復同値を保証する
  - 復号は parse → Tier1 形状検証（Schema ファイルに対する検証、未知フィールド拒否）→ domain 構築 → Tier2 不変条件検証の順で行う
  - 不正 JSON・形状不一致・未知フィールドは黙って補正・破棄せず明示的エラーにし、`eval`/`exec` を使わない
  - 観測可能な完了条件: `encode→decode` が往復同値で、未知フィールド・不正 JSON・不変条件違反がそれぞれ明示的エラーになる unit test が通る
  - _Requirements: 11.3, 12.1, 12.2, 12.3, 12.4, 12.5, 14.4, 14.5_
  - _Depends: 4.1, 3.3, 3.6_
  - _Boundary: infrastructure/json_codec.py_

## 5. Application 層（Builder と検証ユースケース）

- [x] 5.1 (P) Upscale Prompt Builder を実装する
  - 抽出済み画風・照明・材質・カメラ・背景情報に、upscale preset の品質向上指示・維持指示・制限を結合する
  - 元プロンプトにない被写体特徴を追加せず、結合確定後に禁止語検査を適用し、同一入力・同一 preset version で同一出力を返す
  - 観測可能な完了条件: fixture 入力から決定論的な `upscale_prompt` を生成し、被写体特徴が混入しない unit test が通る
  - _Requirements: 7.1, 7.2, 7.3, 9.4_
  - _Depends: 3.4, 3.5, 4.2, 4.3_
  - _Boundary: application/build_upscale_prompt.py_

- [x] 5.2 (P) Detailer Plan Builder を実装する
  - 各要求 scope について、抽出特徴があれば scope 別 preset と結合して `prompt_final` を構築し、無ければ preset のみの非空 fallback task（`extracted_features` 空・`enabled=true`）を生成して plan warning に記録する
  - 抽出結果の `task_id`／`prompt_final`／維持文／局所文を採用せず、元プロンプトにない具体属性を追加しない。`order` は preset の `default_order`、無ければ既定 order 表を用いる
  - `prompt_final` 確定後に禁止語検査を適用し、最後に Plan 整合の不変条件検証を通す
  - 観測可能な完了条件: `scopes=face,hair` から `main.face`・`main.hair` が生成され、特徴欠落 scope に非空 fallback + warning が付く unit test が通る
  - _Requirements: 3.1, 3.3, 5.3, 6.1, 6.2, 6.3, 6.4, 6.5, 8.1, 8.2, 8.3, 8.4, 8.5, 9.4, 10.6, 10.7_
  - _Depends: 3.2, 3.3, 3.4, 3.5, 4.2, 4.3_
  - _Boundary: application/build_detailer_plan.py_

- [x] 5.3 (P) Plan 整合検証ユースケースを実装する
  - domain の不変条件検証を呼び出し、違反を user 向けエラーへ昇格する薄いユースケースとして提供し、検証ロジックを二重化しない
  - 観測可能な完了条件: 不整合 Plan で user 向けエラーが送出され、整合 Plan では成功する unit test が通る
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  - _Depends: 3.3, 3.6_
  - _Boundary: application/validate_detailer_plan.py_

## 6. Validation: contract・integration・snapshot テスト

- [x] 6.1 (P) contract テストを実装する
  - DETAILER_PLAN Schema の適合/拒否と `schema_version` 互換、Ollama response Schema の必須検証を確認する
  - 全 preset・`default_v1` profile・`forbidden_terms_v1` の必須キー充足と、欠落・mapping 不一致での設定エラーを確認する
  - 代表 Plan JSON を Schema（infra）と domain 不変条件検証の双方に通し、判定が矛盾しないことを確認する
  - 観測可能な完了条件: 上記 contract テストがすべて通り、Schema と domain の二重検証整合が担保される
  - _Requirements: 9.1, 10.1, 10.2, 10.3, 10.4, 10.5, 11.1, 11.2, 11.4, 13.1, 13.2_
  - _Depends: 2.1, 2.2, 2.3, 2.4, 3.3, 4.1, 4.2, 4.3_
  - _Boundary: tests/contract_

- [x] 6.2 (P) integration テストを実装する
  - 多様な fixture 抽出結果（写真／イラスト／顔アップ／全身／人物なし／短文／矛盾特徴）から Plan Builder → 直列化 → 復号の往復同値を確認する
  - Upscale Builder が元プロンプトにない被写体特徴を混入しないことを、ComfyUI / Ollama 非依存の fixture で確認する
  - 観測可能な完了条件: fixture 起点の Plan 往復同値と Upscale 非混入が通り、実 Ollama 無しで全経路が再現される
  - _Requirements: 6.1, 6.2, 6.3, 7.2, 12.3, 14.1_
  - _Depends: 4.4, 5.1, 5.2_
  - _Boundary: tests/integration_

- [x] 6.3 (P) snapshot テストを実装する
  - 代表元プロンプト集合ごとに `upscale_prompt` と 7 scope の `prompt_final`・warnings を snapshot 化する
  - preset 変更が該当 scope の snapshot のみに反映されることを確認する
  - 観測可能な完了条件: upscale + 7 scope の snapshot が固定され、preset 差分で該当 snapshot のみが変化する
  - _Requirements: 8.4, 14.6_
  - _Depends: 5.1, 5.2_
  - _Boundary: tests/snapshots_

## Implementation Notes

- **リソースアクセス**: `resources` は package（`__init__.py` あり）だが `schemas/`・`presets/`・`policies/` サブディレクトリは package ではない。`importlib.resources.files("prompt_detailer_router.resources").joinpath("schemas", "detailer_plan_v1.schema.json")` の形で親 package から辿ること（loader タスク 4.1/4.2/4.3 で踏襲）。
- **profile mapping 値 = detailer preset ファイル名 stem**（scope 名と一致、例 `"face": "face"`）。design の File Structure（`detailer/face.json`）に合わせた確定仕様で、reference §14.3 の例示 `"face_v1"` とは異なる。preset_loader（4.2）は mapping 値を `detailer/<value>.json` として解決し、その `scope` が key と一致することを検証する。
- **開発依存**: `jsonschema>=4.20,<5`（インストール済み 4.26.0）は infra 限定。テストは `python -m pytest -q` で実行。
- **禁止語マッチ**: `apply_forbidden_terms` は `case_insensitive_literal` を**単語境界（`\b`）付き**で解釈し、`imperfect` から `perfect` を削らない。builder（5.1/5.2）と snapshot（6.3）はこの語単位除去を前提にする。除去後は空白正規化される。
- **domain 純粋性**: `tests/unit/test_domain_purity.py` が domain 配下の `jsonschema`/`requests`/`comfy` 等 import を静的に禁止。infra loader（4.x）でのみ `jsonschema` を使う。
- **validate_plan は非 raise**: domain の `validate_plan` は `PlanValidationIssue` を列挙して返すのみ。user 向け `PlanValidationError` への昇格は application（5.3）が担う。
- **infra loader の入口**（5.1/5.2 で利用）: `preset_loader.load_detailer_profile()`（既定 `default_v1`、mapping 先の存在と scope 一致を検証）／`load_detailer_preset(scope)`／`load_upscale_preset(id)`／`policy_loader.load_forbidden_terms_policy()`／`json_codec.encode_plan`。preset に `default_order` が無ければ `order_defaults` を使う。
- **json_codec の直列化**: `ensure_ascii=False, indent=2`、キー順は schema 準拠で固定（往復同値・snapshot 安定）。decode は Tier1(schema)→Tier2(`validate_plan`)。
- **prompt_final の合成テンプレ**（6.3 snapshot が固定）: detailer = `join_prompt([feature_clause, preservation, local_details, restrictions])`（`feature_clause="Keep the described <features>."`、fallback は空）→ 禁止語除去。upscale = `join_prompt([global記述子, quality_details, preservation, restrictions])`→ 禁止語除去。global 記述子は `UPSCALE_GLOBAL_ORDER`（medium,style,lighting,camera,material,texture,environment,subject）順で dedup。
- **prompt_core は禁止語フィルタ対象外**（Req 9.2 は prompt_final/upscale_prompt のみ）。scope 限定は `features_for_scope(scope)` + scope preset のみ使用で担保。
- **PR#2 Codex レビュー対応（P2×7）**:
  - Ollama response schema に `schema_version`(const 1) を必須化（Req 13.2）。analyzer は Structured Output に含めるか検証前に注入する。fixture も更新。
  - `validate_plan` を契約完全化: `task_id==subject.scope`(3.1)・`(subject_id,scope)` 一意(3.3)・`requested_scopes` 正規化(4.4) を追加検証。`decode_plan` の garbage task_id を拒否。
  - face preset restrictions から hairstyle/length/color 参照を除去（scope 分離、Req 8.2）。face snapshot 再生成。
  - builder の feature_clause を version 付きリソース `resources/prompts/detailer_builder_v1.json` + `prompt_template_loader` に外部化（固定プロンプト直書き禁止）。
  - preset/policy loader の JSON 構文エラーを `ConfigurationError` に変換（user 向けエラー化）。
  - 禁止語除去後に区切り記号を修復（`repair_separators`）: `", X"`/`"X,, Y"` を正規化。
- **PR#2 Codex レビュー 第2ラウンド対応（P2×5）**:
  - preset/profile を読み込み時に**値型検証**（文字列/`default_order` int|None/mappings str→str）→ `ConfigurationError`。
  - `DetailerProfile.mappings` を `MappingProxyType` で不変化（読み込み後の改変で検証迂回を防止）。
  - `photographic` preset の `quality_details` を**被写体非依存**に変更（skin/pores/hair/fabric を除去、Req 7.2）。upscale snapshot 再生成。
  - `decode_plan` で JSON **重複キーを拒否**（`object_pairs_hook`→`PlanDecodeError`、後勝ち黙殺を防止、Req 12.4/12.5）。
  - schema 検証エラーメッセージに**フィールドパス**を付与（`tasks/0/order: ...`、user 向け actionable 化）。
- **PR#2 Codex レビュー 第3ラウンド対応（P2×5）**:
  - `DetailerTask`/`DetailerPlan` に `__post_init__` を追加し配列を tuple 化（`list` 経由の後変更を防止、真の不変性）。
  - `policy_loader` で term/version/match の型と対応 match モードを検証 → `ConfigurationError`。
  - builder template を読込時に `string.Formatter` で解析し `{features}` 以外・不正波括弧を拒否。
  - **セキュリティ**: `infrastructure/resource_ids.safe_resource_id` を追加し全 loader の id（preset/profile/policy/template）を `^[A-Za-z0-9_-]+$` に制限（`..`/絶対パス等のパストラバーサルを拒否）。
  - 禁止語マッチを英数字 lookaround 境界に変更し `_` を区切り扱い（`perfect_face` を除去、`imperfect`/`upper_body` は保持）。除去後に孤立アンダースコアを整形。
- **PR#2 Codex レビュー 第4ラウンド対応（P2×4）**:
  - `photographic` preset の `preservation` を被写体非依存化（pose/identity/clothing design を除去、Req 7.2）。upscale snapshot 再生成。
  - `validate_plan` に空 `subject_id`（空白含む）検証を追加（`empty_subject_id`）。builder は空 subject で往復不能な Plan を返さず fail-fast。
  - preset/policy/template の JSON 読込境界で **object 検証**を追加（`null`/数値/配列を `ConfigurationError` 化）。
  - `upper_body` preset の `restrictions` から `background` を除去（scope 分離、Req 8.2）。upper_body snapshot 再生成。
- **PR#2 Codex レビュー 第5ラウンド対応（P2×3）**:
  - `illustration` preset の `preservation` を被写体非依存化（character design/pose を除去、Req 7.2）。
  - `generic` preset の `restrictions` から `surrounding scene` を除去（scope 分離、Req 8.2）。generic snapshot 再生成。
  - `encode_plan` に直列化前の `validate_plan` を追加（不正 Plan を `PlanValidationError` 化、`decode_plan` と対称に往復契約を保証、Req 12.3）。
  - 全 preset を横断監査し scope/subject 混入は解消済み（minimal の `subject` は汎用、他 scope は限定でクリーン）。
- **PR#2 Codex レビュー 第6ラウンド対応（P2×4）**:
  - `encode_plan` に Tier1 Schema 検証を追加（`schema_version!=1`/`order=bool` 等を `PlanValidationError` 化、decode と完全対称）。
  - builder template の format_spec/conversion を拒否（`{features:{oops}}`/`{features!r}` を読込時 `ConfigurationError`）。
  - `infrastructure/config_json.parse_config_json` を新設し、重複キー・非 object・構文エラーを一括で `ConfigurationError` 化。preset/policy/template loader を集約。
  - task 6.2 の完了条件を満たすため多様 fixture（illustration/face_closeup/full_body/short/contradictory）を追加し、integration を全 fixture で parametrize（媒体語の非混入・短文/矛盾の fallback 往復も検証）。
- **PR#2 Codex レビュー 第7ラウンド対応（P2×1）**:
  - **Python 3.10 互換**: `Traversable.joinpath` は 3.10 では単一引数のみ（zip/namespace 配置で複数引数は `TypeError`）。`infrastructure/resource_paths.resource_file(*parts)` を新設し一段ずつ連結。preset/policy/template/schema の全 loader と contract テストヘルパを集約（`Traversable` 型 import は 3.11+ 限定のため `TYPE_CHECKING` ガード）。
- **PR#2 Codex レビュー 第8ラウンド対応（P2×3）**:
  - `encode_plan` を Tier1(Schema)→Tier2(`validate_plan`) 順に変更（`subject_id=None` 等の型違反を `PlanValidationError` 化、`.strip()` の生 `AttributeError` を回避）。
  - `repair_separators` を句点隣接・空括弧へ拡張（`". x"`/`"x.. y"`/`"()"` を整形。複数文プロンプトは不変で snapshot 影響なし）。
  - `domain/versions.PROMPT_BUILDER_VERSION` を新設し両 Builder で明示 re-export（design 契約どおり下流 Analyzer の cache key 再現性根拠として import 可能に）。
- **PR#2 Codex レビュー 第9ラウンド対応（P2×4）**:
  - **非UTF-8リソース**: `config_json.read_config_json` を新設し `UnicodeDecodeError`（`OSError` 非継承で従来ハンドラ素通り）を `ConfigurationError` へ変換。preset/policy/template loader の読み込みを集約（schema loader はバンドル済み信頼リソースのため対象外）。
  - **区切り修復の限定**: `apply_forbidden_terms` の `repair_separators` を「実際に禁止語を除去した場合のみ」に限定（第8ラウンド導入の無条件実行が回帰。除去ゼロの `"cinematic... dreamlike"` 等を保持）。
  - **hair プリセット中立化**: `realistic texture`/`fine flyaway hairs` を除去し原スタイル中立の文言へ（illustration/anime に写実強制・未記載毛束を誘発しない）。snapshot は `detailer_hair.txt` のみ更新、scope分離テストは `strand grouping` で判定。
  - **未知フィールド拒否**: `config_json.reject_unknown_keys` を新設し upscale/detailer/profile/policy/template の全 parse に横展開（`"default_oder"` 等のタイプミスが既定値へ黙ってフォールバックするのを防止）。
- **PR#2 Codex レビュー 第10ラウンド対応（P2×4）※本PRのレビュー最終ラウンド**:
  - **区切り修復の除去位置限定**: `apply_forbidden_terms` を「禁止語をセンチネル `\x00` へ置換し、空括弧・孤立区切りの修復をセンチネル近傍のみに限定→末尾でセンチネル除去」へ再設計（第8ラウンド導入の全体修復が回帰。`"cinematic... portrait, beautiful eyes"` → `"cinematic... portrait, eyes"` と正当な `...` を保持）。未使用化した `prompt_text.repair_separators`（＋関連シンボル）を削除。
  - **ロード時ID整合**: `load_upscale_preset`＝`preset_id`、`load_detailer_preset`＝`scope`、`load_detailer_profile`＝`profile_id` をファイル名と一致検証（コピペ由来のID残存を `ConfigurationError` 化）。
  - **必須文字列の空白拒否**: `_require_str_fields` に `.strip()` 空チェックを追加（空 `upscale_prompt` 等の degenerate 出力を読込時に排除）。
  - **profile mapping キーの完全一致**: `parse_detailer_profile` で未知 scope キー（`feet` 等）を拒否し、`parse_detailer_preset` で `scope ∈ SUPPORTED_SCOPES` を検証（到達不能な設定の黙認を防止）。
  - **レビュー打ち切り方針（AGENTS §17.1/§17.2）**: 本PRのCodexレビューは**ラウンド10（上限）で完了**とし、以降の新規指摘は受け付けない。§17.2 のとおりラウンド5以降の新規観点は原則対象外だが、第10ラウンドの4件は contract/AGENTS に根拠があり妥当だったため最終ラウンドとして修正しきった。
- **Issue #3 対応（ラウンド10後の積み残しP2×2・別PR）**: PR#2 マージ後、ラウンド10到達後に挙がった2件を [#3](https://github.com/beastmaniaxxx/ComfyUI-Prompt-Detailer-Router/issues/3) 経由の別PRで対応（develop ベース `fix/issue-3-forbidden-terms-and-preset-scope`）。
  - **禁止語連続除去の修復漏れ（回帰）**: `_repair_removal_sites` を単一パスから **fixpoint ループ＋隣接センチネル畳み込み（`_ADJACENT_SENTINELS`）** へ変更。`"beautiful, perfect, face"`→`"face"`、`"face, beautiful, perfect, hair"`→`"face, hair"`、`"(beautiful perfect), face"`→`"face"`。非連続除去・無関係な `...` 保持は不変。
  - **Detailer preset の scope==ファイル名 過剰制約の撤去**: 第10ラウンドで追加した `load_detailer_preset` の `preset.scope == preset_id` 検査を撤去（Req 10.5／design 契約：preset ID は scope と同一である必要はなく `face -> portrait_face_v1` を許容）。scope 整合は `verify_profile_targets` に委譲。upscale の `preset_id`／profile の `profile_id` 検査は妥当なため維持。
