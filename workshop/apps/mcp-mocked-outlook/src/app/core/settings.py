"""
The whole configuration of the process, gathered into one object.

Each concern keeps its own model and its own environment prefix, and Settings assembles
them. The environment is read while this is built and not again, so one object holds
every value in use.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_app_version() -> str:
    """
    Package version from installed distribution metadata.
    """
    try:
        return version("mocked-outlook-mcp-demo")
    except PackageNotFoundError:
        return "0.0.0+local"


class AppSettings(BaseSettings):
    """
    OpenAPI metadata, uvicorn binding, CORS, and the API prefix.

    List fields accept JSON arrays when overridden.
    """

    model_config = SettingsConfigDict(
        env_prefix="OUTLOOK_CORE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    app_title: str = "Mocked Outlook MCP Server"
    app_description: str = (
        "Simulated Outlook email and calendar exposed via MCP for Databricks demos."
    )
    app_version: str = Field(default_factory=_default_app_version)

    host: str = Field(
        default="0.0.0.0",
        validation_alias=AliasChoices("OUTLOOK_CORE_HOST", "UVICORN_HOST"),
    )
    port: int = Field(
        default=8000,
        validation_alias=AliasChoices("OUTLOOK_CORE_PORT", "UVICORN_PORT", "PORT"),
    )

    api_prefix: str = Field(
        default="/api",
        description="Prefix for REST routes; the probes and the UI stay at the root.",
    )

    log_level: str = Field(
        default="INFO",
        description="Root logger level name (for example INFO, DEBUG, WARNING).",
    )

    max_worker_threads: int = Field(
        default=128,
        gt=0,
        description=(
            "How many calls may be waiting on the volume at once. Nothing here holds "
            "the event loop, so this is the real limit on how many people are served "
            "in parallel; anyio's default of 40 is a room-sized ceiling, and one agent "
            "makes several tool calls per question. The threads are idle on a socket "
            "rather than busy, so the cost of raising it is memory for the stacks."
        ),
    )

    # Browser-based MCP clients (the Genie, Agent Bricks and Playground pickers) send a
    # CORS preflight before posting to /mcp. Without a permissive policy the OPTIONS
    # returns 405, the browser blocks the request, and the server looks unreachable even
    # though curl works. The app already sits behind the Apps OAuth proxy.
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_headers: list[str] = Field(default_factory=lambda: ["*"])
    cors_expose_headers: list[str] = Field(
        default_factory=lambda: ["mcp-session-id", "mcp-protocol-version"],
    )


class MailboxSettings(BaseSettings):
    """
    Where mailboxes are stored and who owns one when the caller is anonymous.
    """

    model_config = SettingsConfigDict(
        env_prefix="OUTLOOK_MAILBOX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    volume_path: str = Field(
        # VOLUME_PATH is the name the Apps runtime injects for the volume resource, so
        # it is accepted as-is rather than asking whoever deploys this to rename it.
        default="/Volumes/vencam_sandbox/agent_bricks_ws_saldo_files/outlook_demo",
        validation_alias=AliasChoices("OUTLOOK_MAILBOX_VOLUME_PATH", "VOLUME_PATH"),
        description="Unity Catalog volume the per-user mailbox files live under.",
    )
    default_user: str = Field(
        default="demo-user@company.com",
        description=(
            "Mailbox used when no forwarded identity header is present, which is the "
            "case when the app is run locally."
        ),
    )


class Settings(BaseSettings):
    """
    Every setting the process needs, loaded from the environment and a .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    core: AppSettings = Field(default_factory=AppSettings)
    mailbox: MailboxSettings = Field(default_factory=MailboxSettings)
