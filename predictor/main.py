import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import joblib
from fastapi import FastAPI
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from pydantic import BaseModel

MODEL_PATH = os.getenv("MODEL_PATH", "model.joblib")
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "factory")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "sensors")
PREDICTION_INTERVAL = float(os.getenv("PREDICTION_INTERVAL", "10"))
WINDOW_SECONDS = int(os.getenv("WINDOW_SECONDS", "30"))
PREDICTION_LOOP = os.getenv("PREDICTION_LOOP", "true") == "true"

model = joblib.load(MODEL_PATH)
latest_predictions = {}


class SensorData(BaseModel):
    temperature: float
    vibration: float
    pressure: float
    rpm: float


def log(message):
    print(message, flush=True)


def predict(values):
    x = [[values[name] for name in model["features"]]]
    rul = max(0.0, float(model["regressor"].predict(x)[0]))
    probability = float(model["classifier"].predict_proba(x)[0][1])
    if probability >= 0.7:
        risk = "high"
    elif rul < 150:
        risk = "medium"
    else:
        risk = "low"
    return {"rul_seconds": round(rul, 1), "failure_probability": round(probability, 3), "risk": risk}


def read_window(query_api):
    query = f'''
from(bucket: "{INFLUXDB_BUCKET}")
  |> range(start: -{WINDOW_SECONDS}s)
  |> filter(fn: (r) => r._measurement == "sensors")
  |> group(columns: ["machine_id", "_field"])
  |> mean()
'''
    window = {}
    for table in query_api.query(query):
        for record in table.records:
            window.setdefault(record.values["machine_id"], {})[record.get_field()] = record.get_value()
    return window


def prediction_loop(stop_event):
    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    query_api = client.query_api()
    write_api = client.write_api(write_options=SYNCHRONOUS)
    log(f"Цикл предсказаний запущен: каждые {PREDICTION_INTERVAL:.0f} с, окно {WINDOW_SECONDS} с")

    while not stop_event.is_set():
        try:
            for machine_id, values in sorted(read_window(query_api).items()):
                if any(name not in values for name in model["features"]):
                    continue
                result = predict(values)
                latest_predictions[machine_id] = {**result, "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                point = (
                    Point("predictions")
                    .tag("machine_id", machine_id)
                    .field("rul_seconds", result["rul_seconds"])
                    .field("failure_probability", result["failure_probability"])
                )
                write_api.write(bucket=INFLUXDB_BUCKET, record=point)
                log(f"{machine_id}: ресурс {result['rul_seconds']:.0f} с, "
                    f"вероятность поломки {result['failure_probability']:.0%}, риск {result['risk']}")
        except Exception as error:
            log(f"Ошибка цикла предсказаний: {error}")
        stop_event.wait(PREDICTION_INTERVAL)

    client.close()


@asynccontextmanager
async def lifespan(app):
    stop_event = threading.Event()
    thread = None
    if PREDICTION_LOOP:
        thread = threading.Thread(target=prediction_loop, args=(stop_event,), daemon=True)
        thread.start()
    yield
    stop_event.set()
    if thread:
        thread.join(timeout=5)


app = FastAPI(title="Predictive Maintenance API", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/predict")
def predict_endpoint(data: SensorData):
    return predict(data.model_dump())


@app.get("/predictions")
def predictions():
    return latest_predictions