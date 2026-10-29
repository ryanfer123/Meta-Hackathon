from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    replay_mode: bool = True
    auth_required: bool = True
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_access_token: SecretStr = SecretStr("")
    server_budget_key: SecretStr = SecretStr("")
    cloud_jobs: bool = False
    cors_origins: list[str] = ["https://apprentice-meta.onrender.com"]
    model_api_key: SecretStr = SecretStr("")
    glimmer_base_url: str = ""
    glimmer_api_key: SecretStr = SecretStr("")
    glimmer_model: str = "muse-glimmer"
    glimmer_max_tokens: int = Field(default=3000, ge=1, le=32768)
    open_tier_label: str = Field(default="glimmer", pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$")
    data_dir: Path = Path("data")
    sam_mode: Literal["video", "image"] = "image"
    sam_video_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1, le=50_000_000)
    max_sam_video_frames: int = Field(default=6000, ge=1)
    hosted_max_sam_video_frames: int = Field(default=6000, ge=1)
    max_sam_calls: int = Field(default=3000, ge=0)
    max_spark_calls: int = Field(default=40, ge=0)
    max_daily_spark_calls: int = Field(default=60, ge=0)
    max_run_cost_usd: float = Field(default=8, gt=0, allow_inf_nan=False)
    max_daily_cost_usd: float = Field(default=10, gt=0, allow_inf_nan=False)
    hosted_max_run_cost_usd: float = Field(default=8, gt=0, allow_inf_nan=False)
    hosted_max_daily_cost_usd: float = Field(default=10, gt=0, allow_inf_nan=False)
    max_upload_mb: int = Field(default=100, ge=1, le=500)

    @model_validator(mode="after")
    def honest_open_tier_label(self) -> "Settings":
        if "muse-spark-open" in self.glimmer_model.lower() and self.open_tier_label == "glimmer":
            self.open_tier_label = "spark-open"
        return self

    def require_live(self) -> None:
        if self.replay_mode or not self.model_api_key.get_secret_value():
            raise RuntimeError("Live inference disabled. Set REPLAY_MODE=false and MODEL_API_KEY.")
