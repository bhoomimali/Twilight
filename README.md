# TWILIGHT + Twinity + LangChain agents

## What this is
- **Twilight gateway** (M1–M3): attestation, policy, trust, audit
- **Frontend**: Twinity Bank UI (`frontend/`)
- **LangChain-style agents** (`langchain_agents/`):
  - TalkerLC, PoisonerLC (red team, words only)
  - SupportBotLC, CoordinatorLC (tools go through Twilight)

Without `OPENAI_API_KEY`, agents use LangChain tools + offline planner.
With a key + `pip install langchain langchain-openai`, they use a real tool-calling LLM.

## Quick terminal demo (LangChain path)

```bash
cd twilight
python -m venv venv
# activate venv
pip install fastapi uvicorn pydantic pydantic-settings pyyaml pynacl httpx
# optional:
pip install langchain langchain-core langchain-openai

python scripts/run_langchain_attack.py --mode on
python scripts/run_langchain_attack.py --mode off
```

Expect: Talker + Poisoner speak → SupportBot tries `issue_refund(9000)` →
**ON = BLOCK**, **OFF = ALLOW**.

## Classic non-LC attack path

```bash
python scripts/run_attack.py --mode on --attacker both
```

## Gateway + UI

```bash
python scripts/reset_db.py
python -m uvicorn gateway.main:app --port 8000 --reload
cd frontend && python -m http.server 5500
```

## Layout

```
twilight/
  gateway/ engine/ agents/ attackers/
  langchain_agents/     ← NEW small LC agents
  scripts/run_langchain_attack.py
  scripts/run_attack.py
  frontend/
```
