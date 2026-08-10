# Requirements Document

## Introduction

`prompt-detailer-core` は、`ComfyUI-Prompt-Detailer-Router` の中核ドメインを最初の spec として確定するものです。画像生成ワークフロー利用者は、元プロンプトから Upscale と Detailer 用の情報を手作業で切り出しており、部位別プロンプトの整合性・再現性・拡張性を保ちにくいという課題を抱えています。

本 spec は、Ollama や ComfyUI を起動しなくてもテストできる Core Domain を定義し、`DETAILER_PLAN` と prompt 構築の契約を安定させます。中心となる原則は「LLM は元プロンプトに明記された事実の抽出だけを担当し、Python 側の決定論的ロジックが scope 正規化・`task_id` 生成・検証・preset 適用・禁止語検査・fallback・最終 prompt 決定を行う」ことです。本 spec は、この決定論的ロジックとその契約（domain model、scope、schema、preset、prompt builder、validator、JSON codec）を対象とします。

対象 scope は `face`、`hair`、`hands`、`body`、`upper_body`、`clothing`、`generic` の 7 種です。初期仕様では単一の主被写体（`subject_id = main`）を前提とします。

## Boundary Context

- **In scope**:
  - `DetailerTask` / `DetailerPlan` の domain model と不変性・整合契約
  - scope 正規化と対応 scope 検証（未対応 scope は warning 付きで破棄）
  - `task_id` 生成規則（`subject_id + "." + scope`）
  - `DETAILER_PLAN` の JSON Schema と contract test
  - Ollama response Schema の **土台のみ**（Schema ファイルと contract test）
  - preset 形式（upscale preset / detailer preset / detailer preset profile / 既定 order）
  - 共有の禁止語ポリシー（version 付きリソース）
  - Upscale Prompt Builder と scope 別 Detailer Prompt Builder
  - 抽出結果データから Plan を構築する Plan Builder（欠落 scope の fallback task 生成を含む）
  - Plan Validator と JSON codec（往復変換）
  - unit / contract / snapshot test
- **Out of scope**:
  - Ollama への実通信（`/api/chat` 呼び出し、timeout、retry、failure_mode、接続 diagnostics）
  - LLM 向け system prompt テキスト（extraction / repair prompt）と client 実装
  - ComfyUI node class（Analyzer / Select / Inspector / From JSON の入出力定義）
  - JavaScript による動的 combo 更新とグラフ探索
  - packaging、Registry 対応、example workflow、CI
  - 複数人物の完全対応（`subject_id` は既定 `main` 固定）と Detailer 自動実行
- **Adjacent expectations**:
  - `ollama-prompt-analyzer` は、core が定義する Ollama response Schema・Plan Builder・Validator・prompt builder・JSON codec をそのまま利用して Analyzer 出力を組み立てる。core は通信結果を「検証済み抽出結果データ」として受け取る前提の契約だけを提供する。
  - `detailer-plan-selection` は、core の `DETAILER_PLAN` 整合契約（`task_id` 一意性、`requested_scopes` との整合、`enabled` 意味論）に依存する。missing behavior 自体は当該 spec が所有する。
  - `dynamic-detailer-task-combo` は、core と同一の scope 正規化規則を前提に UI 候補を生成する。core は正規化規則の正本を提供するが、フロントエンド実装は所有しない。

## Requirements

### Requirement 1: Scope 正規化
**Objective:** ワークフロー利用者として、`face, Hair, face,  hands` のような雑多な scope 入力を安定した正規化結果に変換してほしい。そうすれば、後続の task 候補と Plan が入力表記の揺れに影響されない。

#### Acceptance Criteria
1. When カンマ区切りの scope 文字列が渡されたとき、the Scope 正規化処理 shall カンマで分割し、各要素の前後空白を削除し、小文字化し、空要素を除去した結果を返す。
2. When 正規化後に重複する scope が存在するとき、the Scope 正規化処理 shall 入力での初出順を維持したまま重複を除去する。
3. The Scope 正規化処理 shall 正規化結果の scope 名を対応 scope 集合（`face`、`hair`、`hands`、`body`、`upper_body`、`clothing`、`generic`）と照合する。
4. When 入力が空文字または正規化後に有効な scope が 1 件も残らないとき、the Scope 正規化処理 shall 空の scope 列を返し、その旨を warning として報告する。
5. The Scope 正規化処理 shall 同一入力に対して常に同一の正規化結果を返す。

### Requirement 2: 未対応 scope の扱い
**Objective:** ワークフロー利用者として、未対応 scope を入力しても処理が止まらず、何が無視されたかを把握したい。そうすれば、軽微な入力ミスでワークフロー全体が失敗しない。

