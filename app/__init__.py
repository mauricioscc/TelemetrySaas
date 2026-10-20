import os
import logging
from typing import Optional
from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from app.config import config_by_name, Config
from app.repositories.mongo_client import mongo_client


def configure_logging(app: Flask) -> None:
    """Configura o formato e o nível de logging da aplicação."""
    log_level = logging.DEBUG if app.config.get("DEBUG") else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
    )


def register_error_handlers(app: Flask) -> None:
    """Registra manipuladores de erro para garantir respostas JSON consistentes."""

    @app.errorhandler(HTTPException)
    def handle_http_exception(e: HTTPException):
        """Manipula exceções HTTP padrão do Werkzeug/Flask."""
        return jsonify({
            "error": e.name,
            "message": e.description,
            "status_code": e.code,
        }), e.code

    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({
            "error": "Bad Request",
            "message": str(error.description if hasattr(error, "description") else error),
            "status_code": 400,
        }), 400

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            "error": "Not Found",
            "message": "O recurso solicitado não foi encontrado nesta API.",
            "status_code": 404,
        }), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        return jsonify({
            "error": "Method Not Allowed",
            "message": "O método HTTP especificado não é permitido para esta rota.",
            "status_code": 405,
        }), 405

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        """Trata exceções não mapeadas sem vazar detalhes críticos em produção."""
        app.logger.exception(f"Erro interno não tratado: {error}")
        return jsonify({
            "error": "Internal Server Error",
            "message": "Ocorreu um erro interno no servidor ao processar a requisição.",
            "status_code": 500,
        }), 500


def register_blueprints(app: Flask) -> None:
    """Registra todos os Blueprints da aplicação."""
    from app.controllers.health_ctrl import health_bp
    from app.controllers.ingest_ctrl import telemetry_bp
    from app.controllers.dashboard_ctrl import dashboard_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(telemetry_bp)
    app.register_blueprint(dashboard_bp)


def create_app(config_name: Optional[str] = None) -> Flask:
    """
    Application Factory para criar e configurar a instância Flask.
    """
    app = Flask(__name__)

    # Determina o ambiente e carrega a configuração
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development").lower()

    config_class = config_by_name.get(config_name, Config)
    app.config.from_object(config_class)

    # Configuração de Logs
    configure_logging(app)

    # Inicializa conexão com MongoDB
    mongo_client.init_app(
        uri=app.config.get("MONGO_URI"),
        db_name=app.config.get("MONGO_DB_NAME"),
    )

    # Registra manipuladores globais de erro
    register_error_handlers(app)

    # Registra os Blueprints (Controllers)
    register_blueprints(app)

    app.logger.info(f"Aplicação inicializada com sucesso em modo '{config_name}'.")

    return app
