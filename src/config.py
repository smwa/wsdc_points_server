from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "WSDC Points API"
    database_url: str = "postgresql://localhost:5432/wsdc"

    # Set true in production (HTTPS) so the session cookie is marked Secure.
    cookie_secure: bool = False

    # Apply pending migrations (baked into the image) on app/importer startup.
    # Disable if migrations are applied out-of-band (e.g. a separate step).
    auto_migrate: bool = True

    # --- Data importer ---------------------------------------------------
    # The importer holds no dancer cache: it fetches each dancer straight from
    # the WSDC API and upserts it in its own transaction, scanning ids upward
    # and looping back to 1 forever so every dancer is refreshed over and over.

    # Required to geocode event locations not already in the geocode_cache table.
    open_weather_map_api_key: str = ""

    # Sleep between individual dancer fetches; raise this to run a slow,
    # WSDC-friendly loop. Default is polite rather than fast.
    importer_request_delay_seconds: float = 30.0
    # Sleep between full passes over the registry.
    importer_pass_delay_seconds: float = 0.0
    # Consecutive missing ids that signal the end of the registry for a pass.
    importer_none_slide_limit: int = 200

    # Prioritised refresh: a dancer who placed within this many years is
    # "likely" to have changed and is fetched every pass; everyone else is
    # "unlikely" and only re-fetched when their last import is older than
    # importer_unlikely_refresh_days. (Live mode only; ids not in the database
    # are never re-probed except the new-id scan above the current max id.)
    importer_recent_years: int = 3
    importer_unlikely_refresh_days: int = 28

    # Offline test mode: read the legacy raw cache files instead of hitting
    # WSDC. No request delay is applied. Pair with `python -m src.importer
    # --once` for a quick local import.
    importer_offline: bool = False
    raw_responses_path: str = "../wsdc_points/points/raw_responses.json.gz"
    raw_events_path: str = "../wsdc_points/points/raw_events.html.gz"


settings = Settings()
