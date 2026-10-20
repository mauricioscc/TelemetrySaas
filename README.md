# 🏎️ Apex Telemetry SaaS — Telemetria Automotiva em Alta Frequência

API e Cockpit de alta performance para ingestão, análise e monitoramento de telemetria automotiva em tempo real (RPM, velocidade, pressão de turbo, temperatura de óleo, marcha e aceleração), utilizando **Python 3**, **Flask**, **Streaming SSE (Latência Zero)**, **Síntese de Áudio Web (Shift Tone)** e **MongoDB Time-Series Collections**.

Suporta simulação nativa de motor (Golf R 2.0 TSI Stage 2) e **integração direta via UDP com Forza Horizon 4 / 5**.

---

## 🏗️ Arquitetura do Sistema

```
  ┌───────────────────────────────┐
  │     Forza Horizon 4 / 5       │  (ou Simulador Python: scripts/simulator.py)
  │ (Data Out UDP - Porta 5300)   │
  └──────────────┬────────────────┘
                 │ Pacotes UDP Binários (30 FPS)
                 ▼
  ┌───────────────────────────────┐
  │     scripts/forza_bridge.py   │  (Decodifica structs binárias)
  └──────────────┬────────────────┘
                 │ HTTP POST /api/v1/telemetry (< 20ms)
                 ▼
  ┌────────────────────────────────────────────────────────┐
  │                    API Flask (Backend)                 │
  │  ├── telemetry_svc.py (Validação física e sanitização) │
  │  └── In-Memory Broadcast Queue                         │
  └──────────────┬────────────────────────┬────────────────┘
                 │                        │
      Streaming SSE (Instantâneo)         │ Persistência Assíncrona
                 ▼                        ▼
  ┌──────────────────────────────┐ ┌──────────────────────────────┐
  │     Cockpit Web (Navegador)  │ │   MongoDB Atlas (Cloud)      │
  │   - Mostradores de RPM/Turbo │ │ - Time-Series Collection     │
  │   - F1 Shift Lights          │ │ - Granularity: seconds       │
  │   - Shift Tone (Beep F1)     │ │ - Compactação Temporal BSON  │
  │   - Gráficos a 60 FPS        │ └──────────────────────────────┘
  └──────────────────────────────┘
```

---

## 📁 Estrutura de Diretórios

```text
TelemetrySaas/
│
├── app/
│   ├── __init__.py               # Application Factory (create_app), handlers de erro globais
│   ├── config.py                 # Configurações de ambientes (Dev, Prod, Test) e MongoDB
│   │
│   ├── controllers/              # Endpoints HTTP da Aplicação (Flask Blueprints)
│   │   ├── health_ctrl.py        # GET / e GET /api/v1/health (ping do MongoDB)
│   │   ├── ingest_ctrl.py        # POST /api/v1/telemetry, GET /stream, /latest, /history, /stats
│   │   └── dashboard_ctrl.py     # GET /dashboard (renderiza o cockpit web)
│   │
│   ├── services/
│   │   └── telemetry_svc.py      # Validação física de sensores, Pub/Sub em memória para streaming
│   │
│   ├── repositories/
│   │   ├── mongo_client.py       # Gerenciador resiliente de conexão MongoDB com lazy-connect
│   │   └── telemetry_repo.py     # Criação de Time-Series nativas e agregações analíticas
│   │
│   └── templates/
│       └── dashboard.html        # Cockpit visual esportivo com SVG Gauges e Web Audio
│
├── scripts/
│   ├── simulator.py              # Simulador de Motor Virtual (Golf R MK7.5 2.0 TSI DSG)
│   └── forza_bridge.py           # Conector UDP de telemetria para Forza Horizon 4 / 5
│
├── tests/                        # Bateria completa de testes automatizados (pytest)
│   ├── test_health.py            # Testes de disponibilidade e resiliência
│   └── test_telemetry.py         # Testes de ingestão unitária, batch, streaming e regras de negócio
│
├── .env                          # Variáveis de ambiente locais (URI do MongoDB Atlas, etc.)
├── .env.example                  # Modelo de variáveis de ambiente
├── requirements.txt              # Dependências do projeto (Flask, pymongo, requests, pytest)
├── run.py                        # Ponto de entrada do servidor de desenvolvimento
└── README.md
```

---

## ⚡ Por que Time-Series e Streaming de Latência Zero?

1. **MongoDB Time-Series Collections:**
   * Em vez de salvar cada leitura de sensor como um documento solto (o que incha o banco com milhões de linhas), o MongoDB agrupa as leituras em **buckets temporais comprimidos** por veículo (`granularity: "seconds"`).
   * Reduz o uso de disco em até 80% e viabiliza queries analíticas (picos de velocidade, médias de RPM) em milissegundos.

2. **Server-Sent Events (SSE) vs Polling Tradicional:**
   * **Antes (Polling):** O navegador perguntava repetidamente a cada 350ms, gerando tráfego desnecessário e atraso visível.
   * **Agora (SSE):** O navegador mantém uma conexão aberta em `/api/v1/telemetry/stream`. O script do Forza envia o pacote para a API e, **no mesmo milissegundo**, o servidor empurra o dado diretamente para o painel web. Latência imperceptível (< 15ms).

3. **Alerta Sonoro de Troca de Marcha (Shift Tone):**
   * Sintetizador sonoro integrado via **Web Audio API** (`AudioContext`).
   * Lê a rotação máxima (`max_rpm`) transmitida pela física do jogo ou simulador.
   * Quando o motor atinge **92% do limite de giro**, o painel pisca os **Shift Lights F1** e emite um bipe agudo esportivo (1450 Hz) avisando o piloto para trocar de marcha!

