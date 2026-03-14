from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PostgreSQL
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "logyca"
    postgres_user: str = "logyca"
    postgres_password: str = "logyca_secret"

    # Azure Storage
    azure_storage_connection_string: str = ""
    azure_container_name: str = "csv-uploads"
    azure_queue_name: str = "csv-processing"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    class Config:
        env_file = ".env"


settings = Settings()
