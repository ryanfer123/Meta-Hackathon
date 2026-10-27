from pathlib import Path

from pydantic import Field, SecretStr
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
    data_dir: Path = Path("data")
    max_sam_calls: int = Field(default=120, ge=0)
    max_spark_calls: int = Field(default=12, ge=0)
    max_daily_spark_calls: int = Field(default=60, ge=0)
    max_run_cost_usd: float = Field(default=2, gt=0)
    max_upload_mb: int = Field(default=100, ge=1, le=500)

    def require_live(self) -> None:
        if self.replay_mode or not self.model_api_key.get_secret_value():
            raise RuntimeError("Live inference disabled. Set REPLAY_MODE=false and MODEL_API_KEY.")
