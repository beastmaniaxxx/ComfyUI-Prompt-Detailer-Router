<!--
AGENTS.md §19 に従って記入してください。
PR Budget ブロックは次のコマンドの出力をそのまま貼り付けます。

    python tools/pr_budget.py --format markdown
-->

## 対応した要件

<!-- requirements.md の要件ID -->

## 設計上の判断

<!-- design.md からの導出。逸脱がある場合は理由 -->

## 追加・変更したテスト

<!-- unit / contract / integration / frontend / snapshot -->

## 既知の制約

## ワークフロー互換性

<!-- 既存 example workflow への影響。Schema 変更がある場合は移行影響 -->

## PR Budget (AGENTS.md §19.2 / §19.4)

<!--
`python tools/pr_budget.py --format markdown` の出力で、ここから下を置き換えてください。
OBSERVATIONS は推定値なので、実際の分類を確認して修正すること。
VERDICT: OVER_BUDGET の場合は OVER_BUDGET_REASON を必ず埋めること（§19.3 該当なら分割不要）。
-->

```text
BASE:
REVIEW_LINES:   /1500
REVIEW_FILES:   /30
TEST_LINES:
SPEC_LINES:
META_LINES:
OBSERVATIONS:
VERDICT:
OVER_BUDGET_REASON:
```

## チェックリスト（AGENTS.md §20 抜粋）

- [ ] 横断影響調査（§16）を実施し、Ripple Report を残した
- [ ] レビュー指摘に対し、同種箇所の横断修正（§17.3.2）を行った
- [ ] `python tools/pr_budget.py` を実行し、上記 PR Budget を申告した（§19.4）
- [ ] `VERDICT: OVER_BUDGET` の場合、分割したか `OVER_BUDGET_REASON` を記載した
- [ ] 仕様文書と実装を同一PRに混在させていない（§19.1）
- [ ] 秘密情報やローカルパスを含めていない
