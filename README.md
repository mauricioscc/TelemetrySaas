# Telemetria Automotiva SaaS (MVP)

API de alta performance para ingestão, processamento e análise de telemetria automotiva em tempo real (RPM, velocidade, pressão do turbo, temperatura de óleo), utilizando **Python 3**, **Flask** e coleções nativas de **Séries Temporais (Time-Series) no MongoDB**.

---

## 📁 Estrutura do Projeto

```text
TelemetrySaas/
│
├── app/
│   ├── __init__.py          # Application Factory (create_app), handlers de erro e registro de Blueprints
│   ├── config.py            # Classes de configuração por ambiente (Dev, Prod, Test)
│   ├── controllers/         # Endpoints da API (Blueprints)
│   │   ├── __init__.py
│   │   └── health_ctrl.py   # Health check e status geral da API
│   ├── services/            # Camada de lógica de negócio e validações
│   │   └── __init__.py
│   └── repositories/        # Camada de persistência e acesso exclusivo ao MongoDB
│       ├── __init__.py
│       └── mongo_client.py  # Conexão resiliente e verificação de integridade do MongoDB
│
├── tests/                   # Testes automatizados (pytest)
│   ├── __init__.py
│   └── test_health.py       # Testes do health check e tratamento de erros
│
├── .env.example             # Modelo das variáveis de ambiente
├── .env                     # Variáveis de ambiente locais
├── .gitignore
├── requirements.txt         # Dependências do projeto
├── run.py                   # Ponto de entrada da aplicação
└── README.md
```

---

## 🚀 Como Executar

### 1. Pré-requisitos
- Python 3.10+ (instalado Python 3.12)
- MongoDB 5.0+ (suporte a Time-Series collections) ou MongoDB Atlas

### 2. Ambiente Virtual
O ambiente virtual já se encontra criado na pasta `venv`. Para ativá-lo manualmente:

**No Windows (PowerShell):**
```powershell
.\venv\Scripts\Activate.ps1
```

**No Linux/macOS:**
```bash
source venv/bin/activate
```

### 3. Instalar Dependências (se necessário)
```bash
pip install -r requirements.txt
```

### 4. Executar a Aplicação
```bash
python run.py
```
A API estará disponível em: [http://127.0.0.1:5000](http://127.0.0.1:5000)

---

## 🔍 Endpoints Iniciais

### Informações da API
- **GET `/`**
```json
{
  "documentation": "/api/v1/health",
  "service": "Automotive Telemetry SaaS API",
  "status": "online",
  "timestamp": "2026-10-20T15:52:00.000000+00:00",
  "version": "1.0.0"
}
```

### Health Check
- **GET `/api/v1/health`** (inclui ping do MongoDB)
- **GET `/api/v1/health?db=false`** (apenas verificação do container Flask)

```json
{
  "database": {
    "database": "telemetry_saas",
    "message": "Conexão com o MongoDB estabelecida com sucesso.",
    "status": "connected"
  },
  "environment": "development",
  "status": "healthy",
  "timestamp": "2026-10-20T15:52:00.000000+00:00",
  "version": "1.0.0"
}
```

---

## 🧪 Executando os Testes

Para rodar os testes unitários e de integração com `pytest`:

```powershell
.\venv\Scripts\pytest.exe -v
```

---

## 🛣️ Próximos Passos
1. **Configuração da Coleção Time-Series no MongoDB**: script/rotina para criar `vehicle_telemetry` com `timeField: timestamp`, `metaField: metadata` e granularidade em segundos.
2. **Camada de Repositório (`mongo_repo.py`)**: métodos para inserção em lote (`insert_many`) e inserção individual otimizada.
3. **Camada de Serviço (`telemetry_svc.py`)**: validação de esquemas (JSON Schema / Pydantic ou validação manual com exceções customizadas) para payloads de ECU.
4. **Endpoint de Ingestão (`ingest_ctrl.py`)**: rota `POST /api/v1/telemetry` com tratamento de concorrência e retorno rápido.
5. **Script Simulador (`simulator.py`)**: gerador assíncrono de telemetria simulando múltiplos veículos em tempo real (Stage 1, Stage 2, Stock).
