import random

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import accuracy_score, mean_absolute_error

LIFETIME = 300
WINDOW = 30
WARNING_HORIZON = 60
TRAIN_CYCLES = 32
TEST_CYCLES = 8
HEALTHY_WINDOWS = 400
FEATURES = ["temperature", "vibration", "pressure", "rpm"]

NORMAL = {
    "temperature": (65.0, 0.8),
    "vibration": (0.30, 0.02),
    "pressure": (5.0, 0.1),
    "rpm": (1500.0, 10.0),
}

random.seed(42)


def reading(wear):
    values = {name: random.gauss(base, noise) for name, (base, noise) in NORMAL.items()}
    w = wear ** 2
    values["temperature"] += 30 * w
    values["vibration"] += 1.2 * w
    values["rpm"] -= 150 * w
    return [values[name] for name in FEATURES]


def build_dataset(cycles):
    features, rul = [], []

    for _ in range(cycles):
        readings = [reading(t / LIFETIME) for t in range(LIFETIME)]
        for end in range(WINDOW, LIFETIME + 1):
            features.append(np.mean(readings[end - WINDOW:end], axis=0))
            rul.append(LIFETIME - end)

    for _ in range(HEALTHY_WINDOWS * cycles // 10):
        features.append(np.mean([reading(0.0) for _ in range(WINDOW)], axis=0))
        rul.append(LIFETIME)

    features = np.array(features)
    rul = np.array(rul, dtype=float)
    soon = (rul <= WARNING_HORIZON).astype(int)
    return features, rul, soon


def main():
    x_train, rul_train, soon_train = build_dataset(TRAIN_CYCLES)
    x_test, rul_test, soon_test = build_dataset(TEST_CYCLES)

    regressor = RandomForestRegressor(n_estimators=100, max_depth=12, random_state=42, n_jobs=-1)
    regressor.fit(x_train, rul_train)

    classifier = RandomForestClassifier(n_estimators=100, max_depth=12, random_state=42, n_jobs=-1)
    classifier.fit(x_train, soon_train)

    predicted_rul = regressor.predict(x_test)
    near_failure = rul_test <= 120
    mae = mean_absolute_error(rul_test, predicted_rul)
    mae_near = mean_absolute_error(rul_test[near_failure], predicted_rul[near_failure])
    accuracy = accuracy_score(soon_test, classifier.predict(x_test))
    print(f"Обучающая выборка: циклов износа — {TRAIN_CYCLES}, окон — {len(x_train)}")
    print(f"Проверочная выборка: новых циклов — {TEST_CYCLES}, окон — {len(x_test)}")
    print(f"Средняя ошибка прогноза ресурса (MAE): {mae:.1f} с")
    print(f"MAE за последние 120 с до поломки: {mae_near:.1f} с")
    print(f"Точность классификатора «поломка в ближайшие {WARNING_HORIZON} с»: {accuracy:.3f}")

    joblib.dump({"regressor": regressor, "classifier": classifier, "features": FEATURES}, "model.joblib")
    print("Модель сохранена в model.joblib")


if __name__ == "__main__":
    main()