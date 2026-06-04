"""FastMCP server instance for quality enforcement."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import Context, FastMCP

from .config import ServerConfig
from .logging import get_logger
from .models import AppContext

logger = get_logger(__name__)

_server_config: ServerConfig | None = None


@asynccontextmanager
async def _app_lifespan(server: FastMCP) -> AsyncIterator[dict[str, AppContext]]:
    """Manage app lifecycle resources for tool execution."""
    del server
    cfg = _server_config if _server_config is not None else ServerConfig()

    logger.info(
        "Initializing quality enforcer",
        repos_config=str(cfg.repos_config),
        projects_root=str(cfg.projects_root),
    )

    if not cfg.repos_config.exists():
        logger.warning(
            "Repos config file not found, tools will use default discovery",
            path=str(cfg.repos_config),
        )

    yield {
        "app": AppContext(
            repos_config=cfg.repos_config,
            projects_root=cfg.projects_root,
            use_github=cfg.use_github,
            github_token=cfg.github_token,
        )
    }

    logger.info("Shutting down quality enforcer")


def get_app_context(ctx: Context) -> AppContext:
    """Return typed application context from lifespan context."""
    return ctx.lifespan_context["app"]


mcp = FastMCP(
    "Quality Enforcer",
    instructions=(
        "Scan, synchronize, and validate code quality infrastructure "
        "across multiple repositories."
    ),
    lifespan=_app_lifespan,
)
