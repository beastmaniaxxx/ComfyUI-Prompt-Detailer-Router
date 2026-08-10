# AGENTS.md

## 1. このファイルの目的

このリポジトリで作業するCodexおよびその他の実装エージェント向けの開発規約です。

対象プロジェクト:

- リポジトリ名: `ComfyUI-Prompt-Detailer-Router`
- Pythonパッケージ名: `prompt_detailer_router`
- ノードID接頭辞: `PDR_`
- 主要用途:
  - 元画像の生成プロンプトをOllamaで構造化解析する
  - Ultimate SD Upscale向けの`upscale_prompt`を生成する
  - 複数のDetailer処理を`DETAILER_PLAN`として生成する
  - `DETAILER_PLAN`から対象タスクを選択して`detailer_prompt`を取得する
  - Analyzerの`scopes`入力からSelectorの候補を動的に更新する

### 1.1 ルール

本ファイルは実装時の強制ルールです。仕様や設計の詳細は、次の文書を参照してください。

- `docs/requirements/requirements-design-reference.md`

### 1.2 言語設定

チャットでの応答は必ず日本語で行ってください。
設計文書を、極力日本語で作成してください。

---

## 2. 優先順位

実装判断が競合した場合は、次の順で優先します。

1. cc-sddで承認済みの`requirements.md`
2. cc-sddで承認済みの`design.md`
3. cc-sddで承認済みの`tasks.md`
4. 本ファイル
5. `docs/requirements/requirements-design-reference.md`
6. 既存コードとテスト
7. READMEや補足ドキュメント

承認済み仕様と本ファイルが矛盾する場合は、勝手に仕様を解釈して進めず、差異を明示してください。

---

## 3. 中核となる設計原則

### 3.1 LLMは抽出、Pythonは決定

LLMの責務:

- 元プロンプトに明記された事実の抽出
- 情報のカテゴリ分類
- 指定されたscopeに関係する特徴の抽出
- 構造化JSONの返却

Pythonの責務:

- scopeの正規化
- `task_id`の生成
- JSON Schema検証
- プリセット適用
- 維持指示や局所ディテール文の追加
- 重複除去
- 禁止語検査
- フォールバック
- 最終的な`prompt_final`の決定

LLMに最終プロンプトの自由生成を丸投げしないでください。

### 3.2 UIは利便性、バックエンドは正当性

JavaScriptフロントエンドの責務:

- 接続元Analyzerの探索
- `scopes`の解析
- コンボボックス候補の更新
- 現在値の維持
- ワークフロー読込時のUI復元

Pythonバックエンドの責務:

- 選択された`task_id`の再検証
- `DETAILER_PLAN`に存在しない値の拒否またはフォールバック
- 型とデータ整合性の保証

フロントエンドの候補値を信頼しないでください。

### 3.3 独自型を中心に設計

複数のDetailer結果は、固定数の出力ソケットではなく、`DETAILER_PLAN`に格納します。

主出力:

- `upscale_prompt: STRING`
- `detailer_plan: DETAILER_PLAN`
- `detailer_json: STRING`
- `warning: STRING`
- `diagnostics: STRING`

`face_prompt`、`hair_prompt`などの固定出力は、本体Analyzerではなく補助Unpackノードで提供してください。

### 3.4 ComfyUI依存を隔離

- ノードクラスは`nodes/`に置く
- ComfyUI APIのimportは`compat.py`に集約する
- ドメインロジックはComfyUIを起動せずにテスト可能にする
- Ollama通信は`infrastructure/ollama_client.py`に隔離する
- プロンプト固定文をPythonコードへ直書きしない

---

## 4. 推奨アーキテクチャ

```text
prompt_detailer_router/
├─ nodes/            # ComfyUI入出力アダプタ
├─ domain/           # DETAILER_PLAN、scope、エラーなど
├─ application/      # ユースケース
├─ infrastructure/   # Ollama、JSON、プリセットI/O
├─ resources/        # prompt、schema、preset
└─ utils/            # 純粋な小規模ユーティリティ

web/js/              # ComfyUIフロントエンド拡張
tests/               # unit / integration / contract / frontend
```

依存方向:

```text
nodes
  ↓
application
  ↓
domain

application
  ↓
infrastructure

domainはComfyUI、Ollama、ファイルシステムへ依存しない
```

循環依存を作らないでください。

---

