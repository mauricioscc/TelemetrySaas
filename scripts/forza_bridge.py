#!/usr/bin/env python3
"""
=============================================================================
FORZA HORIZON 4 / 5 TELEMETRY BRIDGE - FUELTECH EDITION (ULTRA LOW-LATENCY)
=============================================================================
Escuta os pacotes UDP nativos do Forza Horizon 4/5 ("Data Out"), extrai a telemetria 
completa da física (RPM, Redline, Velocidade, Turbo, CV de Potência, Torque, Força G, 
Acelerador e Freio) e despacha via HTTP POST para a API com latência imperceptível.

COMO CONFIGURAR O FORZA HORIZON:
1. No menu do jogo: Opções -> Configurações -> HUD e Jogabilidade
2. Data Out: ATIVADO (ON)
3. Data Out IP: 127.0.0.1 (ou IP do PC na rede local)
4. Data Out Porta: 5300
5. Formato: "Dash"

RODAR:
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

UDP_IP = os.getenv("FORZA_UDP_IP", "0.0.0.0")
UDP_PORT = int(os.getenv("FORZA_UDP_PORT", "5300"))
API_URL = os.getenv("TELEMETRY_API_URL", "http://127.0.0.1:5000/api/v1/telemetry")
VEHICLE_ID = os.getenv("FORZA_VEHICLE_ID", "FORZA-PILOT-01")

# Taxa de atualização: 30 FPS (33ms) para fluidez máxima
MIN_SEND_INTERVAL = float(os.getenv("FORZA_SEND_INTERVAL", "0.033"))


def parse_forza_packet(data: bytes) -> dict:
    """
    Decodifica o formato de pacote binário 'Dash' transmitido pelo Forza (324 ou 311 bytes).
    """
    if len(data) < 232:
        return None

    # 1. Rotação do Motor
    engine_max_rpm = struct.unpack("<f", data[8:12])[0]
    engine_idle_rpm = struct.unpack("<f", data[12:16])[0]
    current_rpm = struct.unpack("<f", data[16:20])[0]

    # 2. Forças G e Aceleração
    ax = struct.unpack("<f", data[20:24])[0]
    ay = struct.unpack("<f", data[24:28])[0]
    az = struct.unpack("<f", data[28:32])[0]
    g_force_lat = ax / 9.80665

    # 3. Velocidade em m/s -> km/h
    vx = struct.unpack("<f", data[32:36])[0]
    vy = struct.unpack("<f", data[36:40])[0]
    vz = struct.unpack("<f", data[40:44])[0]
    speed_ms = math.sqrt(vx * vx + vy * vy + vz * vz)
    speed_kmh = speed_ms * 3.6

    # 4. Potência (Watts -> CV) e Torque (Nm)
    power_hp = 0.0
    torque_nm = 0.0
    boost_bar = 0.0
    gear = "N"
    throttle_pct = 0.0
    brake_pct = 0.0

    if len(data) >= 288:
        try:
            power_watts = struct.unpack("<f", data[260:264])[0]
            torque_val = struct.unpack("<f", data[264:268])[0]
            power_hp = max(0.0, power_watts / 735.49875)
            torque_nm = max(0.0, torque_val)
        except Exception:
            pass

        try:
            boost_psi = struct.unpack("<f", data[284:288])[0]
            boost_bar = boost_psi * 0.0689476
        except Exception:
            boost_bar = 0.0

    if len(data) >= 311:
        # Tenta layout padrão V2 (324 bytes) e fallback para V1 (311 bytes)
        try:
            if len(data) >= 324:
                accel_raw = data[315]
                brake_raw = data[316]
                gear_raw = data[319]
            else:
                gear_raw = data[307]
                accel_raw = data[308]
                brake_raw = data[309]

            gear = "R" if gear_raw == 0 else str(gear_raw)
            throttle_pct = (accel_raw / 255.0) * 100.0
            brake_pct = (brake_raw / 255.0) * 100.0
        except Exception:
            pass

    return {
        "rpm": round(max(0.0, current_rpm), 0),
        "max_rpm": round(max(2000.0, engine_max_rpm), 0) if engine_max_rpm > 0 else 8000.0,
        "speed_kmh": round(max(0.0, speed_kmh), 1),
        "boost_pressure_bar": round(boost_bar, 2),
        "oil_temp_c": 92.0,
        "gear": gear,
        "throttle_pct": round(throttle_pct, 1),
        "brake_pct": round(brake_pct, 1),
        "power_hp": round(power_hp, 0),
        "torque_nm": round(torque_nm, 1),
        "g_force_lat": round(g_force_lat, 2),
    }


def main():
    print("\n" + "=" * 68)
    print(" 🏁 FORZA HORIZON 4 / 5 -> FUELTECH TELEMETRY BRIDGE")
    print("=" * 68)
    print(f" ▶ Escuta UDP:    {UDP_IP}:{UDP_PORT}")
    print(f" ▶ API Destino:  {API_URL}")
    print(f" ▶ Taxa:         {1 / MIN_SEND_INTERVAL:.0f} FPS (Intervalo: {MIN_SEND_INTERVAL*1000:.0f}ms)")
    print("=" * 68)
    print(" Aguardando pacotes do jogo (certifique-se de que o Data Out está ligado no Forza)...\n")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))

    session = requests.Session()
    session.headers.update({"Connection": "keep-alive"})

    last_send_time = 0.0
    packet_count = 0

    try:
        while True:
            data, addr = sock.recvfrom(1024)
            current_time = time.time()

            if current_time - last_send_time < MIN_SEND_INTERVAL:
                continue

            sensors = parse_forza_packet(data)
            if not sensors:
                continue

            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "vehicle_id": VEHICLE_ID,
                    "model": "Forza Telemetry Vehicle",
                    "ecu_profile": "FuelTech FT-Dash Sync",
                },
                "measurements": sensors,
            }

            try:
                resp = session.post(API_URL, json=payload, timeout=0.1)
                if resp.status_code == 201:
                    packet_count += 1
                    last_send_time = current_time
                    redline = sensors.get('max_rpm', 8000)
                    print(
                        f"\r[FT PKT #{packet_count:05d}] "
                        f"G:{sensors['gear']} | "
                        f"{sensors['speed_kmh']:5.1f} km/h | "
                        f"{sensors['rpm']:5.0f}/{redline:.0f} RPM | "
                        f"MAP: {sensors['boost_pressure_bar']:+4.2f} bar | "
                        f"{sensors['power_hp']:4.0f} CV | "
                        f"TPS: {sensors['throttle_pct']:3.0f}% | "
                        f"BRK: {sensors['brake_pct']:3.0f}% | "
                        f"[201 OK]",
                        end="",
                        flush=True,
                    )
            except Exception:
                pass

    except KeyboardInterrupt:
        print("\n\nBridge finalizada.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
