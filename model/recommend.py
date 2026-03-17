import pandas as pd
import joblib
from datetime import datetime

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, "datasets", "resources.csv")

data = pd.read_csv(DATA_PATH)
model = joblib.load(os.path.join(BASE_DIR, "model", "resource_model.pkl"))

def refresh_data():
    global data
    data = pd.read_csv(DATA_PATH)

def calculate_priority(prediction, supply):
    gap = prediction - supply
    if gap <= 0:
        return 20
    return min(100, int((gap / prediction) * 100))

def estimate_time_to_crisis(prediction, supply):
    if prediction <= supply:
        return "Stable"
    gap = prediction - supply
    days = max(1, int(supply / (gap + 1)))
    return f"{days} days"

def alert_level(priority):
    if priority > 80:
        return "NATIONAL ALERT"
    elif priority > 50:
        return "STATE ALERT"
    else:
        return "NORMAL"

def predict_risk(state, resource):

    if state not in data["state"].values:
        raise ValueError("State not found")

    row = data[data["state"] == state].iloc[0]

    population = row["population"]
    lpg = row["lpg_stock"]
    water = row["water_level"]
    food = row["food_stock"]

    today = datetime.today()

    input_data = pd.DataFrame(
    [[population, lpg, water, food, today.day, today.month]],
    columns=["population","lpg_stock","water_level","food_stock","day","month"]
    )

    prediction = model.predict(input_data)[0]

    if resource == "lpg":
        supply = lpg
    elif resource == "water":
        supply = water
    elif resource == "food":
        supply = food
    else:
        supply = lpg + food

    if prediction > supply:
        risk = "CRITICAL"
    elif prediction > (0.8 * supply):
        risk = "WARNING"
    else:
        risk = "SAFE"

    return prediction, risk, row, supply

def detect_cause(row, resource):

    causes = []

    if resource == "lpg" and row["lpg_stock"] < 5000:
        causes.append("Low LPG supply / import disruption")

    if resource == "water" and row["water_level"] < 60:
        causes.append("Low water reserves / poor rainfall")

    if resource == "food" and row["food_stock"] < 20000:
        causes.append("Low food stock / supply imbalance")

    if len(causes) == 0:
        causes.append("High demand pressure")

    return causes

def find_support_states(resource):

    if resource == "lpg":
        sorted_states = data.sort_values(by="lpg_stock", ascending=False)
    elif resource == "water":
        sorted_states = data.sort_values(by="water_level", ascending=False)
    elif resource == "food":
        sorted_states = data.sort_values(by="food_stock", ascending=False)
    else:
        sorted_states = data.sort_values(by=["lpg_stock","food_stock"], ascending=False)

    return list(sorted_states["state"].head(3))

def recommend_actions(risk):

    if risk == "SAFE":
        return [
            "Continue monitoring resource levels",
            "Maintain buffer stock"
        ]

    elif risk == "WARNING":
        return [
            "Prepare additional supply",
            "Increase monitoring",
            "Alert authorities"
        ]

    elif risk == "CRITICAL":
        return [
            "Reroute emergency supply",
            "Import additional resources",
            "Issue public advisory",
            "Deploy emergency reserves"
        ]

def weekly_forecast(state, resource):

    base_prediction, _, _, _ = predict_risk(state, resource)

    forecast = []
    demand = base_prediction

    for day in range(7):
        demand *= 1.02
        forecast.append({
            "day": day+1,
            "predicted_demand": int(demand)
        })

    return forecast

def predict_for_date(state, resource, target_date):

    today = datetime.today()
    target = datetime.strptime(target_date,"%Y-%m-%d")

    days = (target - today).days

    base_prediction, _, _, _ = predict_risk(state, resource)

    predicted = base_prediction * (1.02 ** days)

    return int(predicted)

def generate_risk_map(resource):

    results = []

    for _, row in data.iterrows():
        state = row["state"]
        prediction, risk, _, _ = predict_risk(state, resource)

        results.append({
            "state": state,
            "risk_level": risk
        })

    return results

def optimize_redistribution(resource):

    plan = []

    for _, row in data.iterrows():

        state = row["state"]

        prediction, risk, row_data, supply = predict_risk(state, resource)

        if risk == "CRITICAL":

            deficit = prediction - supply

            donors = data.sort_values(
                by=["lpg_stock","food_stock"],
                ascending=False
            )

            for _, donor in donors.iterrows():

                donor_state = donor["state"]

                if donor_state == state:
                    continue

                donor_supply = donor["lpg_stock"] + donor["food_stock"]

                transferable = min(deficit, int(0.2 * donor_supply))

                if transferable > 0:

                    plan.append({
                        "from": donor_state,
                        "to": state,
                        "amount": transferable,
                        "resource": resource
                    })

                    deficit -= transferable

                if deficit <= 0:
                    break

    return plan

def generate_recommendation(state, resource):

    prediction, risk, row, supply = predict_risk(state, resource)

    causes = detect_cause(row, resource)

    support_states = find_support_states(resource) if risk != "SAFE" else []

    actions = recommend_actions(risk)

    weekly = weekly_forecast(state, resource)

    redistribution = optimize_redistribution(resource)

    priority = calculate_priority(prediction, supply)

    time = estimate_time_to_crisis(prediction, supply)

    alert = alert_level(priority)

    result = {
        "state": state,
        "resource": resource,
        "predicted_demand": int(prediction),
        "risk_level": risk,
        "priority_score": priority,
        "time_to_crisis": time,
        "alert_level": alert,
        "causes": causes,
        "support_states": support_states,
        "recommended_actions": actions,
        "weekly_forecast": weekly,
        "redistribution_plan": redistribution
    }

    return result

if __name__ == "__main__":

    print(generate_recommendation("Rajasthan","lpg"))

if __name__ == "__main__":
    result = generate_recommendation("Rajasthan")
    print(result)