## 5. `DETAILER_PLAN`の必須契約

基準データ構造:

```json
{
  "schema_version": 1,
  "requested_scopes": ["face", "hair"],
  "tasks": [
    {
      "task_id": "main.face",
      "subject_id": "main",
      "scope": "face",
      "extracted_features": [
        "dark brown eyes"
      ],
      "prompt_core": "dark brown eyes",
      "prompt_final": "Completed face detailer prompt.",
      "order": 30,
      "enabled": true,
      "warnings": []
    },
    {
      "task_id": "main.hair",
      "subject_id": "main",
      "scope": "hair",
      "extracted_features": [
        "short black hair"
      ],
      "prompt_core": "short black hair",
      "prompt_final": "Completed hair detailer prompt.",
      "order": 20,
      "enabled": true,
      "warnings": []
    }
  ],
  "warnings": []
}
```

必須ルール:

- `schema_version`を必須とする
- `task_id`はPlan内で一意
- 初期仕様では`task_id = subject_id + "." + scope`
- `scope`は正規化済みの小文字
- `prompt_final`は有効タスクでは空にしない
- `requested_scopes`は重複を含まない
- 未知のフィールドを許可するかはSchemaで明示する
- Pythonオブジェクトは可能な限り不変なdataclassで表現する
- JSONとの往復変換で情報を失わない

---

## 6. scopeの処理規則

入力例:

```text
Face, hair, face,  hands
```

正規化結果:

```json
["face", "hair", "hands"]
```

処理順:

1. カンマで分割
2. 前後空白を削除
3. 小文字化
4. 空要素を削除
5. 入力順を維持したまま重複削除
6. 対応scopeと照合
7. 未対応scopeをwarningまたはerrorへ変換

初期対応scope:

- `face`
- `hair`
- `hands`
- `body`
- `upper_body`
- `clothing`
- `generic`

scopeの追加は、次を同一変更で更新してください。

- ドメイン定義
- JSON Schema
- 対応プリセット
- テスト
- ドキュメント
- フロントエンド候補処理

---

## 7. ノード仕様の基本方針

### 7.1 `PDR_OllamaPromptAnalyzer`

主入力:

- `original_prompt: STRING`
- `scopes: STRING`
- `subject_hint: STRING`
- `ollama_url: STRING`
- `ollama_model: STRING`
- `upscale_preset: COMBOまたはSTRING`
- `detailer_preset_profile: COMBOまたはSTRING`
- `seed: INT`
- `temperature: FLOAT`
- `timeout: FLOAT`
- `keep_alive: STRING`
- `failure_mode: COMBO`

主出力:

- `upscale_prompt: STRING`
- `detailer_plan: DETAILER_PLAN`
- `detailer_json: STRING`
- `warning: STRING`
- `diagnostics: STRING`

### 7.2 `PDR_DetailerPlanSelect`

主入力:

- `detailer_plan: DETAILER_PLAN`
- `task_id: STRING`
- `missing_behavior: COMBO`

UI上の`task_id`はコンボとして表示してよいですが、Python側は任意STRINGとして受け取り、必ずPlanと照合してください。

主出力:

- `detailer_prompt: STRING`
- `scope: STRING`
- `subject_id: STRING`
- `task_id: STRING`
- `found: BOOLEAN`
- `warning: STRING`

### 7.3 `PDR_DetailerPlanInspector`

- Planの内容を人間が確認しやすい文字列に変換する
- データを変更しない
- デバッグ用途に限定する

### 7.4 `PDR_DetailerPlanFromJSON`

- LLM Text Processorで検証済みのJSONを`DETAILER_PLAN`へ変換する
- Schema検証を必須とする
- 不正JSONを黙って補正しない
- 修復モードを設ける場合は明示的な設定にする

---

## 8. 動的コンボの実装規約

初期対応:

- AnalyzerからSelectorへの直接接続
- Reroute経由
- 同一グラフ内

初期対象外:

- SetNode/GetNode経由
- サブグラフをまたぐ探索
- LLM実行結果からの完全な人物別候補同期
- 実行結果に応じた動的出力ソケット

コンボ候補はまずAnalyzerの`scopes`から構築します。

例:

```text
face,hair,hands
```

候補:

```text
main.face
main.hair
main.hands
```

複数人物対応後は、実際のPlanまたは明示的subject定義から次の形式を使用します。

```text
left_person.face
right_person.face
```

