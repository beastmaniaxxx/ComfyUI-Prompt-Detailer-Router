# プロジェクト構造

## 組織化方針

テスト可能な ComfyUI カスタムノード構成として、レイヤード構造を採用します。ComfyUI ノードとフロントエンド UI コードは adapter として扱い、永続的な振る舞いは Python の domain/application ロジックと外部 resource ファイルに置きます。

現在のリポジトリは documentation-first の状態です。実装構造はプロジェクトの設計指針に従い、必要な spec の実装に合わせて段階的に導入します。

## ディレクトリパターン

### パッケージルート

**場所**: `prompt_detailer_router/`

**目的**: バックエンドのカスタムノード処理を格納する Python package。

package initialization、extension wiring、ComfyUI compatibility module を置く想定です。実質的な domain logic を package initialization や node registration code に置かないでください。

### ノード Adapter

**場所**: `prompt_detailer_router/nodes/`

**目的**: Analyzer、Plan Select、Inspector、From JSON などの ComfyUI 入出力 adapter。

ノードクラスは application service へ処理を委譲します。prompt generation、Plan validation、Ollama request handling、preset loading rule をノードクラスの責務にしないでください。

### Domain 層

**場所**: `prompt_detailer_router/domain/`

**目的**: `DETAILER_PLAN`、scope、diagnostics、project-specific errors のための純粋な model/rule code。

domain module は ComfyUI API、Ollama client、filesystem-dependent preset loader を import しません。

### Application 層

**場所**: `prompt_detailer_router/application/`

**目的**: prompt analysis、upscale prompt build、detailer plan build、task selection、override、plan validation などの use case。

application code は domain と infrastructure を調停し、判断を決定論的に保ちます。

### Infrastructure 層

**場所**: `prompt_detailer_router/infrastructure/`

**目的**: Ollama API call、JSON encode/decode、schema loading、preset loading、diagnostics timing。

外部サービスと file I/O の詳細はここに閉じ込め、domain model や node へ漏らさないでください。

### Resources

**場所**: `prompt_detailer_router/resources/`

**目的**: prompt template、JSON Schema、versioned preset。

prompts、schemas、upscale presets、detailer presets の subdirectory を使います。schema と preset の変更は contract test と snapshot test で確認します。

### フロントエンド拡張

**場所**: `web/js/`

**目的**: Selector の task 候補を動的に更新する ComfyUI frontend extension。

`extension.js` は登録処理に集中させます。scope parsing、graph source resolution、widget update helper は、Node.js でテスト可能な別 module に分離します。

### Tests

**場所**: `tests/`

**目的**: unit、integration、contract、frontend、fixture、snapshot test を、振る舞いとリスクに応じて整理する。

domain/application の振る舞いは ComfyUI なしでテストすることを優先します。JavaScript の parsing と graph traversal は frontend test で確認します。

## 命名規則

- **Python package/module**: lowercase snake_case。
- **Node ID**: `PDR_` prefix を使う。
- **Custom data type**: Plan output には `DETAILER_PLAN` を使う。
- **Task ID**: `subject_id.scope` から始める。例: `main.face`。
- **Scope**: `face`、`hair`、`hands`、`body`、`upper_body`、`clothing`、`generic` のような正規化済み lowercase string。
- **Resource file**: 出力に影響する schema や preset は versioning を含める。

## Import 構成

レイヤー方向を守る relative import または package import を使います。

```python
# Node adapter calls application
from prompt_detailer_router.application.select_detailer_task import select_detailer_task

# Application uses domain and infrastructure
from prompt_detailer_router.domain.detailer_plan import DetailerPlan
from prompt_detailer_router.infrastructure.preset_loader import PresetLoader
```

domain から application、infrastructure、nodes、frontend code への逆方向 import は避けます。

## コード構成原則

- ComfyUI 依存を隔離し、backend logic を ComfyUI process なしでテストできるようにする。
- LLM/Ollama 依存を隔離し、prompt building と validation を fixture からテストできるようにする。
- scope を追加する場合は、domain definition、schema、preset、test、docs、frontend candidate handling を同一変更で更新する。
- node input/output、schema version、`DETAILER_PLAN` structure を変更する場合は workflow compatibility を維持する。
- agent-specific tooling directory を product structure として文書化しない。