#### Acceptance Criteria
1. If 正規化後の scope 列に対応 scope 集合へ含まれない scope が存在するとき、then the Scope 正規化処理 shall その未対応 scope を `requested_scopes` から除外する。
2. If 未対応 scope を除外したとき、then the Scope 正規化処理 shall 除外した scope 名を含む warning を生成する。
3. The Scope 正規化処理 shall 未対応 scope を検出しても処理を失敗させず、残りの対応 scope で処理を継続する。

### Requirement 3: task_id 生成
**Objective:** 下流ノードの利用者として、各 Detailer task を安定した識別子で参照したい。そうすれば、task 選択と候補表示が一意かつ予測可能になる。

#### Acceptance Criteria
1. When 有効な `subject_id` と正規化済み `scope` から task を生成するとき、the Task 生成処理 shall `task_id` を `subject_id + "." + scope` として構成する。
2. The Task 生成処理 shall 初期仕様において `subject_id` の既定値を `main` とする。
3. If 同一 Plan 内で同一の `subject_id` と `scope` の組が複数生成されようとするとき、then the Task 生成処理 shall 当該組を 1 件に制限し、重複生成を行わない。
4. The Task 生成処理 shall 生成した `task_id` を Plan 内で一意にする。

### Requirement 4: DetailerTask / DetailerPlan ドメインモデル
**Objective:** core 開発者として、Detailer タスクと計画を不変で情報欠落のないモデルとして扱いたい。そうすれば、決定論的な検証と往復変換が保証される。

#### Acceptance Criteria
1. The Core Domain shall `DetailerTask` に `task_id`、`subject_id`、`scope`、`extracted_features`、`prompt_core`、`prompt_final`、`order`、`enabled`、`warnings` の各フィールドを保持させる。
2. The Core Domain shall `DetailerPlan` に `schema_version`、`requested_scopes`、`tasks`、`warnings` の各フィールドを保持させる。
3. The Core Domain shall `DetailerTask` と `DetailerPlan` を生成後に変更できない不変オブジェクトとして表現する。
4. The Core Domain shall `requested_scopes` を、正規化済みかつ重複を含まない scope 列として保持する。
5. The Core Domain shall `DetailerPlan` に `schema_version` を必須項目として保持させる。

### Requirement 5: Plan 整合契約
**Objective:** 下流 spec の利用者として、Plan の内部整合が常に保たれていることを前提にしたい。そうすれば、Selector や UI 候補が Plan と食い違わない。

#### Acceptance Criteria
1. The Plan 整合契約 shall すべての `tasks[].scope` が `requested_scopes` に含まれることを要求する。
2. If `requested_scopes` に含まれない scope を持つ task が存在するとき、then the Plan Validator shall 当該 Plan を不正として拒否する。
3. The Plan 整合契約 shall v1 において、`requested_scopes` の各 scope に対して少なくとも 1 件の `enabled=true` task が存在することを要求する。
4. While task が `enabled=true` であるとき、the Plan 整合契約 shall 当該 task の `prompt_final` を空文字にしないことを要求する。
5. Where task が `enabled=false` であるとき、the Plan 整合契約 shall 当該 task の `prompt_final` が空文字であることを許容する。

### Requirement 6: Plan Builder（抽出結果からの構築と欠落補完）
**Objective:** core 開発者として、検証済みの抽出結果データから決定論的に Plan を構築したい。そうすれば、LLM の揺らぎに依存せず、要求 scope ごとの task が保証される。

#### Acceptance Criteria
1. When 正規化済み `requested_scopes` と検証済み抽出結果データが渡されたとき、the Plan Builder shall 各要求 scope に対応する `DetailerTask` を生成する。
2. When ある要求 scope に対応する抽出特徴が抽出結果に存在しないとき、the Plan Builder shall 当該 scope の `enabled=true` な fallback task を生成し、その欠落を Plan-level warning に記録する。
3. The Plan Builder shall fallback task の `extracted_features` を空とし、`prompt_final` を preset から構築した非空文字列とする。
4. The Plan Builder shall 抽出結果に含まれる `task_id`、`prompt_final`、維持指示、局所ディテール文をそのまま採用せず、Python 側の決定工程で最終値を構築する。
5. The Plan Builder shall 元プロンプトに明記されていない具体的な視覚属性を確定情報として追加しない。

### Requirement 7: Upscale Prompt 構築
**Objective:** ワークフロー利用者として、元プロンプトの画風・照明・材質・カメラ・背景情報から一貫した Upscale プロンプトを得たい。そうすれば、Upscale 段階への手作業転記が不要になる。

