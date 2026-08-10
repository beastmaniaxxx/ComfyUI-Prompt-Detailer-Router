# Requirements Document

## Introduction

`ollama-prompt-analyzer` は、`ComfyUI-Prompt-Detailer-Router` の唯一の LLM 接点である `PDR_OllamaPromptAnalyzer` ノードを確定する spec です。利用者は元画像の生成プロンプトと `face,hair,hands` のような scope 指定を 1 つのノードへ与えるだけで、Ultimate SD Upscale 向けの `upscale_prompt` と、複数の Detailer 処理を格納した `DETAILER_PLAN` を得られるようになります。

本 spec の中心は「LLM は抽出、Python は決定」という原則を、外部通信の境界で守り切ることです。Ollama へは元プロンプトに明記された事実の構造化抽出だけを要求し、応答は上流 spec `prompt-detailer-core` が提供する response Schema で検証します。最終プロンプト、`task_id`、維持指示、preset 適用、禁止語検査、Plan 構築は core の決定論的ロジックが担い、本 spec はそこへ「検証済み抽出結果」を届ける責務と、届かなかった場合の振る舞いを所有します。

Ollama はローカルで動作する外部プロセスであり、未起動・モデル未取得・応答揺れが日常的に発生します。そのため本 spec は、失敗の分類、`failure_mode` による分岐、再試行の上限、安全な fallback 出力、`warning` と `diagnostics` の内容を、利用者から観測できる契約として定義します。あわせて、同一入力に対する再現性とキャッシュ再利用の判定基準も確定します。

## Boundary Context

- **In scope**:
  - `PDR_OllamaPromptAnalyzer` ノードの入出力契約
  - Ollama `/api/chat` への抽出要求の構築（構造化出力指定、逐次応答の無効化、思考出力の無効化、生成オプション、`keep_alive`）
  - LLM 向け system prompt と修復指示 prompt の version 付きリソース化
  - chat 応答エンベロープからの抽出結果 JSON の取り出し、JSON 解析、Schema 検証、検証済み抽出結果の確定
  - 呼び出し失敗の分類（接続・タイムアウト・HTTP ステータス対応表・利用不能な応答本文・不正 JSON・Schema 違反・設定エラー）
  - `failure_mode`（`strict` / `retry_once` / `safe_fallback`）の分岐と、失敗種別との全組合せの結果定義
  - `retry_once` の再試行対象・回数上限・時間上限
  - `safe_fallback` の出力内容
  - `warning` と `diagnostics` の内容、および秘密情報の非開示
  - 接続設定（`ollama_url`、`ollama_model`、`timeout`、`temperature`、preset 指定）の検証
  - キャッシュキーの構成要素と、キャッシュ対象とする結果の限定
  - fixture ベースの統合テストと、実 Ollama 依存テストの分離
- **Out of scope**:
  - `DETAILER_PLAN` / Ollama response Schema の形状変更、対応 scope 集合の変更、`task_id` 規則の変更、preset 形式の変更（すべて `prompt-detailer-core` が所有）
  - 最終 `upscale_prompt` / `prompt_final` の合成規則そのもの（core の prompt builder が所有）
  - 禁止語ポリシーの内容と、除去および区切り正規化の規則（core が所有）
  - `PDR_DetailerPlanSelect` / `PDR_DetailerPlanInspector` / `PDR_DetailerPlanFromJSON` と `missing_behavior`
  - JavaScript による動的コンボ更新とグラフ探索
  - cloud LLM、Ollama 以外の LLM backend、複数人物の完全対応（`subject_id` は既定 `main`）
  - packaging、Registry 対応、example workflow の同梱、CI 定義
