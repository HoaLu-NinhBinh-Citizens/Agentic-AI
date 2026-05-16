"""Example: Hardware analysis using AI_support."""

import asyncio
from ai_support.core.agent.core import AgentCore


async def main():
    agent = AgentCore()
    
    task = "Analyze STM32F407 UART peripheral registers"
    response = await agent.process(task)
    print(response)


if __name__ == "__main__":
    asyncio.run(main())