#### Acceptance Criteria
1. When 検証済み抽出結果と指定された upscale preset が渡されたとき、the Upscale Prompt Builder shall 抽出した画風・照明・材質・カメラ・背景情報に、preset の品質向上指示・維持指示・制限を結合した `upscale_prompt` を生成する。
2. The Upscale Prompt Builder shall 元プロンプトに明記されていない被写体特徴を `upscale_prompt` に追加しない。
3. The Upscale Prompt Builder shall 同一入力・同一 preset version に対して同一の `upscale_prompt` を返す。

### Requirement 8: Scope 別 Detailer Prompt 構築
**Objective:** ワークフロー利用者として、各 scope に限定された Detailer プロンプトを得たい。そうすれば、部位ごとに整合した局所ディテール指示を維持できる。

#### Acceptance Criteria
1. When ある scope の task を構築するとき、the Detailer Prompt Builder shall 当該 scope に対応する情報（例: `face` は face・skin・expression・gaze・必要に応じた hairline）だけを対象として `prompt_final` を構築する。
2. The Detailer Prompt Builder shall scope 外の背景や別部位の情報を `prompt_final` に混入させない。
3. The Detailer Prompt Builder shall 顔の再設計・年齢変更・体型変更につながる表現を自動追加しない。
4. The Detailer Prompt Builder shall 対応 7 scope それぞれについて、当該 scope の preset に基づく維持指示・局所ディテール・制限を反映した `prompt_final` を構築する。
5. The Detailer Prompt Builder shall 同一入力・同一 preset version に対して同一の `prompt_final` を返す。

### Requirement 9: 禁止語ポリシー
**Objective:** ワークフロー利用者として、`beautiful`・`perfect`・`symmetrical` などの既定美化語が最終プロンプトへ紛れ込まないようにしたい。そうすれば、意図しない美化や再設計を避けられる。

#### Acceptance Criteria
1. The 禁止語検査 shall version 付きの共有ポリシーリソースから禁止語一覧を読み込む。
2. When `prompt_final` と `upscale_prompt` の各文字列が LLM 出力・preset・fallback 固定文・利用者入力を結合して確定した後、the 禁止語検査 shall その結合後の文字列に対して禁止語を検査する。
3. If 禁止語が検出されたとき、then the 禁止語検査 shall v1 において当該語を除去し、検出語数と対象出力を warning または diagnostics に記録する。
4. The Upscale Prompt Builder と the Detailer Prompt Builder shall 同一の禁止語ポリシーを適用する。
5. The 禁止語検査 shall 禁止語の検出を LLM に委任しない。
6. When 禁止語が 1 件以上除去されたとき、the 禁止語検査 shall 除去後の文字列に対して次の**区切り正規化**を適用し、除去跡の区切り記号・空括弧を残さない。区切り正規化は除去が 1 件も発生しなかった文字列には適用しない。
   1. 空の括弧ペア（`()`・`[]`・`{}`。内部が空白・区切り記号・入れ子の空ペアのみ）を除去する。除去したペアの**両隣が英数字**のときに限り空白 1 つを残し、2 つの生存トークンが 1 語へ融合することを防ぐ（`face(beautiful)eyes` → `face eyes`）。いずれかの隣が英数字以外のときは空白を残さず、利用者が書いた記号の前後関係を変えない（`face(beautiful)-detail` → `face-detail`）。
   2. 区切り記号と空白の連続（`[\s,;.]+`）を、その中で**最も強い区切り 1 つと空白 1 つ**へ畳み込む。強さは `.` > `;` > `,` とする。区切り記号を含まない連続は空白 1 つへ畳み込む。
   3. 文字列の先頭、および括弧の内側の端に接する区切り記号を除去する。文字列末尾に接する区切り記号は、文末を示す `.` を含む場合を除いて除去する（合成後プロンプトの最終文のピリオドを保持するため）。
7. The 禁止語検査 shall 区切り正規化を**文字列全体**に対して一様に適用し、除去位置に限定しない。結果として、除去が発生した文字列では除去箇所から離れた位置の連続区切り（例: `cinematic... dreamlike` の `...`）も正規化される。これは v1 の受容するトレードオフであり、画像生成プロンプトの意味に影響しないことを前提とする。除去位置に限定した修復は v1 の対象外とする。

### Requirement 10: Preset 管理
**Objective:** ワークフロー利用者として、Python コードを変更せずに Upscale / Detailer の文言を preset として管理したい。そうすれば、文言調整に実装変更が不要になる。