- **Adjacent expectations**:
  - `prompt-detailer-core` は、scope 正規化規則、Ollama response Schema、検証済み抽出結果の表現、Upscale / Detailer prompt builder、Plan Builder、Plan Validator、JSON codec、禁止語ポリシーを提供する。Analyzer はこれらを再実装せずそのまま用い、独自の正規化・合成・検証規則を持たない。本 spec は fallback 経路を含め、`prompt-detailer-core` の API 変更を必要としない。
  - `detailer-plan-selection` は Analyzer が出力した `DETAILER_PLAN` を消費するが、Ollama 通信・`failure_mode`・diagnostics は所有しない。Analyzer は fallback 出力であっても core の Plan 整合契約を満たした Plan を渡す。
  - `dynamic-detailer-task-combo` は Analyzer の `scopes` 入力値から UI 候補を生成する。Analyzer は `scopes` を利用者が編集可能な STRING 入力として保持し続けるが、UI 候補の生成と維持は所有しない。
  - `packaging-and-release` は依存関係の宣言と example workflow を所有する。本 spec はノードの入出力名と `failure_mode` の選択肢を、ワークフロー互換の対象として安定させる。

## 要件作成時に確定した判断

リファレンス `docs/requirements/requirements-design-reference.md` §27 が未決事項として挙げていた論点のうち、本 spec の範囲に該当するものを次のとおり確定しました。

| 論点 | 決定 | 根拠 |
|---|---|---|
| Analyzer のキャッシュ／再実行制御の所有 | 本 spec でキャッシュキーを確定する（Requirement 11） | 利用者判断。`domain/versions.py` の `PROMPT_BUILDER_VERSION` が「下流 Analyzer のキャッシュキーへ供給」と明記していること、および core design が cache key を analyzer spec 所有としていることと整合 |
| `failure_mode` の既定値（§27-11 関連） | `safe_fallback` | 利用者判断 |
| `ollama_url` の許容範囲（§27-12） | scheme とホスト形式を検証し、宛先ホストの範囲は制限しない。URL 形状は origin のみ許容（Requirement 10.1） | 利用者判断 |
| `retry_once` の再試行対象（§27-8） | Schema 違反・不正 JSON に加え、再試行可能な通信失敗も対象とする | 利用者判断。リファレンス §16 の記述を採用 |
| fallback 時の元プロンプト利用度（§27-9） | `original_prompt` を基礎に upscale preset を結合する（Requirement 7.1） | リファレンス §16 の `safe_fallback` 時 Analyzer 出力の定義に従う |
| `upscale_preset` の既定値 | `minimal` | 利用者判断。3 preset のうち唯一画風に言及せず、「元プロンプトにない特徴を追加しない」製品境界と整合する。採らなかった `photographic` は、イラスト系の元画像に既定のまま適用すると写実方向へ寄る |
| `timeout` の上限と超過時の扱い | 上限 600 秒。超過は設定エラーとし、clamp や既定値への置換をしない（Requirement 10.7 / 10.8） | 利用者判断。Requirement 10.6 / 10.10 の「暗黙の代替をしない」方針と一致させる |
| 空 `original_prompt` の扱い | Ollama を呼び出さず、抽出結果を空として扱う（Requirement 2.9） | 利用者判断。空入力に対する抽出特徴はすべて根拠を欠くため、通常経路で捏造を防ぐ |
| preset 入力のウィジェット型 | UI は COMBO を表示してよいが、Python は任意 STRING として受け取り実行時に照合する（Requirement 1.1 / 1.10 / 1.11） | AGENTS.md §7.2 が `task_id` に定める扱いと §3.2「UI は利便性、バックエンドは正当性」に揃える。COMBO 単独に固定すると、preset ファイルを持たない環境でワークフローを読み込んだ際に値が失われる |

## Requirements

### Requirement 1: Analyzer ノードの入出力契約
**Objective:** ワークフロー利用者として、1 つの Analyzer ノードに元プロンプト・`scopes`・Ollama 設定を与えるだけで Upscale と Detailer に必要な出力を一括で得たい。そうすれば、段階ごとにプロンプトを手作業で転記する必要がなくなる。

