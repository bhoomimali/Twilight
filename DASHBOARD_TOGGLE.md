# Guard ON/OFF from the dashboard

## Run it (one server, one URL)
```
python scripts/reset_db.py
python -m uvicorn gateway.main:app --port 8000
```
Open **http://127.0.0.1:8000/ui/**  (keep that terminal visible, the agent conversation prints there)

## Demo flow
1. Click **TWILIGHT · OFF**, then **Run attack**. The terminal shows the poisoned ticket and `ALLOW (no checks)`. Total balance drops by ₹9,000 and a new "unknown beneficiary" debit shows in Customers. The Twilight tab is blind (trust and audit show "—", nothing logged).
2. Click **TWILIGHT · ON** (this resets the bank, trust scores and audit log), then **Run attack**. The terminal shows `BLOCK constraints.issue_refund.max_amount`. Balance stays put. The dashboard jumps to the Twilight tab with the BLOCK log and SupportBot trust 100 → 75.
3. **Reset** gives a fresh bank without changing the mode.

`Run attack` uses `scripts/run_attack.py`. For the LangChain agents, POST `/demo/run-attack?flavor=langchain`.
Scripts now default to `--mode auto` (they follow the dashboard toggle). `--mode on|off` still works.

If the gateway is not running, the dashboard falls back to the old local simulation and says "Gateway offline".

## New files
- `gateway/demo_api.py`  /demo/state, /demo/mode, /demo/reset, /demo/run-attack
- `gateway/ledger.py`    in-memory bank ledger (money only moves when a tool really executes)
- `gateway/signing.py`   signs demo events with the agent's real key

## Bugs fixed on the way (these made the live gateway path block everything)
- `gateway/pipeline.py`: misplaced `else` after the config-hash check returned a QUARANTINE-style BLOCK with an empty reason even when the hash matched.
- `gateway/pipeline.py`: a local `from gateway.tools import execute_tool` shadowed the module import, so every ALLOWed action in ON mode crashed into "internal_error".
- `gateway/db.py`: `update_agent_trust` called a method that doesn't exist (`_connect`), so trust drops never saved.
- `gateway/pipeline.py`: event insert called `.value` on plain strings.
- `gateway/websocket.py`: added the missing `publish_sync` the pipeline calls.
- `gateway/main.py`: CORS allowed only :5173, so the dashboard on another port was blocked. Now open, and the gateway also serves `/ui/`.
- `langchain_agents/gateway_tools.py`: events were sent as "langchain-unsigned" (always blocked on signature) and without the API key. Now signed.
- `langchain_agents/agents.py`: offline planner emitted `a:b:c` but the runner split on `|`.

All 137 existing tests still pass.

## Known leftovers (not touched)
- `gateway/background.py` trust-recovery loop calls `recover_clean_agent` with the wrong arguments and prints an error line about once a minute.
- `GET /audit/verify` is still the placeholder that always returns valid.
