import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from app.repositories.telemetry_repo import telemetry_repo, TelemetryRepository

logger = logging.getLogger(__name__)


class TelemetryValidationError(ValueError):
    """Exceção para validação de dados de telemetria."""
    pass


class TelemetryService:
    """
    Serviço responsável pela sanitização, validação e orquestração
    dos dados de telemetria de alta frequência.
    """

    def __init__(self, repository: TelemetryRepository = telemetry_repo):
        self._repo = repository

    def process_telemetry(
        self, data: Union[Dict[str, Any], List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """
        Processa e persiste um payload de telemetria (único ou em lote).
        """
        if not data:
            raise TelemetryValidationError("O payload de telemetria não pode ser vazio.")

        if isinstance(data, list):
            # Processamento em lote (Batch Ingestion)
            if len(data) > 1000:
                raise TelemetryValidationError("Limite máximo de 1000 itens por lote excedido.")

            sanitized_batch = [self._validate_and_sanitize_record(item, idx) for idx, item in enumerate(data)]
            ids = self._repo.insert_batch(sanitized_batch)
            return {
                "status": "success",
                "mode": "batch",
                "count": len(ids),
                "inserted_ids": ids,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        elif isinstance(data, dict):
            # Processamento unitário
            sanitized = self._validate_and_sanitize_record(data)
            inserted_id = self._repo.insert_telemetry(sanitized)
            return {
                "status": "success",
                "mode": "single",
                "count": 1,
                "inserted_id": inserted_id,
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

        # 1. Validação de Metadata
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

        # 2. Validação de Measurements (Sensores)
        measurements = record.get("measurements")
        if not measurements or not isinstance(measurements, dict):
            raise TelemetryValidationError(f"{prefix}O campo 'measurements' é obrigatório e deve ser um objeto.")

        clean_measurements = self._sanitize_measurements(measurements, prefix)

        # 3. Validação de Timestamp (Obrigatório ser datetime nativo para MongoDB Time-Series)
        raw_timestamp = record.get("timestamp")
        timestamp = self._parse_timestamp(raw_timestamp, prefix)

        return {
            "timestamp": timestamp,
            "metadata": clean_metadata,
            "measurements": clean_measurements,
        }

    def _sanitize_measurements(self, m: Dict[str, Any], prefix: str) -> Dict[str, Any]:
        """Garante limites numéricos de segurança da telemetria."""
        try:
            rpm = float(m.get("rpm", 0))
            if rpm < 0 or rpm > 15000:
                raise TelemetryValidationError(f"{prefix}'rpm' fora do limite aceitável (0 a 15000).")

            speed_kmh = float(m.get("speed_kmh", 0))
            if speed_kmh < 0 or speed_kmh > 500:
                raise TelemetryValidationError(f"{prefix}'speed_kmh' fora do limite aceitável (0 a 500).")

            boost = float(m.get("boost_pressure_bar", 0.0))
            if boost < -1.5 or boost > 6.0:
                raise TelemetryValidationError(f"{prefix}'boost_pressure_bar' fora do limite aceitável (-1.5 a 6.0 bar).")

            oil_temp = float(m.get("oil_temp_c", 90.0))
            if oil_temp < -40 or oil_temp > 200:
                raise TelemetryValidationError(f"{prefix}'oil_temp_c' fora do limite aceitável (-40 a 200°C).")

            clean = {
                "rpm": round(rpm, 0),
                "speed_kmh": round(speed_kmh, 1),
                "boost_pressure_bar": round(boost, 2),
                "oil_temp_c": round(oil_temp, 1),
            }

            # Campos adicionais opcionais (marcha, acelerador, temperatura de arrefecimento)
            if "gear" in m:
                clean["gear"] = str(m["gear"])
            if "throttle_pct" in m:
                clean["throttle_pct"] = max(0.0, min(100.0, float(m["throttle_pct"])))
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
                # Trata formato ISO (ex: 2026-10-20T19:00:00Z ou com microsegundos)
                ts_str = raw_timestamp.replace("Z", "+00:00")
                parsed = datetime.fromisoformat(ts_str)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
            except ValueError:
                raise TelemetryValidationError(
                    f"{prefix}Timestamp '{raw_timestamp}' inválido. Utilize o formato ISO 8601 (ex: '2026-10-20T18:00:00Z')."
                )

        raise TelemetryValidationError(f"{prefix}Timestamp em formato não suportado.")


telemetry_service = TelemetryService()