#### Acceptance Criteria
1. The Analyzer ノード shall 次の入力を、それぞれ指定の型で受け付ける: `original_prompt`（STRING・複数行）、`scopes`（STRING）、`subject_hint`（STRING）、`ollama_url`（STRING）、`ollama_model`（STRING）、`upscale_preset`（STRING）、`detailer_preset_profile`（STRING）、`seed`（INT）、`temperature`（FLOAT）、`timeout`（FLOAT）、`keep_alive`（STRING）、`failure_mode`（COMBO）。
2. The Analyzer ノード shall `upscale_prompt`（STRING）、`detailer_plan`（`DETAILER_PLAN`）、`detailer_json`（STRING）、`warning`（STRING）、`diagnostics`（STRING）の 5 出力を提供する。
3. The Analyzer ノード shall `failure_mode` の選択肢を `strict`、`retry_once`、`safe_fallback` の 3 種に限定し、既定値を `safe_fallback` とする。
4. The Analyzer ノード shall `ollama_model` の既定値を空文字とし、特定の環境に固有なモデル名を既定値として持たない。
5. The Analyzer ノード shall `upscale_preset` の既定値を `minimal` とし、`detailer_preset_profile` の既定値を `default_v1` とする。
6. When `scopes` が渡されたとき、the Analyzer shall 上流 core spec と同一の scope 正規化規則を適用し、独自の正規化規則を持たない。
7. If 正規化後の `requested_scopes` が空であるとき、then the Analyzer shall task を 1 件も含まない `DETAILER_PLAN` を出力し、その旨を `warning` に記録し、実行を失敗させない。
8. When 出力を確定するとき、the Analyzer shall `detailer_json` を、同時に出力する `detailer_plan` を直列化した内容と一致させる。
9. The Analyzer ノード shall 部位ごとの固定出力ソケットを追加せず、実行結果に応じて出力ソケットの数や名前を変更しない。
10. Where `upscale_preset` または `detailer_preset_profile` を UI 上で選択肢として提示するとき、the Analyzer ノード shall 候補を、対応する preset リソースディレクトリ直下の JSON ファイル名 stem のうち安全な識別子形式（英数字・`-`・`_` のみ）を満たすものから、辞書順で構築する。
11. The Analyzer shall UI が提示した候補値を正当性の根拠として信頼せず、`upscale_preset` と `detailer_preset_profile` を任意の STRING として受け取り、実行時に Requirement 10.10 の照合を行う。
12. The Analyzer ノード shall 通常出力・fallback 出力のいずれの場合も、core の Plan 整合契約を満たす `DETAILER_PLAN` だけを出力する。

### Requirement 2: 抽出リクエストの構築
**Objective:** プロジェクト保守者として、LLM への要求を「元プロンプトに明記された事実の構造化抽出」に限定したい。そうすれば、未指定情報の混入と出力揺れを入口の時点で抑えられる。

#### Acceptance Criteria
1. The Analyzer shall Ollama の `/api/chat` エンドポイントへ、逐次応答を無効化し思考出力を無効化した単一の抽出要求を送信する。
2. The Analyzer shall 抽出要求の構造化出力指定に、core spec が提供する Ollama response Schema の実際の `properties`・`required`・未知フィールド方針を渡し、空 Schema や簡略化した Schema を渡さない。
3. The Analyzer shall LLM 向けの system prompt と修復指示 prompt を version 付きリソースとして保持し、Python コードへ直書きしない。
4. The Analyzer shall 抽出要求に、正規化済み scope 列、`subject_hint`、`original_prompt` を含める。
5. When `subject_hint` が空文字または空白のみであるとき、the Analyzer shall 当該項目を抽出要求から省略する。
6. The Analyzer shall `subject_hint` を抽出対象の優先順位付けと警告生成の補助にのみ用い、元プロンプトに無い特徴を補完する根拠として扱わない。
7. The Analyzer shall `seed` と `temperature` を生成オプションとして送信し、`keep_alive` を指定された値のまま送信する。
8. The Analyzer shall LLM に `task_id`、`prompt_final`、維持指示、preset 文言、最終 `upscale_prompt` を生成させない。
9. If `original_prompt` が空文字または空白のみであるとき、then the Analyzer shall これを設定エラーとして扱わず、Ollama への抽出要求を送信せず、抽出結果を空として扱い、抽出を行わなかった旨を `warning` に記録する。

### Requirement 3: 応答の検証と抽出結果の確定
**Objective:** ワークフロー利用者として、LLM の応答が契約どおりであることを確認したうえで後続処理へ進みたい。そうすれば、壊れたデータや scope 外の情報を含んだまま画像生成へ進むことがない。

