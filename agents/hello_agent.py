"""Day 3 gate: prove Microsoft Foundry access with a hello agent.

Usage:
    python -m agents.hello_agent

Required environment variables (load from .env):
    FOUNDRY_PROJECT_ENDPOINT  – Azure AI Foundry project endpoint URL
    FOUNDRY_MODEL             – model deployment name (e.g. gpt-4o)
"""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        print(
            f"ERROR: environment variable {name!r} is not set.\n"
            "Copy .env.example to .env and fill in your Foundry project details.",
            file=sys.stderr,
        )
        sys.exit(1)
    return value


async def main() -> None:
    endpoint = _require_env("FOUNDRY_PROJECT_ENDPOINT")
    model = _require_env("FOUNDRY_MODEL")

    from agent_framework import Agent
    from agent_framework_foundry import FoundryChatClient
    from azure.identity import AzureCliCredential

    client = FoundryChatClient(
        project_endpoint=endpoint,
        model=model,
        credential=AzureCliCredential(),
    )

    analyst = Agent(
        client,
        name="WhatIfAnalyst",
        instructions="You are a football analyst. Answer in two sentences.",
    )

    response = await analyst.run(
        "In football, why can a pass to an unmarked winger be better than a short safe pass?"
    )
    print(response.text)


if __name__ == "__main__":
    asyncio.run(main())
