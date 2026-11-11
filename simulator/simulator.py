import json
import os
import random
import signal
import sys
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

BROKER_HOST = os.getenv("BROKER_HOST", "localhost")
BROKER_PORT = int(os.getenv("BROKER_PORT", "1883"))
MACHINES = os.getenv("MACHINES", "machine1,machine2,machine3").split(",")
DEGRADING_MACHINE = os.getenv("DEGRADING_MACHINE", "machine3")
INTERVAL = float(os.getenv("INTERVAL", "1"))
LIFETIME = float(os.getenv("LIFETIME", "300"))

NORMAL = {
    "temperature": (65.0, 0.8),
    "vibration": (0.30, 0.02),
    "pressure": (5.0, 0.1),
    "rpm": (1500.0, 10.0),
}

running = True


def stop(signum, frame):
    global running
    running = False


signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)


def log(message):
    print(message, flush=True)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_sensors(machine_id, wear):
    values = {name: random.gauss(base, noise) for name, (base, noise) in NORMAL.items()}

    w = wear ** 2
    values["temperature"] += 30 * w
    values["vibration"] += 1.2 * w
    values["rpm"] -= 150 * w

    return {
        "machine_id": machine_id,
        "timestamp": now(),
        "temperature": round(values["temperature"], 2),
        "vibration": round(values["vibration"], 3),
        "pressure": round(values["pressure"], 2),
        "rpm": round(values["rpm"]),
    }


def connect():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    while running:
        try:
            client.connect(BROKER_HOST, BROKER_PORT)
            log(f"Подключено к брокеру {BROKER_HOST}:{BROKER_PORT}")
            return client
        except OSError as error:
            log(f"Брокер {BROKER_HOST}:{BROKER_PORT} недоступен ({error}), повтор через 3 с")
            time.sleep(3)
    sys.exit(0)


def main():
    client = connect()
    client.loop_start()

    wear = 0.0
    wear_step = INTERVAL / LIFETIME

    while running:
        for machine_id in MACHINES:
            machine_wear = wear if machine_id == DEGRADING_MACHINE else 0.0
            data = read_sensors(machine_id, machine_wear)
            client.publish(f"factory/{machine_id}/sensors", json.dumps(data))
            if machine_id == DEGRADING_MACHINE:
                log(f"{machine_id}: износ {wear:.0%}, t={data['temperature']} °C, "
                    f"вибрация={data['vibration']}, обороты={data['rpm']}")

        wear += wear_step
        if wear >= 1.0:
            log(f"!!! ПОЛОМКА {DEGRADING_MACHINE}. Ремонт, износ сброшен")
            event = {"machine_id": DEGRADING_MACHINE, "timestamp": now(), "event": "failure"}
            client.publish(f"factory/{DEGRADING_MACHINE}/events", json.dumps(event))
            wear = 0.0

        time.sleep(INTERVAL)

    log("Остановка симулятора")
    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    main()