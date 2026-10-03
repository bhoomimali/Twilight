# Run LangChain agents (Groq)

## 1. Setup (once)

```powershell
cd twilight
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/reset_db.py
```

## 2. Start gateway (Terminal 1)

```powershell
.\venv\Scripts\Activate.ps1
uvicorn gateway.main:app --host 127.0.0.1 --port 8000 --reload
```

## 3. Groq key + test (Terminal 2 — same folder)

```powershell
.\venv\Scripts\Activate.ps1
$env:GROQ_API_KEY = "gsk_YOUR_KEY_HERE"
$env:GROQ_MODEL = "llama-3.3-70b-versatile"

python scripts/test_groq.py
```

Expect: `[groq] OK`

## 4. Run LangChain attack

```powershell
# Offline Twilight mode simulation inside agents
python scripts/run_langchain_attack.py --mode on

# Hit live gateway on :8000
python scripts/run_langchain_attack.py --mode on --live

# Guard off contrast
python scripts/run_langchain_attack.py --mode off --live
```

## If Groq fails

| Error | Fix |
|-------|-----|
| key not set | Set `$env:GROQ_API_KEY` in **this** terminal |
| 401 | New key from https://console.groq.com/keys |
| model 404 | `$env:GROQ_MODEL = "llama-3.1-8b-instant"` |
| no module openai | `pip install openai langchain-openai` |

Without a key, offline planner still runs tools through Twilight.
