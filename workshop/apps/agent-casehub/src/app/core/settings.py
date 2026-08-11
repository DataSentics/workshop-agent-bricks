"""
The whole configuration of the process, gathered into one object.

Each concern keeps its own model and its own environment prefix, and Settings assembles
them. The environment is read while this is built and not again, so one object holds
every value in use. The prefixes are the ones app.yaml already sets: UC_ for where the
data lives, and DATABRICKS_WAREHOUSE_ID and LLM_ENDPOINT under the names Databricks
Apps and the workshop use for them elsewhere.
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
        return version("agent-casehub")
    except PackageNotFoundError:
        return "0.0.0+local"


class AppSettings(BaseSettings):
    """
    OpenAPI metadata, uvicorn binding, and where the REST routes are mounted.
    """

    model_config = SettingsConfigDict(
        env_prefix="CASEHUB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    app_title: str = "CaseHub"
    app_description: str = "Saldo support case desk, and the agent that works it."
    app_version: str = Field(default_factory=_default_app_version)

    host: str = Field(
        default="0.0.0.0",
        validation_alias=AliasChoices("CASEHUB_HOST", "UVICORN_HOST"),
    )
    port: int = Field(
        default=8000,
        validation_alias=AliasChoices("CASEHUB_PORT", "UVICORN_PORT", "PORT"),
    )

    api_prefix: str = Field(
        default="/api",
        description=(
            "Prefix for what the UI calls. The probes, the UI itself and the agent "
            "routes stay at the root, where the platform and the supervisor look for "
            "them."
        ),
    )

    log_level: str = Field(
        default="INFO",
        description=(
            "Level the root logger is configured at. INFO by default because the log "
            "line naming who changed which case is how a workshop is followed from "
            "outside the room."
        ),
    )

    max_worker_threads: int = Field(
        default=128,
        gt=0,
        description=(
            "How many requests may be waiting on the warehouse or the model at once. "
            "Nothing here holds the event loop, so this is the real limit on how many "
            "people the app serves in parallel; anyio's default of 40 is a room-sized "
            "ceiling and an agent run occupies a thread for its whole length. The "
            "threads are idle on a socket rather than busy, so the cost of raising it "
            "is memory for the stacks."
        ),
    )


class CatalogSettings(BaseSettings):
    """
    Where the case desk's tables live and which warehouse reaches them.

    The seeded tables are read-only; case_state holds what each person changed. The
    fully qualified names are properties rather than settings of their own, so a table
    cannot be pointed somewhere its neighbours are not.
    """

    model_config = SettingsConfigDict(
        env_prefix="UC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    catalog: str = "vencam_sandbox"
    ops_schema: str = "agent_bricks_ws_saldo_ops"
    platform_schema: str = "agent_bricks_ws_saldo_platform"
    warehouse_id: str = Field(
        default="80cda2c5133fbdc6",
        validation_alias=AliasChoices("UC_WAREHOUSE_ID", "DATABRICKS_WAREHOUSE_ID"),
        description="Warehouse every case read and write is executed on.",
    )

    @property
    def cases_table(self) -> str:
        """
        The seeded cases, as everyone in the workshop finds them.
        """
        return f"{self.catalog}.{self.platform_schema}.support_cases"

    @property
    def notes_table(self) -> str:
        """
        The seeded case narratives.
        """
        return f"{self.catalog}.{self.platform_schema}.case_notes"

    @property
    def state_table(self) -> str:
        """
        What each person changed, one row per case they touched.
        """
        return f"{self.catalog}.{self.platform_schema}.case_state"

    @property
    def clients_table(self) -> str:
        """
        Customers, joined in so a case reads as a company rather than a client id.
        """
        return f"{self.catalog}.{self.ops_schema}.clients"


class AgentSettings(BaseSettings):
    """
    The model the agent thinks with and how long it is allowed to think for.
    """

    model_config = SettingsConfigDict(
        env_prefix="CASEHUB_AGENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    llm_endpoint: str = Field(
        default="databricks-claude-sonnet-4-5",
        validation_alias=AliasChoices("CASEHUB_AGENT_LLM_ENDPOINT", "LLM_ENDPOINT"),
        description="Foundation Model serving endpoint the tool loop calls.",
    )
    max_turns: int = Field(
        default=8,
        gt=0,
        description=(
            "Tool-calling rounds before the agent gives up and says so. A loop that "
            "never terminates would otherwise hold the supervisor's request open."
        ),
    )
    max_tokens: int = Field(default=1500, gt=0)


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
    catalog: CatalogSettings = Field(default_factory=CatalogSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
