from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, current_app
from app.repositories.mongo_client import mongo_client

health_bp = Blueprint("health", __name__)


@health_bp.route("/", methods=["GET"])
def api_index():
    """Endpoint raiz com informações gerais da API."""
    return jsonify({
        "service": "Automotive Telemetry SaaS API",
        "version": "1.0.0",
        "status": "online",
        "documentation": "/api/v1/health",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }), 200


@health_bp.route("/api/v1/health", methods=["GET"])
def health_check():
    """
    Health check completo do serviço.
    Retorna status da aplicação e validação opcional da conexão com o MongoDB.
    """
    include_db = request.args.get("db", "true").lower() in ("true", "1", "yes")

    health_status = {
        "status": "healthy",
        "environment": current_app.config.get("ENV", "development"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0",
    }

    if include_db:
        db_health = mongo_client.check_health()
        health_status["database"] = db_health
        if db_health.get("status") not in ("connected", "unconfigured"):
            health_status["status"] = "degraded"

    return jsonify(health_status), 200
