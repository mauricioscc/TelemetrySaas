import os
from dotenv import load_dotenv
from app import create_app

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

# Instanciação da aplicação via Factory Pattern
app = create_app()

if __name__ == "__main__":
    host = app.config.get("HOST", "127.0.0.1")
    port = app.config.get("PORT", 5000)
    debug = app.config.get("DEBUG", True)

    app.logger.info(f"Iniciando Telemetry SaaS Server em http://{host}:{port} (debug={debug})")
    app.run(host=host, port=port, debug=debug)
