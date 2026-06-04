"""Server configuration via QUALITY_MCP_* environment variables and CLI arguments."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerConfig(BaseSettings):
    """MCP server settings from CLI arguments and QUALITY_MCP_* environment variables.

    Precedence (highest to lowest): CLI args > env vars > defaults.
    """

    model_config = SettingsConfigDict(
        env_prefix="QUALITY_MCP_",
        cli_prog_name="quality-enforcer-mcp",
        cli_hide_none_type=True,
    )

    transport: Literal["stdio", "sse", "streamable-http"] = Field(
        default="stdio",
        description="Transport protocol",
    )
    host: str = Field(
        default="0.0.0.0",  # noqa: S104
        description="Host to bind to for HTTP transports",
    )
    port: int = Field(
        default=8000,
        description="Port to bind to for HTTP transports",
    )
    log_level: str = Field(
        default="INFO",
        description="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    repos_config: Path = Field(
        default=Path(__file__).parent.parent.parent / "config" / "repos.yaml",
        description="Path to repos registry YAML file",
    )
    projects_root: Path = Field(
        default=Path.home() / "Desktop" / "Projects",
        description="Root directory containing all projects",
    )
    use_github: bool = Field(
        default=False,
        description="Scan repos via GitHub API instead of local filesystem",
    )
    github_token: str | None = Field(
        default=None,
        description=(
            "GitHub personal access token (strongly recommended; 60 req/hr without it)"
        ),
    )
