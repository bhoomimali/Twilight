#!/usr/bin/env python3
"""Quick Groq connectivity test for Twilight LangChain agents."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from langchain_agents.llms import test_groq_connection, get_llm

if __name__ == "__main__":
    print("\n=== Twilight · Groq connection test ===\n")
    ok = test_groq_connection()
    if ok:
        llm = get_llm(temperature=0)
        if llm is not None:
            print("\n[langchain] get_llm() returned Chat model — trying one invoke...")
            try:
                from langchain_core.messages import HumanMessage
                r = llm.invoke([HumanMessage(content="Say hi in 3 words.")])
                print("[langchain] OK:", getattr(r, "content", r))
            except Exception as e:
                print("[langchain] invoke failed:", e)
                ok = False
    print("\nResult:", "SUCCESS" if ok else "FAILED")
    sys.exit(0 if ok else 1)
