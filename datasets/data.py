import pandas as pd
import random
from datetime import datetime, timedelta

states = [
    "Delhi","Maharashtra","Rajasthan","Punjab","Gujarat",
    "Uttar Pradesh","Bihar","West Bengal","Haryana","Karnataka",
    "Tamil Nadu","Kerala","Madhya Pradesh","Odisha","Assam",
    "Jharkhand","Chhattisgarh","Telangana","Andhra Pradesh","Himachal Pradesh",
    "Uttarakhand","Goa","Tripura","Meghalaya","Manipur"
]

start_date = datetime(2024, 1, 1)
days = 60

data = []

for state in states:

    population = random.randint(5_000_000, 200_000_000)

    base_lpg = random.randint(4000, 10000)
    base_water = random.randint(50, 90)
    base_food = random.randint(20000, 60000)

    for i in range(days):

        date = start_date + timedelta(days=i)

        lpg = base_lpg + random.randint(-500, 500)
        water = base_water + random.randint(-5, 5)
        food = base_food + random.randint(-2000, 2000)

        data.append([
            state,
            date.strftime("%Y-%m-%d"),
            population,
            max(1000, lpg),
            max(30, water),
            max(5000, food)
        ])

df = pd.DataFrame(data, columns=[
    "state","date","population","lpg_stock","water_level","food_stock"
])

df.to_csv("resources.csv", index=False)

print("Dataset generated successfully")