#### Acceptance Criteria
1. When Ollama から HTTP 応答を受け取ったとき、the Analyzer shall 応答本文を Ollama の chat 応答エンベロープとして解析し、抽出結果 JSON を `message.content` の文字列として取り出す。
2. If 応答本文をエンベロープとして解析できない、またはエンベロープが `message.content` を含まないとき、then the Analyzer shall 分類 (f) JSON 解析失敗として扱い、エンベロープ自体を抽出結果 Schema で検証しない。
3. When `message.content` を取り出したとき、the Analyzer shall その文字列を JSON として解析し、core spec の Ollama response Schema に対して検証する。
4. If `message.content` の JSON が Schema に適合しないとき、then the Analyzer shall それを黙って補正・部分採用せず、分類 (g) Schema 違反として扱う。
5. The Analyzer shall 抽出結果 JSON に未知フィールドが含まれる場合を、Schema 検証で拒否する。
6. When 抽出結果 JSON が `schema_version` を含まないとき、the Analyzer shall 検証前に現行の response schema version を注入する。
7. If 抽出結果 JSON が現行と異なる `schema_version` を明示しているとき、then the Analyzer shall 分類 (g) Schema 違反として扱い、version 差を吸収しない。
8. When 検証を通過した抽出結果に `requested_scopes` へ含まれない scope の特徴が含まれるとき、the Analyzer shall 当該特徴を後続処理へ渡さず、無視した scope 名を `warning` に記録する。
9. When 抽出結果の特徴文字列が前後空白を除去した結果として空になるとき、the Analyzer shall 当該要素を破棄し、破棄した件数を `diagnostics` に記録する。
10. When 抽出結果に LLM 由来の `warnings` が含まれるとき、the Analyzer shall それを LLM 由来と識別できる形で `warning` 出力に含める。
11. The Analyzer shall `upscale_prompt` と `DETAILER_PLAN` の構築を core spec の決定論的ロジックに委ね、抽出結果に含まれる値を最終出力へ直接採用しない。
12. The Analyzer shall 応答本文および `message.content` をコードとして評価せず、HTML としても解釈しない。
13. The Analyzer shall v1 において、抽出結果の各特徴が `original_prompt` に実在するかの照合を行わない。元プロンプトにない特徴を追加しないことの担保は、抽出要求で明記された事実のみを求めること（Requirement 2.1–2.8）と、空入力では抽出を行わないこと（Requirement 2.9）に限定する。全特徴の根拠照合は、部分一致・語形変化・言い換えの判定基準が仕様に存在しないまま実装すると解釈が収束しないため v1 の対象外とし、これを受容するトレードオフとする。

### Requirement 4: Ollama 呼び出し失敗の分類
**Objective:** ワークフロー利用者として、失敗の原因を区別して把握したい。そうすれば、Ollama 未起動なのか、モデル未取得なのか、LLM 出力の問題なのかを切り分けられる。

#### Acceptance Criteria
1. The Analyzer shall 失敗を、次の 8 分類のいずれか 1 つに分類する: (a) 接続失敗、(b) タイムアウト、(c) 再試行可能な HTTP エラー、(d) 再試行不可の HTTP エラー、(e) 利用不能な応答本文、(f) JSON 解析失敗、(g) Schema 違反、(h) 設定エラー。
2. When HTTP 応答のステータスコードが 2xx 以外であるとき、the Analyzer shall 次の対応表に従って分類する。

   | ステータスコード | 分類 |
   |---|---|
   | 408、429、500、502、503、504 | (c) 再試行可能な HTTP エラー |
   | 上表以外の 4xx（400、401、403、404 等） | (d) 再試行不可の HTTP エラー |
   | 上表以外の 5xx（501、505 等） | (d) 再試行不可の HTTP エラー |
   | 上表のいずれにも該当しない 2xx 以外の値 | (d) 再試行不可の HTTP エラー |

