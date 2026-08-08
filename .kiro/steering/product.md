# プロダクト概要

ComfyUI-Prompt-Detailer-Router は、元画像の生成プロンプトから Upscale と Detailer のワークフローに必要なルーティング情報を生成する ComfyUI カスタムノードプロジェクトです。

ローカルの Ollama LLM で元プロンプトから構造化された事実を抽出し、その後は決定論的な Python ロジックで最終プロンプトとタスク計画を構築します。LLM は抽出を担当し、Python が判断を担当します。

## 中核機能

- 元画像の生成プロンプトを解析し、明記された事実だけを抽出する。
- style、lighting、camera、material、texture、environment、および必要最小限の被写体維持情報から、Ultimate SD Upscale 向けの `upscale_prompt` を生成する。
- 部位や被写体ごとに出力ソケットを増やすのではなく、複数の Detailer 処理を単一の `DETAILER_PLAN` に格納する。
- `task_id` で Detailer タスクを選択し、Plan に対して検証したうえで `detailer_prompt` を返す。
- Analyzer の `scopes` から JavaScript で動的なタスク候補を提供しつつ、実行時の正当性はバックエンドで保証する。

## 想定ユースケース

主なワークフローでは、元プロンプトと `face,hair,hands` のようなカンマ区切り scope を入力し、次を生成します。

- Upscale 段階で使うプロンプト。
- `main.face` や `main.hair` などのタスクを含む構造化された Detailer Plan。
- デバッグや LLM Text Processor 互換のための JSON と Inspector 出力。
- Impact Pack Detailer などの Detailer ノードへ渡せる Selector 出力。

初期スコープでは、単一の主被写体、Ollama `/api/chat`、構造化 JSON 出力、Analyzer から Selector への接続、Reroute 対応、ローカル ComfyUI 実行を前提にします。

## 価値

このプロジェクトは、Upscale と Detailer の各段階で手作業によりプロンプトを転記する負担を減らし、元プロンプトとの整合性を保ちます。

中心的な価値は、制御された自動化です。LLM の揺らぎは事実抽出に限定し、同一性維持、scope 別の局所ディテール指示、検証、フォールバック、最終プロンプト構築は、決定論的でテスト可能な処理として扱います。

## プロダクト境界

- 元プロンプトにない視覚的事実、同一性変更、美化の既定表現、scope 外の詳細を追加しない。
- 実行時の正当性を UI 側の検証だけに依存しない。
- LLM 結果に応じた動的 output ソケットを作らない。
- Analyzer 本体に部位ごとの固定出力を増やさず、`DETAILER_PLAN` と Selector または補助 Unpack ノードで扱う。
- cloud LLM 対応、SEGS と人物の完全自動対応、SetNode/GetNode 探索、サブグラフ探索、Detailer 自動実行は、専用 spec なしに追加しない。
