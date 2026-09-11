"""Runs docs/BENCHMARK.md's golden dataset against a live local API server and
prints a markdown table of the empirical results — actual payload size, a rough
token estimate, and recall/precision against the hand-verified expected sets in
tests/benchmark/golden_dataset.json.

Token estimate is `len(json_bytes) / 4` — the standard rough English-text
heuristic (~4 bytes/token), not an exact count from a real tokenizer. Good
enough to compare relative sizes across tasks, not meant as a billing figure.

Usage: start the API server (scripts/run_api.py), then:
    python scripts/run_benchmark.py
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DATASET_PATH = Path(__file__).resolve().parents[1] / "tests" / "benchmark" / "golden_dataset.json"
API_BASE = "http://127.0.0.1:8000/api"


def _fetch(path: str) -> tuple[list[dict[str, Any]], int]:
    with urllib.request.urlopen(f"{API_BASE}{path}") as response:
        raw = response.read()
    return json.loads(raw), len(raw)


def _key(item: dict[str, Any]) -> tuple[str, str]:
    return (item["source_system"], item["native_id"])


def run() -> None:
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    business_node_id = dataset["business_node_id"]

    # Both numbers matter: `limit=20` is search-cards' real default — what an
    # agent gets unless it explicitly asks for more — and `limit=100` (the
    # route's own hard cap) is the worst case if it does ask, or if a task's
    # true match count exceeds 20 regardless.
    print("| Task | Limit | Results | Payload bytes | Est. tokens | Recall | Precision |")
    print("|---|---|---|---|---|---|---|")

    for task in dataset["tasks"]:
        for limit in (20, 100):
            q = urllib.parse.quote(task["query"])
            path = f"/catalog/search-cards?q={q}&business_node_id={business_node_id}&limit={limit}"
            cards, payload_bytes = _fetch(path)
            est_tokens = payload_bytes // 4

            actual_keys = {_key(c["node"]) for c in cards}
            expected = task.get("expected")

            if expected is None:
                recall_str = "n/a (documented, not scored)"
                precision_str = "n/a"
            else:
                expected_keys = {(e["source_system"], e["native_id"]) for e in expected}
                hit = expected_keys & actual_keys
                recall = len(hit) / len(expected_keys) if expected_keys else 0.0
                precision = len(hit) / len(actual_keys) if actual_keys else 0.0
                recall_str = f"{recall:.0%} ({len(hit)}/{len(expected_keys)})"
                precision_str = f"{precision:.0%} ({len(hit)}/{len(actual_keys)})"

            print(
                f"| `{task['query']}` | {limit} | {len(cards)} | {payload_bytes:,} "
                f"| {est_tokens:,} | {recall_str} | {precision_str} |"
            )


if __name__ == "__main__":
    run()
