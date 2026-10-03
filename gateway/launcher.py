"""
gateway/launcher.py — Owner: M3
Starts agent processes, independently hashes configs, supervises, kills on drift.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def hash_config(config_path: Path) -> str:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def load_trusted_hash(agent_id: str) -> Optional[str]:
    manifest_path = ROOT / "manifests" / f"{agent_id}.manifest.json"
    if manifest_path.exists():
        try:
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
            return m.get("config_hash") or m.get("hash")
        except Exception:
            return None
    cfg = ROOT / "manifests" / "trusted_configs" / f"{agent_id}.json"
    if cfg.exists():
        return hash_config(cfg)
    return None


class AgentProcess:
    def __init__(self, agent_id: str, module: str, config_path: Path):
        self.agent_id = agent_id
        self.module = module
        self.config_path = config_path
        self.proc: Optional[subprocess.Popen] = None
        self.config_hash = hash_config(config_path) if config_path.exists() else ""

    def start(self) -> None:
        env = os.environ.copy()
        env["TWILIGHT_AGENT_ID"] = self.agent_id
        env["TWILIGHT_CONFIG"] = str(self.config_path)
        self.proc = subprocess.Popen(
            [sys.executable, "-m", self.module],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def verify_config(self) -> bool:
        if not self.config_path.exists():
            return False
        current = hash_config(self.config_path)
        if current != self.config_hash:
            return False
        trusted = load_trusted_hash(self.agent_id)
        if trusted and trusted != current:
            return False
        return True


class Launcher:
    def __init__(self):
        self.agents: Dict[str, AgentProcess] = {}

    def register(self, agent_id: str, module: str, config_path: str | Path) -> AgentProcess:
        ap = AgentProcess(agent_id, module, Path(config_path))
        self.agents[agent_id] = ap
        return ap

    def start_all(self) -> None:
        for ap in self.agents.values():
            ap.start()

    def stop_all(self) -> None:
        for ap in self.agents.values():
            ap.stop()

    def supervise_once(self) -> List[str]:
        killed: List[str] = []
        for agent_id, ap in list(self.agents.items()):
            if not ap.is_alive():
                continue
            if not ap.verify_config():
                ap.stop()
                killed.append(agent_id)
        return killed


def main():
    launcher = Launcher()
    configs = ROOT / "agents" / "configs"
    mapping = {
        "supportbot": "agents.supportbot",
        "databot": "agents.databot",
        "coordinator": "agents.coordinator",
        "emailer": "agents.emailer",
        "payments": "agents.payments",
        "researcher": "agents.researcher",
    }
    for agent_id, module in mapping.items():
        cfg = configs / f"{agent_id}.json"
        if cfg.exists():
            launcher.register(agent_id, module, cfg)
    print(f"Registered {len(launcher.agents)} agents")
    if not launcher.agents:
        print("No agent configs under agents/configs — idle.")
        return
    launcher.start_all()
    try:
        while True:
            killed = launcher.supervise_once()
            if killed:
                print(f"[launcher] killed drifted agents: {killed}")
            time.sleep(5)
    except KeyboardInterrupt:
        launcher.stop_all()
        print("Stopped.")


if __name__ == "__main__":
    main()