動的コンボ更新時:

- 現在値が候補内にあれば維持
- 候補から消えた場合は安全な先頭候補へ変更
- 候補が空なら空文字へ変更
- CanvasをDirtyにする
- ワークフロー読込時にも再計算する
- 例外でComfyUI全体を停止させない

---

## 9. Ollama連携規約

使用API:

- 原則として`POST /api/chat`
- `stream: false`
- Structured OutputまたはJSON Schemaを使用
- `think: false`を初期値とする

必須対応:

- 接続エラー
- HTTPエラー
- モデル不存在
- タイムアウト
- 不正JSON
- Schema違反
- 空レスポンス
- retry回数の上限
- `keep_alive`
- レスポンス時間などのdiagnostics

セキュリティ:

- 任意のコードを実行しない
- `eval`、`exec`を使用しない
- レスポンスをHTMLとして無加工描画しない
- URLやモデル名をログへ出す場合、秘密情報を含めない
- タイムアウトを無制限にしない

---

## 10. プロンプト生成規約

### Upscale

主に利用する情報:

- medium / style
- lighting
- camera
- material
- texture
- environment
- subjectの必要最小限の特徴

短い維持指示と具体的な品質向上指示を組み合わせます。

### Detailer

scopeごとに対象情報を限定します。

- `face`: face、skin、expression、必要に応じてhairline
- `hair`: hair、hairline、strand、volume、color
- `hands`: hands、fingers、nails、accessories
- `clothing`: clothing、material、pattern、seams、folds
- `upper_body`: face、hair、skin、upper body、clothing
- `body`: body、skin、clothing
- `generic`: 対象物の形状、材質、表面情報

禁止事項:

- 元プロンプトにない特徴を確定情報として追加しない
- `beautiful`、`perfect`、`symmetrical`等を既定で付加しない
- 顔の再設計や年齢変更につながる表現を自動追加しない
- scope外の背景や別部位の情報を混入させない

---

## 11. リソース管理

固定文、Schema、system promptは`resources/`で管理します。

```text
resources/
├─ prompts/
├─ schemas/
└─ presets/
   ├─ upscale/
   └─ detailer/
```

ルール:

- 固定プロンプトをPythonへ直書きしない
- すべてのpresetにバージョンを持たせる
- Schema変更時は`schema_version`を検討する
- 既存Schemaの破壊的変更を避ける
- preset変更はsnapshot testで差分を確認する

---

## 12. Python実装規約

- Python 3.10以上を前提とする
- 公開関数と複雑な内部関数に型ヒントを付ける
- domainモデルはdataclassを優先する
- 小さな純粋関数へ分割する
- 幅広い`except Exception`でエラーを握りつぶさない
- ユーザー向けエラーと内部例外を分ける
- ComfyUIノードクラスへ業務ロジックを書かない
- `requests`等の外部依存追加は必要性を説明する
- 標準ライブラリで十分なら依存を増やさない

---

## 13. JavaScript実装規約

- `extension.js`は登録処理に限定する
- scope解析、グラフ探索、widget更新を別モジュールに分離する
- 純粋関数はNode.jsで単体テスト可能にする
- グローバル状態を最小化する
- ノード削除後の参照を保持しない
- イベントやcallbackを二重登録しない
- LiteGraphやComfyUI内部APIへの依存箇所を集中させる
- UI更新失敗時もワークフロー実行を妨げない

---

## 14. テスト要件

変更には原則としてテストを追加または更新してください。

必須カテゴリ:

### Unit

- scope解析
- task_id生成
- DetailerPlan検証
- preset結合
- prompt builder
- task selector
- JSON codec

### Contract

- OllamaレスポンスSchema
- DetailerPlan Schema
- preset必須キー
- schema_version互換性

### Integration

- fixtureレスポンスからAnalyzer出力まで
- JSONからPlanへの変換
- Plan Selectのmissing behavior

### Frontend

- scope parser
- 候補生成
- 現在値の維持
- 候補削除時のフォールバック
- Reroute探索

### Snapshot

- Upscale完成プロンプト
- scope別Detailer完成プロンプト

実Ollamaを必要とするテストは通常CIから分離し、環境変数が設定された場合のみ実行してください。

---

## 15. 実装前の確認事項

作業開始時に次を確認してください。

