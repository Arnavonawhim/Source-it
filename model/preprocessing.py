import pandas as pd

def preprocess_data(data):

    numeric_cols = ["population","lpg_stock","water_level","food_stock"]

    data[numeric_cols] = data[numeric_cols].apply(pd.to_numeric)

    data["water_level"] = data["water_level"] / 100

    return data