import logging
import os
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pymongo.errors import CollectionInvalid, OperationFailure, PyMongoError

from app.repositories.mongo_client import mongo_client, MongoDBClient

logger = logging.getLogger(__name__)


class TelemetryRepository:
    """
    Repositório para persistência e consulta de dados de telemetria
    utilizando Coleções Time-Series do MongoDB.
    """

    def __init__(
        self,
        client: MongoDBClient = mongo_client,
        collection_name: Optional[str] = None,
    ):
        self._client = client
        self._collection_name = collection_name or os.getenv(
            "MONGO_COLLECTION_NAME", "vehicle_telemetry"
        )
        self._collection_initialized = False

    @property
    def db(self):
        return self._client.get_database()

    @property
    def collection(self):
        self.ensure_timeseries_collection()
        return self.db[self._collection_name]

    def ensure_timeseries_collection(self) -> bool:
        """
        Garante que a coleção de telemetria seja criada como uma Time-Series Collection nativa.
        timeField: 'timestamp'
        metaField: 'metadata'
        granularity: 'seconds'
        """
        if self._collection_initialized:
            return True

        try:
            db = self.db
            existing_collections = db.list_collection_names()

            if self._collection_name not in existing_collections:
                logger.info(
                    f"Criando Time-Series Collection '{self._collection_name}'..."
                )
                db.create_collection(
                    self._collection_name,
                    timeseries={
                        "timeField": "timestamp",
                        "metaField": "metadata",
                        "granularity": "seconds",
                    },
                )
                logger.info(
                    f"Time-Series Collection '{self._collection_name}' criada com sucesso!"
                )
            self._collection_initialized = True
            return True
        except (CollectionInvalid, OperationFailure) as exc:
            # Caso a coleção já exista em concorrência
            if "already exists" in str(exc).lower() or getattr(exc, "code", None) == 48:
                self._collection_initialized = True
                return True
            logger.warning(
                f"Aviso ao inicializar coleção Time-Series '{self._collection_name}': {exc}"
            )
            # Permite continuar mesmo em instâncias do Mongo com restrições
            self._collection_initialized = True
            return False
        except Exception as exc:
            logger.error(f"Erro inesperado ao inicializar Time-Series Collection: {exc}")
            return False

    def insert_telemetry(self, record: Dict[str, Any]) -> str:
        """
        Insere uma única leitura de telemetria na coleção Time-Series.
        """
        try:
            result = self.collection.insert_one(record)
            return str(result.inserted_id)
        except PyMongoError as exc:
            logger.error(f"Falha ao persistir telemetria: {exc}")
            raise

    def insert_batch(self, records: List[Dict[str, Any]]) -> List[str]:
        """
        Insere um lote (batch) de telemetrias em uma única operação atômica de rede.
        Ideal para rajadas de dados de alta frequência.
        """
        if not records:
            return []
        try:
            result = self.collection.insert_many(records, ordered=False)
            return [str(idx) for idx in result.inserted_ids]
        except PyMongoError as exc:
            logger.error(f"Falha ao persistir lote de telemetria: {exc}")
            raise

    def get_latest(self, vehicle_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Retorna o último registro de telemetria recebido (global ou por veículo).
        """
        try:
            filter_query = {}
            if vehicle_id:
                filter_query["metadata.vehicle_id"] = vehicle_id

            doc = self.collection.find_one(filter_query, sort=[("timestamp", -1)])
            if doc:
                return self._serialize_doc(doc)
            return None
        except PyMongoError as exc:
            logger.error(f"Erro ao buscar telemetria mais recente: {exc}")
            return None

    def get_history(
        self, vehicle_id: Optional[str] = None, limit: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Retorna os registros mais recentes ordenados cronologicamente (do mais antigo para o mais novo).
        Ideal para desenhar gráficos em tempo real no Dashboard.
        """
        try:
            filter_query = {}
            if vehicle_id:
                filter_query["metadata.vehicle_id"] = vehicle_id

            # Pega os N mais recentes
            cursor = self.collection.find(
                filter_query, sort=[("timestamp", -1)]
            ).limit(limit)

            docs = list(cursor)
            # Inverte para ordem cronológica (linha do tempo para gráfico)
            docs.reverse()
            return [self._serialize_doc(d) for d in docs]
        except PyMongoError as exc:
            logger.error(f"Erro ao buscar histórico de telemetria: {exc}")
            return []

    def get_distinct_vehicles(self) -> List[Dict[str, Any]]:
        """
        Retorna a lista de veículos distintos identificados no banco.
        """
        try:
            pipeline = [
                {
                    "$group": {
                        "_id": "$metadata.vehicle_id",
                        "model": {"$last": "$metadata.model"},
                        "ecu_profile": {"$last": "$metadata.ecu_profile"},
                        "last_seen": {"$max": "$timestamp"},
                        "total_pings": {"$sum": 1},
                    }
                },
                {"$sort": {"last_seen": -1}},
            ]
            results = list(self.collection.aggregate(pipeline))
            serialized = []
            for item in results:
                serialized.append(
                    {
                        "vehicle_id": item.get("_id"),
                        "model": item.get("model", "Desconhecido"),
                        "ecu_profile": item.get("ecu_profile", "Stock"),
                        "last_seen": item.get("last_seen").isoformat()
                        if isinstance(item.get("last_seen"), datetime)
                        else str(item.get("last_seen")),
                        "total_pings": item.get("total_pings", 0),
                    }
                )
            return serialized
        except PyMongoError as exc:
            logger.error(f"Erro ao listar veículos: {exc}")
            return []

    def get_vehicle_stats(self, vehicle_id: str) -> Dict[str, Any]:
        """
        Executa agregação para calcular estatísticas de desempenho do veículo.
        """
        try:
            pipeline = [
                {"$match": {"metadata.vehicle_id": vehicle_id}},
                {
                    "$group": {
                        "_id": "$metadata.vehicle_id",
                        "max_rpm": {"$max": "$measurements.rpm"},
                        "max_speed_kmh": {"$max": "$measurements.speed_kmh"},
                        "max_boost_bar": {"$max": "$measurements.boost_pressure_bar"},
                        "max_oil_temp_c": {"$max": "$measurements.oil_temp_c"},
                        "avg_speed_kmh": {"$avg": "$measurements.speed_kmh"},
                        "total_samples": {"$sum": 1},
                        "first_seen": {"$min": "$timestamp"},
                        "last_seen": {"$max": "$timestamp"},
                    }
                },
            ]
            results = list(self.collection.aggregate(pipeline))
            if not results:
                return {}

            stats = results[0]
            return {
                "vehicle_id": stats.get("_id"),
                "max_rpm": round(float(stats.get("max_rpm") or 0), 0),
                "max_speed_kmh": round(float(stats.get("max_speed_kmh") or 0), 1),
                "max_boost_bar": round(float(stats.get("max_boost_bar") or 0), 2),
                "max_oil_temp_c": round(float(stats.get("max_oil_temp_c") or 0), 1),
                "avg_speed_kmh": round(float(stats.get("avg_speed_kmh") or 0), 1),
                "total_samples": stats.get("total_samples", 0),
            }
        except PyMongoError as exc:
            logger.error(f"Erro ao calcular estatísticas do veículo: {exc}")
            return {}

    @staticmethod
    def _serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
        """Converte ObjectId e datetime para strings JSON-compliant."""
        res = dict(doc)
        if "_id" in res:
            res["id"] = str(res.pop("_id"))
        if "timestamp" in res and isinstance(res["timestamp"], datetime):
            res["timestamp"] = res["timestamp"].isoformat()
        return res


telemetry_repo = TelemetryRepository()
