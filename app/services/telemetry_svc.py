import json
import logging
import queue
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from app.repositories.telemetry_repo import telemetry_repo, TelemetryRepository

logger = logging.getLogger(__name__)


class TelemetryValidationError(ValueError):
    """Exceção para validação de dados de telemetria."""
    pass


class TelemetryService:
    """
    Serviço de alta frequência com persistência assíncrona em background
    e streaming em tempo real (Pub/Sub) de latência zero.
    """

    def __init__(self, repository: TelemetryRepository = telemetry_repo):
        self._repo = repository
        self._listeners: List[queue.Queue] = []
        self._lock = threading.Lock()

        # Fila assíncrona para não bloquear requisições HTTP esperando o MongoDB Atlas na nuvem
        self._db_queue: queue.Queue = queue.Queue(maxsize=10000)
        self._worker_thread = threading.Thread(target=self._db_worker, daemon=True, name="TelemetryDBWorker")
        self._worker_thread.start()

    def _db_worker(self) -> None:
        """
        Thread em background que consome a fila e grava no MongoDB Atlas em lotes (batch),
        garantindo que o loop de streaming no Flask responda em < 1ms sem travar.
        """
        while True:
            items: List[Dict[str, Any]] = []
            try:
                # Aguarda o primeiro item
                item = self._db_queue.get(timeout=0.2)
                items.append(item)

                # Drena até 100 itens da fila de uma só vez para gravar em lote (insert_batch)
                while len(items) < 100:
                    try:
                        items.append(self._db_queue.get_nowait())
                    except queue.Empty:
                        break
            except queue.Empty:
                continue

            if items:
                try:
                    if len(items) == 1:
                        self._repo.insert_telemetry(items[0])
                    else:
                        self._repo.insert_batch(items)
                except Exception as exc:
                    logger.error(f"Erro no background writer do MongoDB Atlas: {exc}")
                finally:
                    for _ in items:
                        self._db_queue.task_done()

    def add_listener(self) -> queue.Queue:
        """Registra um ouvinte para streaming SSE em tempo real."""
        q = queue.Queue(maxsize=100)
        with self._lock:
            self._listeners.append(q)
        return q

    def remove_listener(self, q: queue.Queue) -> None:
        """Remove o ouvinte após desconexão."""
        with self._lock:
            if q in self._listeners:
                self._listeners.remove(q)

    def _broadcast(self, record: Dict[str, Any]) -> None:
        """
        Transmite o pacote em tempo real (in-memory) para o dashboard em < 0.1ms.
        """
        with self._lock:
            if not self._listeners:
                return
            listeners = list(self._listeners)

        payload = {
            "timestamp": record["timestamp"].isoformat()
            if isinstance(record["timestamp"], datetime)
            else str(record["timestamp"]),
            "metadata": record["metadata"],
            "measurements": record["measurements"],
        }

        for q in listeners:
            try:
                q.put_nowait(payload)
            except queue.Full:
                try:
                    q.get_nowait()
                    q.put_nowait(payload)
                except Exception:
                    pass

    def process_telemetry(
        self, data: Union[Dict[str, Any], List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """
        Processa telemetria em alta frequência:
        1. Valida e sanitiza na memória (< 0.1ms)
        2. Dispara broadcast SSE imediatamente (< 0.1ms)
        3. Enfileira para gravação assíncrona no MongoDB Atlas (0ms de espera!)
        """
        if not data:
            raise TelemetryValidationError("O payload de telemetria não pode ser vazio.")

        if isinstance(data, list):
            if len(data) > 1000:
                raise TelemetryValidationError("Limite máximo de 1000 itens por lote excedido.")

            sanitized_batch = [self._validate_and_sanitize_record(item, idx) for idx, item in enumerate(data)]
            
            # Broadcast imediato do último dado para o painel
            if sanitized_batch:
                self._broadcast(sanitized_batch[-1])

            # Enfileira para gravação assíncrona no Atlas
            for item in sanitized_batch:
                try:
                    self._db_queue.put_nowait(item)
                except queue.Full:
                    pass

            return {
                "status": "success",
                "mode": "batch",
                "count": len(sanitized_batch),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        elif isinstance(data, dict):
            sanitized = self._validate_and_sanitize_record(data)
            
            # Broadcast imediato no mesmo tick
            self._broadcast(sanitized)

            # Enfileira para persistência no Atlas sem bloquear a requisição
            try:
                self._db_queue.put_nowait(sanitized)
            except queue.Full:
                pass

            return {
                "status": "success",
                "mode": "single",
                "count": 1,
                "vehicle_id": sanitized["metadata"]["vehicle_id"],
                "timestamp": sanitized["timestamp"].isoformat(),
            }
        else:
            raise TelemetryValidationError("O payload deve ser um objeto JSON ou uma lista de objetos.")

    def get_latest_telemetry(self, vehicle_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Busca o registro mais recente para monitoramento ao vivo."""
        return self._repo.get_latest(vehicle_id)

    def get_history(self, vehicle_id: Optional[str] = None, limit: int = 60) -> List[Dict[str, Any]]:
        """Busca histórico ordenado para gráficos."""
        limit = min(max(1, limit), 500)
        return self._repo.get_history(vehicle_id, limit=limit)

    def list_vehicles(self) -> List[Dict[str, Any]]:
        """Lista os veículos ativos que enviaram telemetria."""
        return self._repo.get_distinct_vehicles()

    def get_vehicle_stats(self, vehicle_id: str) -> Dict[str, Any]:
        """Retorna resumo analítico de performance do veículo."""
        if not vehicle_id:
            raise TelemetryValidationError("vehicle_id é obrigatório para consultar estatísticas.")
        return self._repo.get_vehicle_stats(vehicle_id)

    def _validate_and_sanitize_record(
        self, record: Any, index: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Valida tipos, limites físicos dos sensores e garante tipos BSON corretos.
        """
        prefix = f"Item [{index}]: " if index is not None else ""

        if not isinstance(record, dict):
            raise TelemetryValidationError(f"{prefix}Cada leitura deve ser um objeto JSON.")

        # 1. Metadata
        metadata = record.get("metadata")
        if not metadata or not isinstance(metadata, dict):
            raise TelemetryValidationError(f"{prefix}O campo 'metadata' é obrigatório e deve ser um objeto.")

        vehicle_id = metadata.get("vehicle_id")
        if not vehicle_id or not isinstance(vehicle_id, str) or not vehicle_id.strip():
            raise TelemetryValidationError(f"{prefix}'metadata.vehicle_id' é obrigatório e não pode ser vazio.")

        clean_metadata = {
            "vehicle_id": vehicle_id.strip(),
            "model": str(metadata.get("model", "Veículo Genérico")).strip(),
            "ecu_profile": str(metadata.get("ecu_profile", "Stock")).strip(),
        }

        # 2. Measurements
        measurements = record.get("measurements")
        if not measurements or not isinstance(measurements, dict):
            raise TelemetryValidationError(f"{prefix}O campo 'measurements' é obrigatório e deve ser um objeto.")

        clean_measurements = self._sanitize_measurements(measurements, prefix)

        # 3. Timestamp
        raw_timestamp = record.get("timestamp")
        timestamp = self._parse_timestamp(raw_timestamp, prefix)

        return {
            "timestamp": timestamp,
            "metadata": clean_metadata,
            "measurements": clean_measurements,
        }

    def _sanitize_measurements(self, m: Dict[str, Any], prefix: str) -> Dict[str, Any]:
        """Garante limites numéricos de segurança da telemetria e suporta telemetria FuelTech/Forza."""
        try:
            rpm = float(m.get("rpm", 0))
            if rpm < 0 or rpm > 20000:
                raise TelemetryValidationError(f"{prefix}'rpm' fora do limite aceitável (0 a 20000).")

            speed_kmh = float(m.get("speed_kmh", 0))
            if speed_kmh < 0 or speed_kmh > 600:
                raise TelemetryValidationError(f"{prefix}'speed_kmh' fora do limite aceitável (0 a 600).")

            boost = float(m.get("boost_pressure_bar", 0.0))
            if boost < -1.5 or boost > 8.0:
                raise TelemetryValidationError(f"{prefix}'boost_pressure_bar' fora do limite aceitável (-1.5 a 8.0 bar).")

            oil_temp = float(m.get("oil_temp_c", 90.0))
            if oil_temp < -40 or oil_temp > 200:
                raise TelemetryValidationError(f"{prefix}'oil_temp_c' fora do limite aceitável (-40 a 200°C).")

            clean = {
                "rpm": round(rpm, 0),
                "speed_kmh": round(speed_kmh, 1),
                "boost_pressure_bar": round(boost, 2),
                "oil_temp_c": round(oil_temp, 1),
            }

            # Campos adicionais estilo FuelTech / Corrida
            if "max_rpm" in m and m["max_rpm"] is not None:
                clean["max_rpm"] = round(float(m["max_rpm"]), 0)
            if "gear" in m:
                clean["gear"] = str(m["gear"])
            if "throttle_pct" in m:
                clean["throttle_pct"] = max(0.0, min(100.0, round(float(m["throttle_pct"]), 1)))
            if "brake_pct" in m:
                clean["brake_pct"] = max(0.0, min(100.0, round(float(m["brake_pct"]), 1)))
            if "power_hp" in m:
                clean["power_hp"] = round(float(m["power_hp"]), 1)
            if "torque_nm" in m:
                clean["torque_nm"] = round(float(m["torque_nm"]), 1)
            if "g_force_lat" in m:
                clean["g_force_lat"] = round(float(m["g_force_lat"]), 2)
            if "g_force_long" in m:
                clean["g_force_long"] = round(float(m["g_force_long"]), 2)
            if "coolant_temp_c" in m:
                clean["coolant_temp_c"] = round(float(m["coolant_temp_c"]), 1)

            return clean
        except (ValueError, TypeError) as exc:
            if isinstance(exc, TelemetryValidationError):
                raise
            raise TelemetryValidationError(f"{prefix}Valor numérico inválido nos sensores: {exc}")

    def _parse_timestamp(self, raw_timestamp: Any, prefix: str) -> datetime:
        """Converte timestamp de entrada para datetime UTC."""
        if raw_timestamp is None:
            return datetime.now(timezone.utc)

        if isinstance(raw_timestamp, datetime):
            if raw_timestamp.tzinfo is None:
                return raw_timestamp.replace(tzinfo=timezone.utc)
            return raw_timestamp

        if isinstance(raw_timestamp, str):
            try:
                ts_str = raw_timestamp.replace("Z", "+00:00")
                parsed = datetime.fromisoformat(ts_str)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
            except ValueError:
                raise TelemetryValidationError(
                    f"{prefix}Timestamp '{raw_timestamp}' inválido. Utilize o formato ISO 8601."
                )

        raise TelemetryValidationError(f"{prefix}Timestamp em formato não suportado.")


telemetry_service = TelemetryService()
