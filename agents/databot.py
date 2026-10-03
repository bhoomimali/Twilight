"""
DataBot — NovaBank customer data lookup agent (PRD D-1).
Tools: read_customer_record, read_ticket.
"""
from agents.base_agent import BaseAgent


class DataBotAgent(BaseAgent):
    def __init__(self):
        super().__init__("databot")

    async def read_customer_record(self, customer_id: str):
        return await self.call_tool("read_customer_record", {"customer_id": customer_id})

    async def read_ticket(self, ticket_id: str = "T-1"):
        return await self.call_tool("read_ticket", {"ticket_id": ticket_id})