#### Acceptance Criteria
1. The Preset Loader shall upscale preset を、`version`・`preset_id`・`quality_details`・`preservation`・`restrictions` を必須項目として読み込む。
2. The Preset Loader shall detailer preset を、`version`・`scope`・`preservation`・`local_details`・`restrictions` を必須項目として読み込む。
3. The Preset Loader shall detailer preset profile を、`version`・`profile_id` および 7 scope すべての mapping を必須項目として読み込む。
4. If preset または profile に必須キーが欠けているとき、then the Preset Loader shall 設定エラーとして報告し、別 preset へ暗黙 fallback しない。
5. If 指定 profile に要求 scope の mapping が欠けている、または mapping 先 detailer preset の `scope` が mapping key と一致しないとき、then the Preset Loader shall 設定エラーとして報告する。
6. The Core Domain shall `detailer_preset_profile` 未指定時に既定 profile `default_v1` を使用する。
7. The Plan Builder shall preset に `default_order` が無い scope について、既定 order 表（`hair`=20、`face`=30、`hands`=40、`upper_body`=50、`body`=60、`clothing`=70、`generic`=90）の値を `order` に設定する。

### Requirement 11: DETAILER_PLAN JSON Schema と contract
**Objective:** 下流 spec と外部 JSON 利用者として、`DETAILER_PLAN` の構造が Schema で明示され検証されることを前提にしたい。そうすれば、不正な Plan JSON を確実に検出できる。

#### Acceptance Criteria
1. The DETAILER_PLAN JSON Schema shall `schema_version`・`requested_scopes`・`tasks`・`warnings`、および各 task の必須フィールドを定義する。
2. The DETAILER_PLAN JSON Schema shall root と task の両方で未知フィールドを拒否する（`additionalProperties: false` 相当）。
3. When Plan JSON が Schema 検証されるとき、the Plan Validator shall Schema に適合しない Plan JSON を拒否する。
4. The contract test shall `schema_version` の互換性と、Schema が定める必須項目・未知フィールド拒否方針を検証する。

### Requirement 12: JSON codec（往復変換）
**Objective:** core 開発者と下流 spec として、Plan を情報欠落なく直列化・復号したい。そうすれば、`detailer_json` と Plan 復元が一貫する。

#### Acceptance Criteria
1. When 完成済み `DetailerPlan` を直列化するとき、the JSON codec shall Plan の全フィールドを保持した JSON 文字列を生成する。
2. When 直列化済み Plan JSON を復号するとき、the JSON codec shall Schema 検証を通過した JSON を等価な `DetailerPlan` に復元する。
3. The JSON codec shall 直列化と復号の往復で情報を欠落させない。
4. If 復号対象 JSON に未知フィールドが含まれるとき、then the JSON codec shall それを黙って破棄せず、Schema 検証で拒否する。
5. If 復号対象 JSON が不正または Schema 非適合であるとき、then the JSON codec shall それを黙って補正せず、明示的なエラーとして報告する。

### Requirement 13: Ollama response Schema の土台
**Objective:** `ollama-prompt-analyzer` の開発者として、抽出結果の構造を検証する Schema の土台を core から得たい。そうすれば、通信実装と Schema 定義を分離できる。

#### Acceptance Criteria
1. The Core Domain shall Ollama 抽出結果を検証するための version 付き response Schema リソースを提供する。
2. The contract test shall response Schema の必須項目と `schema_version` 互換性を検証する。
3. The Core Domain shall Ollama への実通信、client 実装、LLM 向け system prompt テキスト、retry / failure_mode を本 spec に含めない。

### Requirement 14: 非機能要件（独立性・テスト可能性・セキュリティ）
**Objective:** プロジェクト保守者として、core ロジックを外部依存なしにテストでき、安全に動作させたい。そうすれば、下流の全 spec が安定した契約に依存できる。

#### Acceptance Criteria
1. The Core Domain shall ComfyUI・Ollama・ファイルシステムへの依存なしに、domain モデルとルールをテスト可能にする。
2. The Core Domain shall 固定プロンプト文・schema・preset・禁止語ポリシーを Python コードへ直書きせず、version 付きリソースとして扱う。
3. The Core Domain shall 利用者向けエラーと内部例外を区別し、不正 JSON・schema 違反・未対応 scope・preset 設定エラーを明示的に扱う。
4. The Core Domain shall model 出力および利用者入力に対して `eval` や `exec` を使用しない。
5. The Core Domain shall 不正データを黙って破棄せず、warning または明示的エラーとして表面化する。
6. The snapshot test shall 対応 7 scope の Detailer 完成プロンプトと Upscale 完成プロンプトの差分を検出できる。