3. The Analyzer shall モデル不存在を、ステータスコード 404 として分類 (d) に対応付け、エラー本文のテキスト一致による判定を行わない。エラー本文は `diagnostics` へ要約して出力する。
4. The Analyzer shall HTTP 応答本文に上限サイズ 1 MiB を設け、上限を超える応答本文を解析せず後続処理へ渡さない。
5. The Analyzer shall 次のいずれかに該当する場合を分類 (e) 利用不能な応答本文として扱う: HTTP 応答本文が空である、HTTP 応答本文が上限サイズを超えている、エンベロープの `message.content` が空である、`message.content` が空白のみである。
6. The Analyzer shall 分類 (a)、(b)、(c)、(e)、(f)、(g) を**再試行可能な失敗**と定義し、分類 (d) と (h) を**再試行不可の失敗**と定義する。
7. The Analyzer shall 分類した失敗種別を `diagnostics` に出力する。ただし Requirement 4.9 に該当する場合は、エラーメッセージへ出力する。
8. If 失敗が発生したとき、then the Analyzer shall 内部例外の型名や stack trace を `upscale_prompt`・`warning`・`diagnostics`・エラーメッセージへそのまま到達させない。
9. When 明示的なエラーとして扱う経路（Requirement 5.2 / 5.3 / 5.4 / 6.5）で失敗が発生したとき、the Analyzer shall 失敗した事実・分類・原因・`failure_mode` をエラーメッセージへ含め、`warning` と `diagnostics` を出力しない。
10. When 出力を生成する経路（通常出力、再試行成功、fallback 出力）で失敗が発生したとき、the Analyzer shall 失敗した事実と分類を `warning` と `diagnostics` の双方に記録する。

### Requirement 5: failure_mode による分岐
**Objective:** ワークフロー利用者として、Ollama 障害時の振る舞いを明示的に選びたい。そうすれば、試行錯誤中はワークフローを止めず、最終生成時は意図しないプロンプトのまま先へ進めない、という使い分けができる。

#### Acceptance Criteria
1. When 抽出要求が成功し応答が Schema 検証を通過したとき、the Analyzer shall `failure_mode` の値によらず通常出力（`upscale_prompt`・`detailer_plan`・`detailer_json`）を返す。
2. If 分類 (h) 設定エラーが発生したとき、then the Analyzer shall `failure_mode` の値によらず明示的なエラーとして扱い、fallback 出力を返さない。
3. If 再試行可能な失敗（Requirement 4.6）が発生し `failure_mode` が `strict` であるとき、then the Analyzer shall 再試行せず明示的なエラーとして扱う。
4. If 分類 (d) 再試行不可の HTTP エラーが発生し `failure_mode` が `strict` または `retry_once` であるとき、then the Analyzer shall 再試行せず明示的なエラーとして扱う。
5. If 再試行可能な失敗（Requirement 4.6）が発生し `failure_mode` が `retry_once` であるとき、then the Analyzer shall Requirement 6 の規則に従って再試行する。
6. If 分類 (h) 設定エラー以外の失敗が発生し `failure_mode` が `safe_fallback` であるとき、then the Analyzer shall 再試行せず Requirement 7 の fallback 出力を返す。
7. The Analyzer shall Requirement 4.1 の 8 分類と `failure_mode` の 3 種による全 24 通りの組合せが、通常出力・再試行・明示的なエラー・fallback 出力のいずれか 1 つだけに対応するようにし、未定義の組合せを残さない。
8. When 明示的なエラーとして扱うとき、the Analyzer shall 5 出力のいずれも生成せずにワークフロー実行を失敗させ、失敗種別と原因を Requirement 4.9 の形で利用者へ提示する。

### Requirement 6: retry_once の再試行規則
**Objective:** ワークフロー利用者として、一過性の失敗を 1 回だけ自動で取り戻したい。そうすれば、待ち時間を無制限に伸ばすことなく、偶発的な失敗で作業が止まる頻度を下げられる。

