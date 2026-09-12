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
CI (.github/workflows/pr-budget.yml) が次を検証します。空欄のままでは失敗します。

- 必須フィールド（BASE / REVIEW_LINES / REVIEW_FILES / TEST_LINES / OBSERVATIONS / VERDICT）が非空
- OBSERVATIONS から `(推定 — ...)` の注記が削除されている
  ツールの出力は推定値です。§22.1 の実分類を確認し、注記を消してください。
  書式はカンマ区切りで、各項目を分類記号 A〜E で始めます。該当なしは `-`。
  例: `OBSERVATIONS: A 外部入力検証, C ドメイン不変条件`
  F テストは数えません（AGENTS.md §19.2）。
- VERDICT が、実測（行数・ファイル数）と申告分類から導かれる判定と一致している
  3分類以上を申告した場合、VERDICT は OVER_BUDGET になります。
- VERDICT: OVER_BUDGET なら OVER_BUDGET_REASON が埋まっている（§19.3 該当なら分割不要）
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
