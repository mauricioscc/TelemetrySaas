import pytest
from app import create_app
from app.repositories.mongo_client import mongo_client


@pytest.fixture
def app():
    app = create_app("testing")
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def test_dashboard_route_returns_html(client):
    """Verifica se a rota /dashboard renderiza o cluster de instrumentos visual."""
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "text/html" in response.content_type
    assert b"Apex Telemetry SaaS" in response.data
    assert b"Tachometer" in response.data
    assert b"Boost Pressure" in response.data


def test_ft600_dashboard_route_returns_separate_html(client):
    response = client.get("/dashboard/ft600")
    assert response.status_code == 200
    assert "text/html" in response.content_type
    assert b"FT600" in response.data
    assert b"TELEMETRIA" in response.data
    assert b"11000" in response.data
    assert b'id="fullscreenButton"' in response.data
    assert b'id="shiftToneButton"' in response.data
    assert b'id="vehicleSelect"' not in response.data
    assert b"LIMITER_BEEP_INTERVAL_MS = 80" in response.data
    assert b"const SHIFT_WARNING_RATIO = 0.95" in response.data
    assert b"const LIMITER_RATIO =" in response.data
    assert b"(rpm / limit) * 100" in response.data
    assert b'aria-valuemax", String(Math.round(limit))' in response.data
    assert b"50 - clamp(lateralG" in response.data
    assert b"50 + clamp(longitudinalG" in response.data


def test_sanitize_measurements_preserves_longitudinal_g_force():
    from app.services.telemetry_svc import telemetry_service

    clean = telemetry_service._sanitize_measurements(
        {
            "rpm": 3500,
            "speed_kmh": 80,
            "boost_pressure_bar": 0.5,
            "oil_temp_c": 92,
            "g_force_lat": 0.42,
            "g_force_long": -0.18,
        },
        "",
    )

    assert clean["g_force_lat"] == 0.42
    assert clean["g_force_long"] == -0.18


def test_ingest_single_valid_telemetry(client):
    """Verifica o endpoint POST /api/v1/telemetry para payload único."""
    payload = {
        "timestamp": "2026-10-20T19:00:00Z",
        "metadata": {
            "vehicle_id": "TEST-GOLF-01",
            "model": "Golf R",
            "ecu_profile": "Stage 2",
        },
        "measurements": {
            "rpm": 5200,
            "speed_kmh": 120.5,
            "boost_pressure_bar": 1.45,
            "oil_temp_c": 95.0,
            "gear": "3",
            "throttle_pct": 85.0,
        },
    }

    # Se o MongoDB estiver conectado nos testes, insere e valida 201
    db_health = mongo_client.check_health()
    response = client.post("/api/v1/telemetry", json=payload)

    if db_health.get("status") == "connected":
        assert response.status_code == 201
        data = response.get_json()
        assert data["status"] == "success"
        assert data["vehicle_id"] == "TEST-GOLF-01"
    else:
        # Se banco não estiver configurado para testing, retorna 500 tratado graciosamente
        assert response.status_code in (201, 500)


def test_ingest_batch_valid_telemetry(client):
    """Verifica o endpoint POST /api/v1/telemetry para ingestão em lote (batch)."""
    payload = [
        {
            "metadata": {"vehicle_id": "TEST-BATCH-01"},
            "measurements": {"rpm": 2000, "speed_kmh": 30, "boost_pressure_bar": 0.1, "oil_temp_c": 85},
        },
        {
            "metadata": {"vehicle_id": "TEST-BATCH-01"},
            "measurements": {"rpm": 3500, "speed_kmh": 65, "boost_pressure_bar": 0.8, "oil_temp_c": 86},
        },
    ]

    db_health = mongo_client.check_health()
    response = client.post("/api/v1/telemetry", json=payload)

    if db_health.get("status") == "connected":
        assert response.status_code == 201
        data = response.get_json()
        assert data["status"] == "success"
        assert data["mode"] == "batch"
        assert data["count"] == 2
    else:
        assert response.status_code in (201, 500)


def test_ingest_invalid_payload_validation(client):
    """Garante que payloads sem metadata ou com dados corrompidos são rejeitados com 400 ou 422."""
    # Payload vazio
    resp_empty = client.post("/api/v1/telemetry", json={})
    assert resp_empty.status_code in (400, 422)

    # Payload sem vehicle_id
    resp_no_veh = client.post("/api/v1/telemetry", json={"metadata": {}, "measurements": {"rpm": 1000}})
    assert resp_no_veh.status_code in (400, 422)

    # Payload com RPM impossível (fora dos limites de segurança)
    resp_bad_rpm = client.post("/api/v1/telemetry", json={
        "metadata": {"vehicle_id": "VW-01"},
        "measurements": {"rpm": 999999, "speed_kmh": 100, "boost_pressure_bar": 1.0, "oil_temp_c": 90}
    })
    assert resp_bad_rpm.status_code == 422


def test_ingest_with_max_rpm_and_gear(client):
    """Garante suporte a campos avançados como max_rpm para cálculo dinâmico de redline."""
    payload = {
        "metadata": {"vehicle_id": "FORZA-TEST-01", "model": "Porsche 911 GT3"},
        "measurements": {
            "rpm": 8500,
            "max_rpm": 9000,
            "speed_kmh": 240.0,
            "boost_pressure_bar": 0.0,
            "oil_temp_c": 92.0,
            "gear": "5",
        },
    }
    db_health = mongo_client.check_health()
    response = client.post("/api/v1/telemetry", json=payload)
    if db_health.get("status") == "connected":
        assert response.status_code == 201


def test_telemetry_stream_endpoint(app):
    """Verifica se o endpoint /api/v1/telemetry/stream expõe headers corretos de SSE e inicia o gerador."""
    with app.test_request_context("/api/v1/telemetry/stream"):
        from app.controllers.ingest_ctrl import stream_telemetry
        response = stream_telemetry()
        assert response.status_code == 200
        assert "text/event-stream" in response.content_type
        gen = response.response
        first_chunk = next(gen)
        assert isinstance(first_chunk, (str, bytes))
        gen.close()
