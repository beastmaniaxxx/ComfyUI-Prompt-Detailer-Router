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
- 必要に応じて`diagnostics: STRING`

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
- `preset: COMBOまたはSTRING`
- `seed: INT`
- `temperature: FLOAT`
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

要件が曖昧でも、勝手に大規模な機能追加を行わないでください。

---

## 16. 禁止事項

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

---

## 17. Git・PR方針

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

## 18. 完了条件

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

---

## 19. 変更提案時の書式

仕様外の改善を発見した場合は、実装へ混ぜず次の形式で報告してください。

```text
提案:
理由:
影響範囲:
互換性:
追加が必要なspec:
推奨優先度:
```
