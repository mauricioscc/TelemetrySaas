import logging
import certifi
from typing import Optional
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

logger = logging.getLogger(__name__)


class MongoDBClient:
    """Gerenciador de conexão com o MongoDB."""

    _instance: Optional["MongoDBClient"] = None
    _client: Optional[MongoClient] = None
    _db: Optional[Database] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoDBClient, cls).__new__(cls)
        return cls._instance

    def init_app(self, uri: str, db_name: str) -> None:
        """Inicializa a conexão com o banco de dados MongoDB."""
        self._uri = uri
        self._db_name = db_name
        self._client = MongoClient(
            self._uri,
            serverSelectionTimeoutMS=2000,
            connect=False,  # Conexão sob demanda (lazy)
            tlsCAFile=certifi.where()
        )
        self._db = self._client[self._db_name]
        logger.info(f"MongoDB configurado para o banco '{self._db_name}'.")

    def get_database(self) -> Database:
        """Retorna a instância do banco de dados configurado."""
        if self._db is None:
            raise RuntimeError("MongoDBClient não foi inicializado com init_app().")
        return self._db

    def check_health(self) -> dict:
        """Verifica a conectividade ativa com o MongoDB."""
        if self._client is None:
            return {
                "status": "unconfigured",
                "message": "Cliente MongoDB não inicializado.",
            }

        try:
            # Comando ping rápido para checar integridade do cluster
            self._client.admin.command("ping")
            return {
                "status": "connected",
                "database": self._db_name,
                "message": "Conexão com o MongoDB estabelecida com sucesso.",
            }
        except (ConnectionFailure, ServerSelectionTimeoutError) as exc:
            logger.warning(f"Falha ao conectar no MongoDB: {exc}")
            return {
                "status": "disconnected",
                "database": self._db_name,
                "message": f"Não foi possível conectar ao MongoDB: {str(exc)}",
            }
        except Exception as exc:
            logger.error(f"Erro inesperado no MongoDB: {exc}")
            return {
                "status": "error",
                "database": self._db_name,
                "message": str(exc),
            }

    def close(self) -> None:
        """Fecha conexões ativas com o cluster MongoDB."""
        if self._client:
            self._client.close()
            logger.info("Conexão com o MongoDB encerrada.")


mongo_client = MongoDBClient()
