def create_features(data):
    
    data["estimated_demand"] = (
        data["population"] * 0.0002 +
        data["lpg_stock"] * 0.3 +
        data["food_stock"] * 0.1
    )

    return data