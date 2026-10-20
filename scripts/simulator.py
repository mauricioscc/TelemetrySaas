#!/usr/bin/env python3
"""
=============================================================================
MOTOR SIMULATOR - APEX TELEMETRY SAAS
=============================================================================
Simula em tempo real a ECU de um veículo esportivo acelerando em pista.
Gera leituras contínuas de RPM, velocidade, pressão de turbo (boost), 
temperatura de óleo e posição de acelerador, enviando via HTTP POST para a API.

COMO USAR:
    .\venv\Scripts\python.exe scripts/simulator.py

PARÂMETROS CUSTOMIZÁVEIS:
    Você pode alterar as variáveis globais abaixo:
    - API_URL: Endereço da API Flask
    - VEHICLE_ID: Placa / ID único do veículo
    - MODEL: Modelo do veículo
    - ECU_PROFILE: Perfil de calibração / reprogramação
    - TICK_INTERVAL: Intervalo de envio (em segundos, ex: 0.2 = 5 vezes por seg)
=============================================================================
"""

import os
import sys
import time
import math
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("[ERRO] Biblioteca 'requests' não encontrada. Instale com: pip install requests")
    sys.exit(1)

# =============================================================================
# CONFIGURAÇÃO CUSTOMIZÁVEL
# =============================================================================
API_URL = os.getenv("TELEMETRY_API_URL", "http://127.0.0.1:5000/api/v1/telemetry")
VEHICLE_ID = os.getenv("SIM_VEHICLE_ID", "VW-GOLF-R")
MODEL = os.getenv("SIM_MODEL", "Golf R 2.0 TSI MK7.5")
ECU_PROFILE = os.getenv("SIM_ECU_PROFILE", "Stage 2+ (360cv / 48kgfm)")
TICK_INTERVAL = float(os.getenv("SIM_INTERVAL", "0.2"))  # 0.2s = 5 leituras/segundo

# Parâmetros de Motor e Câmbio DSG
IDLE_RPM = 850
REDLINE_RPM = 6500
SHIFT_RPM = 6350
PEAK_BOOST_BAR = 1.85  # Pressão de trabalho da turbina
MIN_BOOST_BAR = -0.70  # Vácuo em marcha lenta / desaceleração

GEAR_RATIOS = {
    1: {"ratio": 3.40, "max_speed": 55},
    2: {"ratio": 2.10, "max_speed": 95},
    3: {"ratio": 1.45, "max_speed": 140},
    4: {"ratio": 1.10, "max_speed": 185},
    5: {"ratio": 0.88, "max_speed": 225},
    6: {"ratio": 0.72, "max_speed": 265},
}


def render_bar(value: float, max_value: float, width: int = 20, fill_char: str = "█") -> str:
    """Renderiza uma barra de progresso visual em texto."""
    ratio = max(0.0, min(1.0, value / max_value))
    filled = int(ratio * width)
    return f"[{fill_char * filled}{'-' * (width - filled)}]"


