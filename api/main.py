from fastapi import FastAPI
from model.recommend import (
    generate_recommendation,
    generate_risk_map,
    weekly_forecast,
    predict_for_date,
    optimize_redistribution,
    refresh_data
)

app = FastAPI()

@app.get("/recommend")
def recommend(state: str, resource: str):
    return generate_recommendation(state, resource)

@app.get("/risk_map")
def risk_map(resource: str):
    return generate_risk_map(resource)

@app.get("/forecast")
def forecast(state: str, resource: str):
    return weekly_forecast(state, resource)

@app.get("/predict_date")
def predict_date(state: str, resource: str, date: str):
    return predict_for_date(state, resource, date)

@app.get("/redistribute")
def redistribute(resource: str):
    return optimize_redistribution(resource)

@app.get("/refresh")
def refresh():
    refresh_data()