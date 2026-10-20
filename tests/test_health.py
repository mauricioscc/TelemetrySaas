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


def test_health_check_default(client):
    """
    Testa se o health check responde 200 mesmo se o MongoDB estiver desconectado,
    marcando o status como degraded sem lançar exceção não tratada.
    """
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] in ("healthy", "degraded")
    assert "database" in data
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
