"""Tiny in-memory bank ledger for the demo.
Money only moves when a tool really executes: Guard OFF drains it, Guard ON leaves it alone."""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_lock = threading.Lock()
_state: dict = {}


def _read(name: str):
    return json.loads((ROOT / "frontend" / "data" / name).read_text(encoding="utf-8"))


def reset() -> None:
    with _lock:
        bank = _read("bank.json")
        customers = _read("customers.json")
        _state.clear()
        _state.update(
            start=float(bank["ledger_balance"]),
            ledger=float(bank["ledger_balance"]),
            customers={c["id"]: float(c["balance"]) for c in customers},
            txns={},  # customer_id -> extra transactions, newest first
        )


def refund(customer_id: str, amount: float, ticket_id: str = "") -> dict:
    with _lock:
        amount = float(amount)
        _state["ledger"] -= amount
        if customer_id in _state["customers"]:
            _state["customers"][customer_id] -= amount
        rows = _state["txns"].setdefault(customer_id, [])
        rows.insert(0, {
            "id": f"TX-X{len(rows) + 1}",
            "ts": datetime.now().strftime("%H:%M:%S"),
            "type": "debit",
            "label": "IMPS to ACCT-4471 (unknown beneficiary)",
            "amount": amount,
            "status": "completed",
            "suspicious": True,
        })
        return {"customer_id": customer_id, "amount": amount, "ledger": _state["ledger"]}


def snapshot() -> dict:
    with _lock:
        return {
            "ledger_start": _state["start"],
            "ledger_balance": _state["ledger"],
            "customers": dict(_state["customers"]),
            "transactions": {k: list(v) for k, v in _state["txns"].items()},
        }


reset()