1. 対象spec名
2. 対象task
3. 変更対象レイヤー
4. Schema変更の有無
5. ノード入出力変更の有無
6. ワークフロー互換性への影響
7. presetやsnapshotへの影響
8. PythonとJavaScriptの両方に変更が必要か
9. §22 の頻出指摘チェックリストのうち、今回の変更に該当する項目

要件が曖昧でも、勝手に大規模な機能追加を行わないでください。

---

## 16. 実装後の横断影響調査（Ripple Check）

kiro（`/kiro-impl`）による実装直後、レビュー依頼およびコミットの前に、必ず横断影響調査を実施してください。
変更したファイルだけを見て完了としないでください。

### 16.1 実施タイミング

- 実装者: `## Status Report` を返す前
- 修正対応時: レビュー指摘を修正した直後（§17.3）
- 対象: 差分が1行でもある全タスク（ドキュメントのみの変更を除く）

### 16.2 探索対象

変更したシンボル・キー・識別子を起点に、リポジトリ全体を検索します。

検索の起点にする語:

- 変更した関数名、クラス名、dataclassフィールド名
- ノードID（`PDR_` 接頭辞）、入出力ソケット名
- `DETAILER_PLAN` のキー、`schema_version`
- scope名、`task_id` 書式
- presetキー、prompt/schemaファイル名

確認する範囲:

- `prompt_detailer_router/nodes/` のノード登録と入出力定義
- `__init__.py` の `NODE_CLASS_MAPPINGS` / `NODE_DISPLAY_NAME_MAPPINGS`
- `application/` と `domain/` の呼び出し元
- `infrastructure/` の I/O とシリアライズ処理
- `resources/schemas/` の JSON Schema
- `resources/presets/` の全preset
- `resources/prompts/` の固定文
- `web/js/` のscope解析・候補生成・widget更新
- `tests/` の unit / contract / integration / frontend / snapshot と fixture
- `docs/`、`README`、example workflow

### 16.3 修正方針

- 影響箇所が承認済みtaskの `_Boundary:_` 内にある場合は、同一タスク内で修正まで完了させる
- `_Boundary:_` 外に影響がある場合は、勝手に修正せず、影響一覧を報告してboundary拡張または後続task化の判断を仰ぐ
- 「動くから放置」を許容しない。テスト・Schema・preset・フロントエンドのいずれかが古い定義のまま残ることを不整合として扱う

### 16.4 報告書式

実装者およびレビュー修正者は、報告に次のブロックを含めてください。

```text
## Ripple Report
- SEARCH_KEYS: <検索した語のリスト>
- SEARCH_COMMANDS: <実行した検索コマンド>
- IMPACTED_IN_BOUNDARY: <boundary内で修正したファイル:行>
- IMPACTED_OUT_OF_BOUNDARY: <boundary外の影響箇所と対応方針>
- NO_IMPACT_CONFIRMED: <調査したが影響が無かった範囲>
```

`SEARCH_COMMANDS` が空の Ripple Report は無効とし、レビューはREJECTしてください。

---

## 17. レビュー運用規約

### 17.1 ラウンド上限

- 1タスクあたりのレビューラウンドは最大10ラウンドとする
- 1ラウンド = 「レビュー実施 → 指摘 → 修正 → 再レビュー」の1往復
- 初回レビューをラウンド1と数える
- 10ラウンドに到達しても `APPROVED` にならない場合は、実装・レビューを継続せず打ち切る
  - `tasks.md` に `_Blocked: レビュー10ラウンド未収束 — <未解決の要点>_` を追記
  - 未解決指摘を一覧化して人間のレビューへエスカレーションする
- `kiro-impl` のラウンド配分は本規約に従う
  - ラウンド1〜3の`REJECTED`: 実装者へ直接再依頼
  - ラウンド4〜9の`REJECTED`: debugサブエージェント経由で再実装（debug最大3ラウンド）
  - ラウンド10の`REJECTED`: 打ち切り、人間のレビューへエスカレーション
- debugラウンドもレビューラウンドとして計上する。debug3ラウンドとレビュー10ラウンドのいずれか早く到達した方でタスクをBLOCKする

### 17.2 レビュー側の規約

