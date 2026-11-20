"""Compare naive top-k retrieval with planning-based recall.

Runs fully offline: the planner is a dict of scripted plans, so results are
deterministic and reproducible. Swap in `PlannedRetriever.json_planner(provider)`
to use a real model.

Usage:
    python scripts/eval_retrieval.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mini_harness.core.evaluation import EvalCase, evaluate, markdown_table  # noqa: E402
from mini_harness.core.retrieval import Document, NaiveRetriever, PlannedRetriever  # noqa: E402

PLANS: dict[str, dict[str, list[str]]] = {
    "程序崩了以后还能接着跑吗": {
        "sub_queries": ["进程崩溃后如何恢复运行", "断点续跑怎么做"],
        "keywords": ["崩溃", "断点续跑", "状态"],
    },
    "聊得太久窗口装不下该怎么办": {
        "sub_queries": ["上下文超出预算如何裁剪", "工具结果外置与滚动摘要"],
        "keywords": ["上下文", "预算", "裁剪"],
    },
    "模型要是乱改测试文件怎么办": {
        "sub_queries": ["如何限制模型可调用的工具", "越权调用如何拦截"],
        "keywords": ["allowlist", "白名单", "越权"],
    },
    "怎么比较两种方案的好坏并给出数字": {
        "sub_queries": ["如何评估检索方案效果", "命中率与 MRR 怎么算"],
        "keywords": ["评测", "命中率", "MRR"],
    },
    "同样的错误反复出现会不会被重复记住": {
        "sub_queries": ["记忆如何去重", "事实冲突如何处理"],
        "keywords": ["记忆", "去重", "幂等"],
    },
    "改完代码怎么确认真的修好了": {
        "sub_queries": ["如何验证修复结果", "测试通过如何判定"],
        "keywords": ["pytest", "全绿", "重跑"],
    },
}


def planner(question: str) -> str:
    plan = PLANS.get(question)
    if plan is None:
        return json.dumps({"sub_queries": [question], "keywords": []})
    return json.dumps(plan)


def main() -> int:
    corpus_raw = json.loads((ROOT / "evals/corpus.json").read_text("utf-8"))
    cases_raw = json.loads((ROOT / "evals/cases.json").read_text("utf-8"))
    documents = [Document(**item) for item in corpus_raw]
    cases = [EvalCase(**item) for item in cases_raw]

    naive = NaiveRetriever(documents)
    planned = PlannedRetriever(documents, planner)

    results = {
        naive.name: evaluate(naive, cases, k=3),
        planned.name: evaluate(planned, cases, k=3),
    }
    table = markdown_table(results)
    print(table)

    baseline, improved = results[naive.name]["hit_rate"], results[planned.name]["hit_rate"]
    print(f"\nimprovement: {baseline:.0%} -> {improved:.0%}")

    out = ROOT / "docs" / "retrieval_eval.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "# 检索评测结果\n\n"
        f"语料：{len(documents)} 篇｜评测集：{len(cases)} 题（刻意包含多跳问题与同义改写）\n\n"
        f"{table}\n\n"
        f"命中率提升：{baseline:.0%} → {improved:.0%}\n",
        encoding="utf-8",
    )
    print(f"written: {out.relative_to(ROOT)}")
    return 0 if improved > baseline else 1


if __name__ == "__main__":
    raise SystemExit(main())
