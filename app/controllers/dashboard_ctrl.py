import logging
from flask import Blueprint, render_template

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard", methods=["GET"])
def live_dashboard():
    """
    Renderiza o painel visual de instrumentos e telemetria em tempo real.
    """
    return render_template("dashboard.html")


@dashboard_bp.route("/dashboard/ft600", methods=["GET"])
def ft600_dashboard():
    """Renderiza o painel alternativo em estilo de cluster de corrida."""
    return render_template("ft600_dashboard.html")