#### Acceptance Criteria
1. The Analyzer shall `retry_once` における再試行回数の上限を 1 回とし、無限再試行および 2 回以上の再試行を行わない。
2. When 再試行対象が分類 (f) JSON 解析失敗または分類 (g) Schema 違反であるとき、the Analyzer shall version 付きの修復指示 prompt を加えた要求で再試行する。
3. When 再試行対象が分類 (a) 接続失敗、(b) タイムアウト、(c) 再試行可能な HTTP エラー、または (e) 利用不能な応答本文であるとき、the Analyzer shall 初回と同一内容の要求で再試行する。
4. When 再試行の応答が Schema 検証を通過したとき、the Analyzer shall 通常出力を返し、再試行を実施した事実を `warning` と `diagnostics` に記録する。
5. If 再試行後も失敗するとき、then the Analyzer shall fallback 出力へ移行せず、明示的なエラーとして扱う。
6. The Analyzer shall `timeout` を 1 回の Ollama 要求あたりの上限として適用し、再試行を含む総待機時間が `timeout` の 2 倍を超えないようにする。

### Requirement 7: safe_fallback の出力
**Objective:** ワークフロー利用者として、Ollama が使えない状況でもワークフローを完走させたい。そうすれば、Ollama の起動状態に関係なく Upscale と Detailer の接続構成を確認・実行できる。

#### Acceptance Criteria
1. When `failure_mode` が `safe_fallback` で分類 (h) 設定エラー以外の失敗が発生したとき、the Analyzer shall `original_prompt` を記述部とする抽出結果を組み立て、それを通常出力と同一の core Upscale Prompt Builder へ渡して `upscale_prompt` を非空文字列として生成する。
2. The Analyzer shall preset 文言の結合順序・区切り・禁止語検査を自前で実装せず、core の Upscale Prompt Builder と Plan Builder に委ねる。この構築経路は上流 spec `prompt-detailer-core` の API 変更を必要としない。
3. When `failure_mode` が `safe_fallback` で分類 (h) 設定エラー以外の失敗が発生したとき、the Analyzer shall 正規化済み `requested_scopes` の各 scope に対して `enabled=true` の fallback task を持つ `DETAILER_PLAN` を生成する。
4. The Analyzer shall fallback task の `extracted_features` を空とし、`prompt_final` を当該 scope の preset から構築した非空文字列とする。
5. The Analyzer shall fallback 出力に、元プロンプトへ明記されていない視覚的特徴を確定情報として追加しない。
6. The Analyzer shall fallback 出力の `detailer_json` を、生成した fallback Plan を直列化した内容とする。
7. When fallback 出力を返すとき、the Analyzer shall fallback した理由、分類した失敗種別、生成した fallback task 数を `warning` に含める。
8. The Analyzer shall fallback 出力の `upscale_prompt` と各 `prompt_final` に対しても、通常出力と同一の禁止語ポリシーを適用する。
9. The Analyzer shall fallback 出力を通常出力と同じ 5 出力の形で返し、出力ソケットの構成を変更しない。
10. The Analyzer shall fallback では抽出が行えず被写体特徴の取捨選択ができないため、`original_prompt` 全文が `upscale_prompt` の記述部となることを受容する。採らなかった案は core へ raw prompt 専用の fallback builder を追加することであり、上流 spec の変更を要するため v1 では選択しない。

### Requirement 8: warning 出力
**Objective:** ワークフロー利用者として、実行中に何が起きたかを 1 つの出力から把握したい。そうすれば、無視された入力や自動で補われた部分を見落とさずに済む。

#### Acceptance Criteria
1. The Analyzer shall `warning` に、破棄した未対応 scope、空の `requested_scopes`、空 `original_prompt` により抽出を行わなかった事実、生成した fallback task、除去した禁止語、無視した scope 外特徴、LLM 由来の warning、再試行の実施、fallback の理由のうち、発生したものをすべて含める。
2. When warning に該当する事象が 1 件も発生しなかったとき、the Analyzer shall `warning` を空文字として出力する。
3. The Analyzer shall warning を、利用者が原因と対処を判断できる自然文として表現する。
4. The Analyzer shall 同一入力・同一応答に対して、warning の内容と並び順を同一にする。
5. The Analyzer shall 失敗を warning のみで表現して黙って成功扱いにせず、Requirement 5 が定める分岐結果を必ず伴わせる。