- 指摘は「代表例」ではなく該当箇所を全件列挙する。同種の指摘を1件にまとめる場合も、対象ファイルと行を漏れなく挙げる
- 同一観点の指摘は初回ラウンドで出し切る。後続ラウンドで同一観点の新規指摘を追加しない
- ラウンド5以降は、新規観点の指摘を原則行わず、修正によって新たに混入した欠陥のみを対象とする
- 指摘には根拠（requirements / design の節番号、または本ファイルの節番号）を必ず添える
- 好みの問題や仕様に根拠の無い指摘を `REJECTED` の理由にしない

### 17.3 修正側の規約

- 指摘された箇所のみを修正して再提出しない
- 各指摘について、同種の欠陥がリポジトリ全体に他に存在しないかを検索し、見つかった分も同一ラウンドで修正する
- §16 の Ripple Check を修正後に再実施する
- 再提出時の報告に次を含める

```text
## Remediation Report
- FINDING: <指摘ID / 要約>
- ROOT_CAUSE: <原因>
- FIXED_AT: <直接指摘された箇所>
- SAME_KIND_SEARCH: <同種欠陥を探した検索コマンド>
- SAME_KIND_FIXED: <横断探索で追加修正した箇所（無ければ NONE、根拠付き）>
```

- `SAME_KIND_SEARCH` が空、または「指摘箇所のみ修正」の再提出は、レビュー内容によらずREJECTしてよい

### 17.4 打ち切り時の扱い

- 打ち切ったタスクは未完了として扱い、`[x]` にしない
- 部分的に妥当な修正はコミットしてよいが、コミットメッセージに未収束である旨を残す
- 打ち切りの原因が仕様側にある場合は、コード側で回避せず requirements / design の差異として報告する（§21）

### 17.5 指摘対象の重大度基準

レビューラウンドは有限資源です。動作・契約・仕様適合に影響しない事項でラウンドを消費しないでください。
本節はCodexを含む全レビュー主体（bot・サブエージェント・人間）に適用します。

#### 指摘する（`Critical` / `Important`、`REJECTED` の理由にしてよい）

- 承認済み requirements / design / tasks の完了条件との差異
- 契約違反（JSON Schema、`DETAILER_PLAN` 不変条件、`encode`/`decode` 往復、ノード入出力、`schema_version`）
- 利用者へ生の例外が到達する経路、エラーの黙殺、フォールバック不備
- scope / subject の越境によるプロンプト汚染
- 実際に到達可能な入力での性能劣化・セキュリティ問題（パス解決、ReDoS、二乗時間）
- 完了条件を満たさないテスト（要求された fixture 種別の不足、実装を壊しても通るテスト）
- 対応 Python バージョン（3.10）で動作しないコード
- 横断影響調査の未実施（`SEARCH_COMMANDS` 空の Ripple Report）

#### 指摘しない（報告する場合も `Suggestion` / `FYI` に留め、`REJECTED` の理由にしない）

- 動作が変わらない命名・語順・コメント文言・docstring 表現の好み
- 出力が同一な等価リファクタ提案（早期 return 化、内包表記化、ヘルパ抽出、定数の切り出し）
- 型ヒントの等価な書き換え（lint が通る範囲の表記ゆれ）
- 上流の Schema 検証や呼び出し元の契約で既に排除済みの、到達不能な理論上の入力
- テストの命名・分割方法・パラメータ化スタイル
- 既存コードにも同様に存在し、当該変更が新たに悪化させていない事項
- formatter / linter が自動修正できる書式

#### 指摘の書式要件

- 指摘には「どの入力で」「どの出力または例外が」「どう誤るか」を必ず添える
- 再現条件を具体的に示せない指摘は出さない（「〜の可能性がある」だけの指摘は無効）
- 根拠として requirements / design の節番号または本ファイルの節番号を添える（§17.2）
- `Suggestion` / `FYI` は1ラウンド合計5件までとし、修正は任意とする
- 実装者は `Suggestion` / `FYI` を対応せずに再提出してよい。その旨を報告に1行残せば足りる

---

## 18. 禁止事項

- Analyzerのoutputを部位ごとに無制限に増やす
- LLM結果に応じてoutputソケット数を変更する
- UI側だけでPlanの整合性を保証する
- LLMに維持文や固定プリセットを毎回自由生成させる
- ComfyUIノードクラスに全処理を集約する
- Schema検証なしでJSONをdictとして使用する
- 不正データを黙って破棄する
- `task_id`を配列indexだけで管理する
- コード内に大量の固定プロンプトを直書きする
- テストを通すためだけに仕様を弱める
- 未承認の破壊的Schema変更を行う
- 指摘された箇所だけを修正し、同種の欠陥を残したまま再提出する
- 横断影響調査を行わずに実装完了を報告する
- 動作・契約・仕様適合に影響しない軽微な事項を `REJECTED` の理由にする（§17.5）
- 再現条件を示せない推測ベースの指摘でレビューラウンドを消費する（§17.5）

