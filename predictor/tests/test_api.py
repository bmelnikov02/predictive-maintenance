import os

os.environ["PREDICTION_LOOP"] = "false"

from fastapi.testclient import TestClient

from main import app

NORMAL = {"temperature": 65.0, "vibration": 0.30, "pressure": 5.0, "rpm": 1500}
WORN = {"temperature": 92.0, "vibration": 1.35, "pressure": 5.0, "rpm": 1365}


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_normal_machine_low_risk():
    with TestClient(app) as client:
        result = client.post("/predict", json=NORMAL).json()
    assert result["risk"] == "low"
    assert result["rul_seconds"] > 150
    assert result["failure_probability"] < 0.3


def test_worn_machine_high_risk():
    with TestClient(app) as client:
        result = client.post("/predict", json=WORN).json()
    assert result["risk"] == "high"
    assert result["rul_seconds"] < 60
    assert result["failure_probability"] > 0.7


def test_invalid_input_rejected():
    with TestClient(app) as client:
        response = client.post("/predict", json={"temperature": "горячо"})
    assert response.status_code == 422