### Requirement 9: diagnostics 出力と秘密情報の非開示
**Objective:** ワークフロー利用者および保守者として、出力がどの設定・どの version から生成されたかを確認したい。そうすれば、再現しない結果の原因を特定でき、同時に接続情報が意図せず露出しない。

#### Acceptance Criteria
1. The Analyzer shall `diagnostics` に、`failure_mode`、再試行の実施有無と回数、失敗種別、Ollama 応答までの所要時間、fallback 使用有無と理由、キャッシュ再利用の有無、破棄した空の特徴要素の件数、HTTP エラー本文の要約を含める。
2. The Analyzer shall `diagnostics` に、使用した model 名、`upscale_preset` の id と version、`detailer_preset_profile` の id と version、禁止語ポリシーの id と version、prompt builder version、response schema version、system prompt version を含める。
3. Where `diagnostics` に Ollama 接続先を含めるとき、the Analyzer shall scheme・ホスト・ポートのみを出力し、利用者名やパスワードを含む userinfo、パス、クエリ文字列を出力しない。
4. The Analyzer shall `diagnostics` と `warning` にローカルファイルシステムの絶対パスを出力しない。
5. The Analyzer shall 失敗時だけでなく成功時にも `diagnostics` を出力する。
6. The Analyzer shall 同一入力・同一応答に対して、`diagnostics` の項目集合と並び順を同一にする。

### Requirement 10: 接続設定と preset 指定の検証
**Objective:** ワークフロー利用者として、設定の誤りを通信前に具体的なエラーとして知りたい。そうすれば、原因不明の通信エラーとして扱われることなく、修正すべき入力が分かる。

#### Acceptance Criteria
1. When `ollama_url` が与えられたとき、the Analyzer shall 次の決定表に従って各 URL 構成要素を判定する。

   | 構成要素 | 判定 |
   |---|---|
   | scheme | `http` または `https` のみ許容。それ以外は分類 (h) 設定エラー |
   | userinfo（利用者名・パスワード） | 非空なら分類 (h) 設定エラー（v1 は認証付き Ollama 非対応） |
   | ホスト | 空なら分類 (h) 設定エラー。値の範囲は制限しない |
   | ポート | 任意。省略時は scheme の既定ポートを実効値とする |
   | パス | 空または `/` のみ許容。それ以外は分類 (h) 設定エラー |
   | クエリ | 非空なら分類 (h) 設定エラー |
   | フラグメント | 非空なら分類 (h) 設定エラー |

2. When `ollama_url` が Requirement 10.1 の全判定を通過したとき、the Analyzer shall 要求先 endpoint を `scheme://ホスト[:ポート]` に `/api/chat` を連結して構成する。
3. If `ollama_url` が Requirement 10.1 のいずれかで設定エラーと判定されたとき、then the Analyzer shall Ollama への要求を送信しない。
4. The Analyzer shall `ollama_url` の宛先ホストの範囲を制限せず、ローカルホスト以外の Ollama サーバーへの接続を許容する。
5. The Analyzer shall v1 において、パス prefix を持つリバースプロキシ配下の Ollama（例: `http://host/ollama`）を非対応とすることを受容する。採らなかった案はパスを prefix として保持し `/api/chat` を連結するもので、`http://host/api/chat` という誤入力が `/api/chat/api/chat` として送信され失敗原因の特定が困難になるため選択しない。
6. If `ollama_model` が空文字または空白のみであるとき、then the Analyzer shall 分類 (h) 設定エラーとして報告し、暗黙の既定モデル名で代替しない。
7. The Analyzer shall `timeout` の有効範囲を `0 < timeout <= 600`（秒、上限を含む）とする。
8. If `timeout` が 0 以下、または 600 秒を超えるとき、then the Analyzer shall 分類 (h) 設定エラーとして報告し、上限値への丸め込みや既定値への置換を行わない。
9. If `temperature` が負値であるとき、then the Analyzer shall 分類 (h) 設定エラーとして報告する。
10. If 指定された `upscale_preset` または `detailer_preset_profile` が存在しない、必須キーを欠く、またはファイル内の `preset_id` / `profile_id` が要求 id と一致しないとき、then the Analyzer shall 分類 (h) 設定エラーとして報告し、別 preset へ暗黙に fallback しない。
11. The Analyzer shall 設定エラーを、Ollama の障害と区別できる分類として Requirement 4.9 のエラーメッセージへ含める。