---

## 19. Git・PR方針

- 1つのPRは1つのspecまたは明確な垂直スライスを基本とする
- 生成物やローカルモデルをコミットしない
- Ollamaモデル名を固定した個人設定をコミットしない
- PR本文に次を含める
  - 対応した要件
  - 設計上の判断
  - 追加・変更したテスト
  - 既知の制約
  - ワークフロー互換性
- UI変更はスクリーンショットまたは短い動作説明を添える
- Schema変更は移行影響を記載する

---

## 20. 完了条件

実装完了を宣言する前に、次を確認してください。

- [ ] 対象requirementsを満たしている
- [ ] designから逸脱していない
- [ ] tasksの完了条件を満たしている
- [ ] Python unit testが通る
- [ ] contract testが通る
- [ ] JavaScript testが通る
- [ ] formatter / lintが通る
- [ ] 不正JSONの挙動を確認した
- [ ] missing taskの挙動を確認した
- [ ] example workflowへの影響を確認した
- [ ] READMEまたはdocsを更新した
- [ ] warningとdiagnosticsがユーザーに理解可能
- [ ] 秘密情報やローカルパスを含めていない
- [ ] 横断影響調査（§16）を実施し、Ripple Reportを残した
- [ ] レビュー指摘に対し、同種箇所の横断修正（§17.3）を行った
- [ ] §22 の頻出指摘チェックリストのうち、該当分類を全て確認した
- [ ] レビューラウンドが10以内で `APPROVED` に到達した

---

## 21. 変更提案時の書式

仕様外の改善を発見した場合は、実装へ混ぜず次の形式で報告してください。

```text
提案:
理由:
影響範囲:
互換性:
追加が必要なspec:
推奨優先度:
```

---

## 22. 頻出レビュー指摘と先回り実装チェックリスト

過去PR（#1 docs / #2 core / #4 fix）のレビュー指摘を分類した結果です。
実装時はこのチェックリストを先に潰してください。指摘されてから直すのではなく、最初から満たすことを前提とします。

### 22.1 実測傾向（実装PR #2・#4、計46件・全て P2 相当）

| 分類 | 件数 | 主な発生箇所 |
|---|---|---|
| A. 外部入力・設定リソースの検証境界 | 18 | `infrastructure/preset_loader.py`（13）、`policy_loader.py`、`prompt_template_loader.py` |
| B. 文字列後処理と計算量 | 10 | `domain/forbidden_terms.py` |
| C. ドメイン不変条件と往復契約 | 7 | `domain/detailer_plan.py`、`infrastructure/json_codec.py` |
| D. preset の scope / subject 越境 | 7 | `resources/presets/` 全体 |
| E. リソース外部化とバージョン | 3 | 固定文の直書き、バージョン定数の未実装 |
| F. テスト網羅・ランタイム互換 | 2 | fixture 種別不足、Python 3.10 互換 |

docs PR（#1、48件）は「分岐・出力・キャッシュキーの未定義」と「preset 契約の未分離」に集中しました。
設計文書では、各分岐の**全出力**と**キャッシュキーの全構成要素**を漏れなく定義してください。

### 22.2 A: 外部入力・設定リソースの読み込み境界（最頻出）

`resources/` 配下のファイルと、ノードの STRING 入力は「利用者が編集しうる外部入力」として扱います。

- JSON 構文エラー・文字コードエラー・非 object ルート・重複キーを `ConfigurationError` へ変換する
- 必須キーの存在だけでなく、**値の型**を dataclass 構築前に検証する（`str` / `int` / `list[str]` / `dict[str, str]`）
- 必須文字列は空文字だけでなく**空白のみ**も拒否する
- **未知フィールド**を拒否する
- リソース ID は安全な stem（`^[A-Za-z0-9_-]+$`）に限定し、解決後パスが対象 resource ディレクトリ配下であることを確認する
- ファイル内の id と要求 id を照合する
- mapping のキー・値は対応 scope 集合に限定する
- テンプレートは全 format field・format_spec・conversion を読み込み時に検証する
- 生の `JSONDecodeError` / `UnicodeDecodeError` / `TypeError` / `AttributeError` / `KeyError` / `ValueError` を利用者へ到達させない

