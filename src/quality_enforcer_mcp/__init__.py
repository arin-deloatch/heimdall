"""Quality Enforcer MCP Server - Cross-repo quality infrastructure management."""

from pydantic_settings import CliApp

from quality_enforcer_mcp import server as _server
from quality_enforcer_mcp import (
    tools as _tools,  # noqa: F401 - triggers @mcp.tool registration
)
from quality_enforcer_mcp.config import ServerConfig
from quality_enforcer_mcp.logging import configure_logging
from quality_enforcer_mcp.server import mcp

__all__ = ["mcp", "main"]


def main() -> None:
    """Run the MCP server with configurable transport.

    Settings are loaded from CLI arguments and QUALITY_MCP_* environment variables.
    CLI arguments take precedence over environment variables.
    Run ``quality-enforcer-mcp --help`` for available options.
    """
    config = CliApp.run(ServerConfig)
    _server._server_config = config
    configure_logging(config.log_level)

    logger = __import__("structlog").get_logger(__name__)
    logger.info("Starting Quality Enforcer MCP", transport=config.transport)

    if config.transport in ("sse", "streamable-http"):
        mcp.run(transport=config.transport, host=config.host, port=config.port)
    else:
        mcp.run(transport="stdio")
