# LangChain agents + Twilight (Groq / OpenAI)

## Install

```powershell
pip install langchain langchain-core langchain-openai openai httpx
```

## Groq setup (recommended)

1. Create a key: https://console.groq.com/keys  
2. **Same terminal** as you run Python:

```powershell
$env:GROQ_API_KEY = "gsk_xxxxxxxx"
# optional:
$env:GROQ_MODEL = "llama-3.3-70b-versatile"
# or faster/cheaper:
# $env:GROQ_MODEL = "llama-3.1-8b-instant"
```

3. Test connection **before** the full attack:

```powershell
cd twilight
.\venv\Scripts\Activate.ps1
python scripts/test_groq.py
```

You should see `[groq] OK`.

## Run LangChain attack

```powershell
# Terminal 1 — gateway
uvicorn gateway.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2 — same env with GROQ_API_KEY
python scripts/run_langchain_attack.py --mode on
python scripts/run_langchain_attack.py --mode on --live
```

## Common errors

| Error | Fix |
|--------|-----|
| `GROQ_API_KEY not set` | Set `$env:GROQ_API_KEY` in **this** PowerShell window |
| `401 Unauthorized` | New key from console.groq.com — old/revoked key |
| `model not found` | `$env:GROQ_MODEL = "llama-3.1-8b-instant"` |
| `Connect timeout / SSL` | VPN/firewall blocking `api.groq.com` |
| `No module named openai` | `pip install openai langchain-openai` |

Without a key, agents still run via **offline planner**; tools still go through Twilight.