def run_simulation():
    print("\n" + "=" * 65)
    print(" 🏎️  APEX TELEMETRY SAAS - SIMULADOR VIRTUAL DE MOTOR")
    print("=" * 65)
    print(f" ▶ Veículo:      {VEHICLE_ID} ({MODEL})")
    print(f" ▶ Mapa de ECU:  {ECU_PROFILE}")
    print(f" ▶ Alvo da API:  {API_URL}")
    print(f" ▶ Taxa:         {1 / TICK_INTERVAL:.1f} pacotes/segundo (a cada {TICK_INTERVAL*1000:.0f}ms)")
    print("=" * 65)
    print(" Pressione Ctrl+C para desligar o motor a qualquer momento.\n")

    current_gear = 1
    current_rpm = float(IDLE_RPM)
    current_speed = 0.0
    current_boost = MIN_BOOST_BAR
    oil_temp = 82.0
    accelerating = True
    throttle = 0.0
    packet_counter = 0

    session = requests.Session()

    try:
        while True:
            # 1. Física de aceleração e troca de marcha
            if accelerating:
                throttle = min(100.0, throttle + 15.0)
                # RPM sobe mais rápido em marchas baixas
                rpm_gain = (700.0 / current_gear) * (throttle / 100.0)
                current_rpm += rpm_gain

                # Pressão de turbo cresce conforme a aceleração
                target_boost = PEAK_BOOST_BAR * (throttle / 100.0)
                current_boost += (target_boost - current_boost) * 0.35

                # Velocidade acompanha a marcha e rotação
                max_spd = GEAR_RATIOS[current_gear]["max_speed"]
                speed_ratio = (current_rpm - IDLE_RPM) / (SHIFT_RPM - IDLE_RPM)
                prev_max = GEAR_RATIOS[current_gear - 1]["max_speed"] if current_gear > 1 else 0
                current_speed = prev_max + (max_spd - prev_max) * max(0.0, min(1.0, speed_ratio))

                # Aquecimento gradual do óleo
                oil_temp = min(104.0, oil_temp + 0.05)

                # Troca de marcha ao atingir o ponto de corte (6350 RPM)
                if current_rpm >= SHIFT_RPM:
                    if current_gear < 6:
                        # UP-SHIFT DSG (Alívio de turbo e queda de RPM)
                        current_gear += 1
                        current_rpm = 4100.0
                        current_boost = 0.3  # Alívio da válvula wastegate
                        print(f"   [CÂMBIO] 💨 UP-SHIFT: Engatou {current_gear}ª Marcha!")
                    else:
                        # Atingiu final de reta em 6ª! Inicia desaceleração
                        accelerating = False
                        print("   [PISTA] 🛑 Fim de reta! Freando forte para curva...")
            else:
                # FASE DE FRENAGEM E DESACELERAÇÃO
                throttle = max(0.0, throttle - 25.0)
                current_boost = max(MIN_BOOST_BAR, current_boost - 0.5)
                current_speed = max(25.0, current_speed - 12.0)
                current_rpm = max(1100.0, current_rpm - 600.0)

                # Downshift conforme a velocidade cai
                if current_gear > 2 and current_speed < GEAR_RATIOS[current_gear - 1]["max_speed"] * 0.7:
                    current_gear -= 1
                    current_rpm = 3800.0  # Ponta-taco / rev-matching
                    print(f"   [CÂMBIO] 🔻 DOWN-SHIFT: Reduziu para {current_gear}ª Marcha!")

                if current_speed <= 30.0:
                    current_gear = 1
                    current_rpm = 1200.0
                    accelerating = True
                    print("   [PISTA] 🟢 Saída de curva: Pé no fundo novamente!")

            # 2. Montagem do payload compatível com a Coleção Time-Series
            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "vehicle_id": VEHICLE_ID,
                    "model": MODEL,
                    "ecu_profile": ECU_PROFILE,
                },
                "measurements": {
                    "rpm": round(current_rpm, 0),
                    "speed_kmh": round(current_speed, 1),
                    "boost_pressure_bar": round(current_boost, 2),
                    "oil_temp_c": round(oil_temp, 1),
                    "gear": str(current_gear),
                    "throttle_pct": round(throttle, 1),
                },
            }

            # 3. Envio HTTP POST para a API
            status_text = "ERR"
            try:
                resp = session.post(API_URL, json=payload, timeout=2.0)
                if resp.status_code == 201:
                    status_text = f"HTTP 201 OK"
                    packet_counter += 1
                else:
                    status_text = f"HTTP {resp.status_code}"
            except requests.exceptions.RequestException as err:
                status_text = "CONEXÃO FALHOU"

            # 4. Renderização do cockpit no terminal
            rpm_bar = render_bar(current_rpm, REDLINE_RPM, width=15)
            boost_bar = render_bar(max(0, current_boost), PEAK_BOOST_BAR, width=10)

            print(
                f"\r[{packet_counter:04d}] "
                f"M:{current_gear} | "
                f"{current_speed:5.1f} km/h | "
                f"{current_rpm:5.0f} RPM {rpm_bar} | "
                f"Boost: {current_boost:+4.2f} bar {boost_bar} | "
                f"TPS: {throttle:3.0f}% | "
                f"Óleo: {oil_temp:4.1f}°C | "
                f"[{status_text}]",
                end="",
                flush=True,
            )

            time.sleep(TICK_INTERVAL)

    except KeyboardInterrupt:
        print("\n\n" + "=" * 65)
        print(" 🏁 Motor desligado com sucesso. Total de pacotes enviados:", packet_counter)
        print("=" * 65 + "\n")


if __name__ == "__main__":
    run_simulation()
