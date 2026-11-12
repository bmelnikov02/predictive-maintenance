import json
import os
import signal
import time

import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

BROKER_HOST = os.getenv("BROKER_HOST", "localhost")
BROKER_PORT = int(os.getenv("BROKER_PORT", "1883"))
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.environ["INFLUXDB_TOKEN"]
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "factory")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "sensors")

SENSOR_FIELDS = ("temperature", "vibration", "pressure", "rpm")
TOPICS = [("factory/+/sensors", 0), ("factory/+/events", 0)]

influx = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
write_api = influx.write_api(write_options=SYNCHRONOUS)
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
written = 0


def log(message):
    print(message, flush=True)


def wait_for_influxdb():
    while True:
        try:
            if influx.ping():
                log(f"InfluxDB доступна: {INFLUXDB_URL}")
                return
        except Exception:
            pass
        log(f"InfluxDB {INFLUXDB_URL} недоступна, повтор через 3 с")
        time.sleep(3)


def to_point(topic, data):
    machine_id = data["machine_id"]
    if topic.endswith("/sensors"):
        point = Point("sensors").tag("machine_id", machine_id)
        for field in SENSOR_FIELDS:
            point = point.field(field, float(data[field]))
    else:
        point = Point("events").tag("machine_id", machine_id).field("event", data["event"])
    return point.time(data["timestamp"])


def on_connect(client, userdata, flags, reason_code, properties):
    log(f"Подключено к брокеру {BROKER_HOST}:{BROKER_PORT}, подписка на {[t for t, _ in TOPICS]}")
    client.subscribe(TOPICS)


def on_message(client, userdata, message):
    global written
    try:
        data = json.loads(message.payload)
        write_api.write(bucket=INFLUXDB_BUCKET, record=to_point(message.topic, data))
    except Exception as error:
        log(f"Ошибка обработки {message.topic}: {error}")
        return

    written += 1
    if message.topic.endswith("/events"):
        log(f"Записано событие: {data['machine_id']} — {data['event']}")
    elif written % 30 == 0:
        log(f"Записано в InfluxDB: {written} измерений")


def connect_to_broker():
    while True:
        try:
            mqtt_client.connect(BROKER_HOST, BROKER_PORT)
            return
        except OSError as error:
            log(f"Брокер {BROKER_HOST}:{BROKER_PORT} недоступен ({error}), повтор через 3 с")
            time.sleep(3)


def stop(signum, frame):
    mqtt_client.disconnect()


def main():
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    wait_for_influxdb()

    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    connect_to_broker()
    mqtt_client.loop_forever()

    log("Остановка сборщика")
    influx.close()


if __name__ == "__main__":
    main()