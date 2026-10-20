#!/usr/bin/env python3
"""
=============================================================================
FORZA HORIZON 4 / 5 TELEMETRY BRIDGE - APEX TELEMETRY SAAS
=============================================================================
Este script escuta os pacotes UDP nativos transmitidos pelo Forza Horizon 4, 
Forza Horizon 5 ou Forza Motorsport ("Data Out"), decodifica a telemetria 
da física do jogo e despacha via HTTP POST para a sua API Flask em alta taxa.

COMO CONFIGURAR O FORZA HORIZON (PC OU XBOX):
1. No menu do jogo, vá em:
   Opções -> Configurações -> HUD e Jogabilidade (HUD and Gameplay)
2. Role até o final da lista onde estão as opções de telemetria:
   - Data Out: ATIVADO (ON)
   - Data Out IP Address: 127.0.0.1 (ou o IP do seu PC na rede local)
   - Data Out IP Port: 5300
   - Packet Format: "Dash" (padrão)
3. Salve as opções e acelere seu carro no jogo!

COMO RODAR ESTE SCRIPT:
   .\venv\Scripts\python.exe scripts/forza_bridge.py
=============================================================================
"""

import os
import sys
import math
import socket
import struct
import time
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("[ERRO] Instale a biblioteca 'requests': pip install requests")
    sys.exit(1)

# Configurações de Rede e API
UDP_IP = os.getenv("FORZA_UDP_IP", "0.0.0.0")
UDP_PORT = int(os.getenv("FORZA_UDP_PORT", "5300"))
API_URL = os.getenv("TELEMETRY_API_URL", "http://127.0.0.1:5000/api/v1/telemetry")
VEHICLE_ID = os.getenv("FORZA_VEHICLE_ID", "FORZA-PILOT-01")

# Taxa de envio otimizada para latência ultra-baixa: 30 FPS (a cada 33 milissegundos)
MIN_SEND_INTERVAL = float(os.getenv("FORZA_SEND_INTERVAL", "0.033"))


def parse_forza_packet(data: bytes) -> dict:
    """
    Decodifica o formato de pacote binário 'Dash' transmitido pelo Forza (324 ou 311 bytes).
    """
    if len(data) < 232:
        return None

    # Estrutura base de offsets do Forza Data Out
    is_race_on = struct.unpack("<i", data[0:4])[0]
    engine_max_rpm = struct.unpack("<f", data[8:12])[0]
    engine_idle_rpm = struct.unpack("<f", data[12:16])[0]
    current_rpm = struct.unpack("<f", data[16:20])[0]

    # Velocidade em m/s convertida para km/h
    vx = struct.unpack("<f", data[32:36])[0]
    vy = struct.unpack("<f", data[36:40])[0]
    vz = struct.unpack("<f", data[40:44])[0]
    speed_ms = math.sqrt(vx * vx + vy * vy + vz * vz)
    speed_kmh = speed_ms * 3.6

    boost_bar = 0.0
    gear = "1"
    throttle_pct = 0.0

    if len(data) >= 311:
        # Boost em PSI convertido para bar
        try:
            boost_psi = struct.unpack("<f", data[284:288])[0]
            boost_bar = boost_psi * 0.0689476
        except Exception:
            boost_bar = 0.0

        try:
            gear_raw = data[307]
            gear = "R" if gear_raw == 0 else str(gear_raw)
            accel_raw = data[308]
            throttle_pct = (accel_raw / 255.0) * 100.0
        except Exception:
            pass

    return {
        "rpm": round(max(0.0, current_rpm), 0),
        "max_rpm": round(max(1000.0, engine_max_rpm), 0) if engine_max_rpm > 0 else 7500.0,
        "speed_kmh": round(max(0.0, speed_kmh), 1),
        "boost_pressure_bar": round(boost_bar, 2),
        "oil_temp_c": 92.0,  # Forza padrão
        "gear": gear,
        "throttle_pct": round(throttle_pct, 1),
    }


def main():
    print("\n" + "=" * 65)
    print(" 🎮 FORZA HORIZON 4 / 5 TELEMETRY UDP BRIDGE (ULTRA LOW-LATENCY)")
    print("=" * 65)
    print(f" ▶ Escutando UDP em:     {UDP_IP}:{UDP_PORT}")
    print(f" ▶ Encaminhando para:   {API_URL}")
    print(f" ▶ Veículo ID:          {VEHICLE_ID}")
    print(f" ▶ Taxa de Envio:       {1 / MIN_SEND_INTERVAL:.0f} FPS (Intervalo: {MIN_SEND_INTERVAL*1000:.1f}ms)")
    print("=" * 65)
    print(" Aguardando pacotes do jogo (certifique-se de que o Data Out está ativo nas opções do Forza)...\n")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))

    session = requests.Session()
    # Desativa headers de adapter desnecessários para latência máxima
    session.headers.update({"Connection": "keep-alive"})

    last_send_time = 0.0
    packet_count = 0

    try:
        while True:
            data, addr = sock.recvfrom(1024)
            current_time = time.time()

            # Controle de taxa para latência baixa sem inundar o socket
            if current_time - last_send_time < MIN_SEND_INTERVAL:
                continue

            sensors = parse_forza_packet(data)
            if not sensors:
                continue

            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "vehicle_id": VEHICLE_ID,
                    "model": "Forza Horizon Telemetry Vehicle",
                    "ecu_profile": "In-Game Physics Engine",
                },
                "measurements": sensors,
            }

            try:
                resp = session.post(API_URL, json=payload, timeout=0.15)
                if resp.status_code == 201:
                    packet_count += 1
                    last_send_time = current_time
                    redline_info = f"Redline: {sensors.get('max_rpm', 0):.0f}"
                    print(
                        f"\r[FORZA PKT #{packet_count:05d}] "
                        f"Gear: {sensors['gear']} | "
                        f"{sensors['speed_kmh']:5.1f} km/h | "
                        f"{sensors['rpm']:5.0f} RPM ({redline_info}) | "
                        f"Boost: {sensors['boost_pressure_bar']:+4.2f} bar | "
                        f"TPS: {sensors['throttle_pct']:3.0f}% | "
                        f"[201 OK]",
                        end="",
                        flush=True,
                    )
            except Exception:
                pass

    except KeyboardInterrupt:
        print("\n\nBridge do Forza finalizado.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