新しい loader を追加する場合は、既存 loader と同じ検証を**共有ヘルパ経由**で適用してください。loader ごとに検証が欠けることが再指摘の主因でした。

### 22.3 B: 文字列後処理と計算量

- 除去・置換を実装したら、**除去跡の修復**（区切り記号、空括弧、連続区切り、先頭末尾）まで同一変更で設計する
- 単語境界に `\b` を使わない。画像生成プロンプトは `_` を区切りに使う（`perfect_face` を検出できること、`imperfect` を検出しないこと）
- 修復規則は**承認済み requirements / design に決定表として明記してから実装する**。仕様に無い修復挙動を実装で発明しない。仕様に無い挙動は「正しい答え」が定義されないため、レビューのたびに新しい解釈が生まれ収束しない（実測: `forbidden_terms.py` は未仕様の修復挙動で計8ラウンドを消費した）
- 修復の適用範囲（**文字列全体か、除去位置限定か**）を仕様で明示的に選ぶ。位置限定は入力空間が「境界 × 左右の区切り群 × 句読点種別 × 隣接文字種」の組合せに膨らむため、正当化できる製品価値がある場合にのみ選ぶこと。`prompt-detailer-core` は Req 9.7 で**全体一様**を選択済み（離れた位置の `...` も正規化されることを受容するトレードオフ）
- 反復回数上限に依存する fixpoint を書かない。入力長に依存せず1パスで完結させる
- ネストした量指定子（`[\s,;.]*` の入れ子等）はカタストロフィックバックトラッキングを招く。単一量指定子で書く
- 入力長に上限がない（Schema に `maxLength` が無い）箇所は、最悪ケース入力で実測してからコミットする

### 22.4 C: ドメイン不変条件と往復契約

- `validate_*` は Schema が保証する内容に依存せず自己完結させる
- `task_id == subject_id + "." + scope`、`(subject_id, scope)` の一意性、空/空白 `subject_id` の拒否を明示検証する
- `requested_scopes` は「対応済み」「小文字」「重複なし」を明示検証する
- `frozen=True` だけでは不変にならない。`__post_init__` で列を tuple 化し、mapping は `MappingProxyType` で包む
- `encode` と `decode` を対称にする（`encode` 側でも Tier1 Schema → Tier2 不変条件の順で検証する）
- 検証エラーメッセージにフィールドパス（`tasks/0/order` 形式）を含める

### 22.5 D: preset の scope / subject 越境

- detailer preset は当該 scope の対象部位のみに言及する（`face` に髪型、`upper_body` に背景、`generic` に周辺シーンを入れない）
- upscale preset は被写体非依存にする（`pose` / `identity` / `clothing` / `skin` を無条件に含めない）
- 品質語や写実性の強制を preset に固定で入れない（§10 の禁止事項）
- preset を1つ修正したら、**全 preset を横断監査**して同種の越境がないことを確認する（§17.3）

### 22.6 E / F: リソース・バージョン・テスト・ランタイム

- プロンプト固定文を Python に直書きしない。version 付きで `resources/` に置く
- design.md に登場するバージョン定数（例: Prompt Builder のバージョン）は実装に定義し、下流から import 可能にする
- 外部 I/F の Schema には `schema_version` を必須化し、異なる version を拒否する contract test を書く
- `tasks.md` の完了条件に列挙された fixture 種別は**全て**用意する。代表1件で済ませない
- Python 3.10 前提: `Traversable.joinpath` は単一引数のみ。3.11+ 限定 API を使わない

### 22.7 再指摘を招く典型パターン（禁止）

- 指摘された1ケースだけを直す。同じ関数の残りの境界が次ラウンドで指摘される
- 修復ロジックを継ぎ足しで拡張する。過剰修復や性能劣化という新規欠陥を生む

実測として `forbidden_terms.py` は10ラウンド、`preset_loader.py` は13件の指摘を要しました。
いずれも「1件ずつの追随修正」が原因です。修正時は**当該関数の入力空間を列挙し、一度に閉じてください**（§17.3 の `SAME_KIND_SEARCH` と同じ趣旨を、関数の入力空間に対しても適用する）。
