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
