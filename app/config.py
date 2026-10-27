import os
from dotenv import load_dotenv

# Carrega variáveis do arquivo .env se presente
load_dotenv()


class Config:
    """Configuração base compartilhada."""
    ENV = os.getenv("FLASK_ENV", "production")
    DEBUG = False
    TESTING = False
    PORT = int(os.getenv("PORT", 5000))
    HOST = os.getenv("HOST", "127.0.0.1")
    TELEMETRY_STORAGE = os.getenv("TELEMETRY_STORAGE", "memory").strip().lower()

    # Configurações do MongoDB
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "telemetry_saas")
    MONGO_COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME", "vehicle_telemetry")


class DevelopmentConfig(Config):
    """Configuração para ambiente de desenvolvimento."""
    DEBUG = True
    ENV = "development"


class TestingConfig(Config):
    """Configuração para testes automatizados."""
    TESTING = True
    DEBUG = True
    ENV = "testing"
    TELEMETRY_STORAGE = "memory"
    MONGO_DB_NAME = f"{Config.MONGO_DB_NAME}_test"


class ProductionConfig(Config):
    """Configuração para ambiente de produção."""
    DEBUG = False
    ENV = "production"


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
