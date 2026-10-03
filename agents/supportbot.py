"""
SupportBot — NovaBank customer support agent (PRD D-1).
Tools: read_ticket, issue_refund. Max refund 500.
"""
from agents.base_agent import BaseAgent


class SupportBotAgent(BaseAgent):
    def __init__(self):
        super().__init__("supportbot")

    async def read_ticket(self, ticket_id: str = "T-1"):
        return await self.call_tool("read_ticket", {"ticket_id": ticket_id})

    async def issue_refund(self, customer: str, amount: float, ticket_id: str = None):
        args = {"customer": customer, "amount": amount}
        if ticket_id:
            args["ticket_id"] = ticket_id
        return await self.call_tool("issue_refund", args)