---

## 🚀 Como Executar

### 1. Iniciar o Servidor Flask
No PowerShell dentro do diretório do projeto:
```powershell
.\venv\Scripts\python.exe run.py
```
O servidor estará rodando em: **`http://127.0.0.1:5000`**

### 2. Abrir o Cockpit no Navegador
Acesse no Chrome ou Edge:
👉 **[http://127.0.0.1:5000/dashboard](http://127.0.0.1:5000/dashboard)**

* Clique em **"🔇 SHIFT TONE"** no topo da página para ativar o bipe sonoro de troca de marcha.
* Você pode alternar os carros visualizados no seletor **"Veículo"**.

---

## 🏎️ Como Gerar Dados de Telemetria

Você tem duas formas de alimentar a telemetria:

### Opção A: Simulador de Motor Virtual (Python)
Em um segundo terminal, rode:
```powershell
.\venv\Scripts\python.exe scripts/simulator.py
```
* Simula um **Golf R 2.0 TSI MK7.5 Stage 2+** acelerando de 0 a 265 km/h, trocando marchas de 1ª a 6ª e aliviando a turbina nas reduções de curva.

---

### Opção B: Forza Horizon 4 / 5 (PC ou Xbox)
1. No menu do Forza, vá em **Opções -> Configurações -> HUD e Jogabilidade**:
   * **Data Out:** `Ativado (ON)`
   * **Data Out IP Address:** `127.0.0.1` *(ou o IP da sua máquina se jogar no Xbox)*
   * **Data Out IP Port:** `5300`
   * **Packet Format:** `Dash`
2. No terminal, execute a bridge UDP otimizada (30 FPS):
   ```powershell
   .\venv\Scripts\python.exe scripts/forza_bridge.py
   ```
3. Acelere qualquer carro no jogo e veja o painel no navegador acompanhar seus giros, trocas de marcha e pressão de turbo ao vivo!

---

## 📡 Referência dos Endpoints da API

| Método | Rota | Descrição |
| :---: | :--- | :--- |
| `GET` | `/` | Metadados do SaaS e links rápidos. |
| `GET` | `/dashboard` | Cockpit visual completo com gauges e áudio. |
| `GET` | `/api/v1/health` | Health check da aplicação e ping de integridade do MongoDB Atlas. |
| `POST` | `/api/v1/telemetry` | Ingestão de telemetria individual ou em lote (batch de até 1.000 itens). |
| `GET` | `/api/v1/telemetry/stream` | Stream SSE em tempo real com latência zero (`text/event-stream`). |
| `GET` | `/api/v1/telemetry/latest` | Retorna o pacote mais recente (`?vehicle_id=...`). |
| `GET` | `/api/v1/telemetry/history` | Retorna os últimos N pacotes ordenados para gráficos (`?limit=60`). |
| `GET` | `/api/v1/telemetry/vehicles` | Lista todos os veículos registrados no banco de dados. |
| `GET` | `/api/v1/telemetry/stats/<id>` | Retorna agregação analítica: Top Speed, Pico de RPM, Max Boost e Amostras. |

### Exemplo de Payload JSON (`POST /api/v1/telemetry`):

```json
{
  "timestamp": "2026-10-20T19:30:00.000Z",
  "metadata": {
    "vehicle_id": "FORZA-PILOT-01",
    "model": "Porsche 911 GT3 RS",
    "ecu_profile": "FuelTech FT-Dash Sync"
  },
  "measurements": {
    "rpm": 8750,
    "max_rpm": 9000,
    "speed_kmh": 242.5,
    "boost_pressure_bar": 0.0,
    "oil_temp_c": 94.0,
    "gear": "5",
    "throttle_pct": 100.0,
    "brake_pct": 0.0,
    "power_hp": 525.0,
    "torque_nm": 465.0,
    "g_force_lat": 1.35
  }
}
```

---

## 🧪 Bateria de Testes Automatizados

O projeto conta com suíte de testes com **100% de aprovação** cobrindo contratos HTTP, validações de limites físicos e streaming SSE:

```powershell
.\venv\Scripts\pytest.exe -v
```

```text
tests/test_health.py::test_index_route PASSED
tests/test_health.py::test_health_check_without_db PASSED
tests/test_health.py::test_health_check_default PASSED
tests/test_health.py::test_404_error_handler PASSED
tests/test_health.py::test_405_error_handler PASSED
tests/test_telemetry.py::test_dashboard_route_returns_html PASSED
tests/test_telemetry.py::test_ingest_single_valid_telemetry PASSED
tests/test_telemetry.py::test_ingest_batch_valid_telemetry PASSED
tests/test_telemetry.py::test_ingest_invalid_payload_validation PASSED
tests/test_telemetry.py::test_ingest_with_max_rpm_and_gear PASSED
tests/test_telemetry.py::test_telemetry_stream_endpoint PASSED
============================= 11 passed in 3.10s ==============================
```

---

## 🛠️ Tecnologias Utilizadas

* **Backend:** Python 3.12, Flask 3, PyMongo 4, Requests, Python-Dotenv
* **Banco de Dados:** MongoDB Atlas (Time-Series Collections)
* **Frontend:** HTML5, Vanilla CSS (Dark Automotive Theme, Glassmorphism, CSS Transitions), Vanilla JS (Web Audio API, SSE EventSource, Canvas API)
* **Qualidade de Software:** Pytest 8, Arquitetura em Camadas (Application Factory, Blueprints, Services, Repositories)
* **Integrações:** Sockets UDP nativos para telemetria de simuladores e jogos (Forza Data Out)
