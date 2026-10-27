import pytest
from app import create_app


@pytest.fixture
def client():
    """Cria um cliente de teste da aplicação Flask em modo de teste."""
    app = create_app("testing")
    with app.test_client() as client:
        yield client


def test_index_route(client):
    """Testa se a rota raiz (/) responde 200 e com metadados da API."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.get_json()
    assert data["service"] == "Automotive Telemetry SaaS API"
    assert data["status"] == "online"
    assert "version" in data
    assert "timestamp" in data


def test_health_check_without_db(client):
    """Testa se o health check responde saudável quando db=false."""
    response = client.get("/api/v1/health?db=false")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["version"] == "1.0.0"
    assert "database" not in data


def test_memory_mode_does_not_initialize_mongodb(monkeypatch):
    from app import create_app
    from app.repositories.mongo_client import mongo_client

    def fail_if_database_is_initialized(*args, **kwargs):
        raise AssertionError("O modo memória não deve inicializar MongoDB.")

    monkeypatch.setattr(mongo_client, "init_app", fail_if_database_is_initialized)
    app = create_app("testing")

    assert app.config["TELEMETRY_STORAGE"] == "memory"


def test_health_check_default(client, monkeypatch):
    """O health check informa que o armazenamento em memória não depende do MongoDB."""
    def fail_if_database_is_checked():
        raise AssertionError("O health check não deve consultar MongoDB no modo memória.")

    from app.repositories.mongo_client import mongo_client
    monkeypatch.setattr(mongo_client, "check_health", fail_if_database_is_checked)

    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["storage"] == "memory"
    assert data["database"]["status"] == "disabled"
    assert "timestamp" in data


def test_404_error_handler(client):
    """Testa se rotas inexistentes retornam payload JSON padronizado com status 404."""
    response = client.get("/api/v1/rota-inexistente")
    assert response.status_code == 404
    data = response.get_json()
    assert data["status_code"] == 404
    assert data["error"] == "Not Found"


def test_405_error_handler(client):
    """Testa se métodos não permitidos retornam payload JSON padronizado com status 405."""
    response = client.post("/")
    assert response.status_code == 405
    data = response.get_json()
    assert data["status_code"] == 405
    assert data["error"] == "Method Not Allowed"
