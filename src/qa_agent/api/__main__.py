"""Entry point: ``qa-agent-api`` / ``python -m qa_agent.api``."""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    uvicorn.run(
        "qa_agent.api.main:create_app",
        factory=True,
        host=os.environ.get("QA_AGENT_API_HOST", "0.0.0.0"),
        port=int(os.environ.get("QA_AGENT_API_PORT", "8000")),
        reload=bool(os.environ.get("QA_AGENT_API_RELOAD")),
    )


if __name__ == "__main__":
    main()
