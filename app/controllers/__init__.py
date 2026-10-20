from app.controllers.health_ctrl import health_bp
from app.controllers.ingest_ctrl import telemetry_bp
from app.controllers.dashboard_ctrl import dashboard_bp

__all__ = ["health_bp", "telemetry_bp", "dashboard_bp"]
