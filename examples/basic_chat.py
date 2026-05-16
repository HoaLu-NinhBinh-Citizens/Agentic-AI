"""Basic chat example with AI_support."""

import asyncio
from ai_support.core.agent.core import AgentCore


async def main():
    agent = AgentCore()
    
    response = await agent.process("Hello, how can you help me?")
    print(response)


if __name__ == "__main__":
    asyncio.run(main())
