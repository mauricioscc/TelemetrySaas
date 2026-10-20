import json
import logging
import queue
from flask import Blueprint, Response, jsonify, request, stream_with_context
from app.services.telemetry_svc import telemetry_service, TelemetryValidationError

logger = logging.getLogger(__name__)

telemetry_bp = Blueprint("telemetry", __name__, url_prefix="/api/v1/telemetry")


@telemetry_bp.route("", methods=["POST"])
def ingest_telemetry():
    """
    Endpoint principal para ingestão de telemetria em alta frequência.
    Aceita um documento individual ou uma lista de documentos para batch ingestion.
    """
    if not request.is_json:
        return jsonify({
            "error": "Bad Request",
            "message": "Content-Type deve ser 'application/json' e conter um corpo JSON válido.",
            "status_code": 400,
        }), 400

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({
            "error": "Bad Request",
            "message": "Corpo JSON malformado ou nulo.",
            "status_code": 400,
        }), 400

    try:
        result = telemetry_service.process_telemetry(data)
        return jsonify(result), 201
    except TelemetryValidationError as exc:
        return jsonify({
            "error": "Unprocessable Entity",
            "message": str(exc),
            "status_code": 422,
        }), 422
    except Exception as exc:
        logger.exception(f"Erro interno durante ingestão de telemetria: {exc}")
        return jsonify({
            "error": "Internal Server Error",
            "message": "Falha ao persistir telemetria no banco de dados.",
            "details": str(exc),
            "status_code": 500,
        }), 500


@telemetry_bp.route("/stream", methods=["GET"])
def stream_telemetry():
    """
    Endpoint de Streaming em Tempo Real (Server-Sent Events / SSE).
    Permite ao Dashboard receber os dados de telemetria no exato instante
    em que chegam do Forza ou do simulador, com latência imperceptível (< 15ms).
    """
    def event_stream():
        q = telemetry_service.add_listener()
        try:
            # Envia imediatamente o pacote mais recente para abrir os mostradores
            vehicle_filter = request.args.get("vehicle_id")
            latest = telemetry_service.get_latest_telemetry(vehicle_filter)
            if latest:
                yield f"data: {json.dumps(latest)}\n\n"

            while True:
                try:
                    # Aguarda o próximo pacote empurrado pelo Forza / simulador
                    packet = q.get(timeout=15.0)
                    if vehicle_filter:
                        v_id = packet.get("metadata", {}).get("vehicle_id")
                        if v_id != vehicle_filter:
                            continue
                    yield f"data: {json.dumps(packet)}\n\n"
                except queue.Empty:
                    # Ping keep-alive para manter a conexão aberta em HTTP
                    yield ": ping\n\n"
        except GeneratorExit:
            pass
        finally:
            telemetry_service.remove_listener(q)

    return Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@telemetry_bp.route("/latest", methods=["GET"])
def get_latest_telemetry():
    """
    Retorna a telemetria mais recente registrada.
    Suporta filtro por veículo via query param: ?vehicle_id=VW-GOLF-R
    """
    vehicle_id = request.args.get("vehicle_id")
    record = telemetry_service.get_latest_telemetry(vehicle_id)

    if not record:
        return jsonify({
            "status": "not_found",
            "message": f"Nenhuma leitura de telemetria encontrada{' para o veículo ' + vehicle_id if vehicle_id else ''}.",
            "data": None,
        }), 404

    return jsonify({
        "status": "success",
        "data": record,
    }), 200


@telemetry_bp.route("/history", methods=["GET"])
def get_telemetry_history():
    """
    Retorna o histórico cronológico de telemetria para alimentar gráficos.
    Parâmetros: ?vehicle_id=... & limit=60
    """
    vehicle_id = request.args.get("vehicle_id")
    try:
        limit = int(request.args.get("limit", 60))
    except ValueError:
        limit = 60

    history = telemetry_service.get_history(vehicle_id, limit)
    return jsonify({
        "status": "success",
        "count": len(history),
        "vehicle_id": vehicle_id,
        "data": history,
    }), 200


@telemetry_bp.route("/vehicles", methods=["GET"])
def list_vehicles():
    """Retorna os veículos que já enviaram telemetria."""
    vehicles = telemetry_service.list_vehicles()
    return jsonify({
        "status": "success",
        "count": len(vehicles),
        "vehicles": vehicles,
    }), 200


@telemetry_bp.route("/stats/<vehicle_id>", methods=["GET"])
def get_vehicle_stats(vehicle_id: str):
    """Retorna os recordes e médias de desempenho do veículo."""
    stats = telemetry_service.get_vehicle_stats(vehicle_id)
    if not stats:
        return jsonify({
            "status": "not_found",
            "message": f"Sem estatísticas disponíveis para o veículo '{vehicle_id}'.",
        }), 404

    return jsonify({
        "status": "success",
        "stats": stats,
    }), 200
