import pandas as pd
import joblib
import os
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, "datasets", "resources.csv")

df = pd.read_csv(DATA_PATH)

df["date"] = pd.to_datetime(df["date"])
df["day"] = df["date"].dt.day
df["month"] = df["date"].dt.month

import numpy as np

df["demand"] = (
    df["population"] * 0.0005 +
    (100 - df["water_level"]) * 50 +
    (50000 - df["food_stock"]) * 0.1 +
    np.random.normal(0, 500, len(df))
)

X = df[["population","lpg_stock","water_level","food_stock","day","month"]]
y = df["demand"]

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

model = RandomForestRegressor()
model.fit(X_train, y_train)

score = model.score(X_test, y_test)
print("Model Accuracy:", score)

MODEL_PATH = os.path.join(BASE_DIR, "model", "resource_model.pkl")
joblib.dump(model, MODEL_PATH)

print("Model saved successfully")