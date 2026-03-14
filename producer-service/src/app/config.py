from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "producer-service"
    app_port: int = 8000

    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"
    rabbitmq_virtual_host: str = "/"
    rabbitmq_queue: str = "user_activity_events"
    rabbitmq_heartbeat: int = 60
    rabbitmq_blocked_connection_timeout: int = 30
    rabbitmq_connection_retries: int = 5
    rabbitmq_retry_delay_seconds: int = 2

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)
