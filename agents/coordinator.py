"""
Coordinator — NovaBank inter-agent messaging (PRD D-1).
Tools: send_message.
"""
from agents.base_agent import BaseAgent


class CoordinatorAgent(BaseAgent):
    def __init__(self):
        super().__init__("coordinator")

    async def send_message(self, to: str, text: str):
        return await self.call_tool("send_message", {"to": to, "text": text})