### Requirement 11: 再現性とキャッシュキー
**Objective:** ワークフロー利用者として、設定を変えていないのに出力が変わったり、preset を変えたのに古い結果が使われたりする状態を避けたい。そうすれば、生成結果の差分がどの変更に由来するかを判断できる。

#### Acceptance Criteria
1. While Ollama が同一の応答を返す状況において、the Analyzer shall 同一の入力・同一 preset version・同一の禁止語ポリシー version・同一の prompt builder version に対して、`upscale_prompt`・`detailer_plan`・`detailer_json`・`warning` の 4 出力を同一にする。
2. The Analyzer shall `diagnostics` を Requirement 11.1 の同一性契約の対象外とする。`diagnostics` は応答所要時間やキャッシュ再利用の有無など実行ごとに変化する値を含むため、Requirement 9.6 が定める項目集合と並び順の同一性のみを満たす。
3. The Analyzer shall キャッシュキーを、`original_prompt`、正規化済み scope 列、`subject_hint`、正規化した接続先識別子、model 名、`seed`、`temperature`、正規化した `timeout`、`failure_mode`、system prompt の id と version、修復指示 prompt の id と version、response schema version、`upscale_preset` の id と version、`detailer_preset_profile` の id と version、禁止語ポリシーの id と version、prompt builder version から構成する。
4. The Analyzer shall キャッシュキーにおける「正規化した接続先識別子」を `scheme://小文字化したホスト:実効ポート` とし、「正規化した `timeout`」を Requirement 10.7 の検証を通過した秒値を小数第 3 位で丸めた値とする。
5. The Analyzer shall `keep_alive`、UI 表示設定、`diagnostics` の表示形式をキャッシュキーに含めない。
6. The Analyzer shall 抽出要求・応答検証・prompt 構築のすべてに成功した結果のみをキャッシュ対象とする。
7. The Analyzer shall `safe_fallback` で生成した fallback 出力をキャッシュ対象としない。
8. The Analyzer shall `strict` または `retry_once` で最終的に失敗した結果をキャッシュ対象としない。
9. When キャッシュキーの構成要素が 1 つでも変化したとき、the Analyzer shall キャッシュ済み結果を再利用せず、抽出要求を再実行する。
10. When キャッシュ済み結果を再利用したとき、the Analyzer shall Ollama への要求を送信せず、再利用した事実を `diagnostics` に記録する。

### Requirement 12: 非機能要件（セキュリティ・テスト可能性・ランタイム）
**Objective:** プロジェクト保守者として、LLM 応答を安全に扱い、実 Ollama なしで振る舞いを検証したい。そうすれば、外部プロセスの状態に左右されずに品質を保てる。

#### Acceptance Criteria
1. The Analyzer shall Ollama 応答および利用者入力に対して `eval` や `exec` を使用しない。
2. The Analyzer shall Ollama 応答を実行可能なコードとして扱わず、raw HTML として描画しない。
3. The Analyzer shall 無限再試行および無制限の待機を行わない。
4. The Analyzer shall 通信・検証・再試行・fallback を含む主要な振る舞いを、実 Ollama を起動せずに fixture 応答で検証可能にする。
5. The 統合テスト shall 成功応答、エンベロープ不正応答、`message.content` 欠落応答、`message.content` の Schema 違反応答、`message.content` の不正 JSON 応答、空応答、上限サイズ超過応答、接続失敗、タイムアウト、再試行可能な HTTP エラー、再試行不可の HTTP エラーの各 fixture について、3 種の `failure_mode` での出力を検証する。
6. The 統合テスト shall 空 `original_prompt` の入力について、Ollama へ要求が送信されないことと、抽出結果が空として扱われることを検証する。
7. The 統合テスト shall 実 Ollama を必要とするテストを通常のテスト実行から分離し、明示的に有効化された場合のみ実行する。
8. The Analyzer shall Python 3.10 で動作する。
