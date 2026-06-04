"""Pydantic models for quality enforcer."""

from pathlib import Path

from pydantic import BaseModel, Field


class AppContext(BaseModel):
    """Lifespan context shared across MCP tools."""

    repos_config: Path
    projects_root: Path
    use_github: bool = False
    github_token: str | None = None


class RepoInfo(BaseModel):
    """Repository metadata from repos.yaml."""

    name: str
    path: Path | None = None
    github_ref: str | None = None
    type: str = Field(
        default="python", description="Project type (python, mcp, fastapi, lib)"
    )
    has_pre_commit: bool = False
    has_coderabbit: bool = False
    has_makefile: bool = False
    type_checker: str | None = None
    has_radon_gate: bool = False


class QualityDriftReport(BaseModel):
    """Report of quality infrastructure drift across repos."""

    total_repos: int
    repos_with_pre_commit: int
    repos_with_coderabbit: int
    repos_with_makefile: int
    type_checker_breakdown: dict[str, int] = Field(default_factory=dict)
    repos_missing_pre_commit: list[str] = Field(default_factory=list)
    repos_missing_coderabbit: list[str] = Field(default_factory=list)
    repos_missing_radon_gate: list[str] = Field(default_factory=list)
