"""M3: sandbox offline replay."""
from pathlib import Path
from engine.sandbox import run_sandbox, write_report


def test_sample_dataset_metrics(tmp_path):
    sample = Path("datasets/sample.jsonl")
    if not sample.exists():
        sample = tmp_path / "sample.jsonl"
        sample.write_text(
            '{"tool":"issue_refund","args":{"amount":50},"label":"benign"}\n'
            '{"tool":"issue_refund","args":{"amount":99999},"label":"attack"}\n',
            encoding="utf-8",
        )

    def checker(event):
        amount = (event.get("args") or {}).get("amount") or 0
        if amount and float(amount) > 1000:
            return {"verdict": "BLOCK", "reason": "amount"}
        return {"verdict": "ALLOW", "reason": "ok"}

    r = run_sandbox(sample, checker)
    assert r.total >= 2
    assert r.caught >= 1
    write_report(r, tmp_path / "report.json")
    assert (tmp_path / "report.json").exists()
