from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    product_name: str = "PROBE"
    anthropic_api_key: str = ""
    model_agents: str = "claude-sonnet-5-5"  # intent, flight director, persona
    model_voice: str = "claude-haiku-5-5"  # milestone messages
    x402_pay_to: str = "0x0000000000000000000000000000000000000000"
    x402_network: str = "eip155:84532"
    x402_sync_on_start: bool = False
    checkout_provider: str = "dev"
    public_host: str = "127.0.0.1"
    price_mission_design: str = "$1.00"

    data_dir: Path = Path("data")
    ephemeris_source: str = "horizons"  # "horizons" (live JPL) or "de421" (offline JPL kernel)
    search_horizon_days: float = 1100.0
    search_workers: int = 2
    search_maxiter: int = 250
    waker_interval_s: int = 600  # how often the in-process waker checks for due milestones
    free_probes_per_browser: int = 1


settings = Settings()
