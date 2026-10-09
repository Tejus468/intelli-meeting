from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # PostgreSQL Configuration
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "intelli_meeting"
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"

    # Neo4j Configuration
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "password123"

    # Embedding Configuration
    embedding_model: str = "BAAI/bge-large-en-v1.5"
    embedding_dimension: int = 1024

    # LLM Configuration
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_timeout_seconds: float = 60.0
    # Send response_format={"type": "json_object"}. Disable for local models (e.g. gemma3 on Ollama)
    # that return "{}" in JSON mode; the client still parses JSON out of plain/fenced replies.
    llm_json_mode: bool = True

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def postgres_connection_string(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
