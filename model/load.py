import pandas as pd

def load_dataset():

    path = "../datasets/resources.csv"

    data = pd.read_csv(path)

    print("Dataset Loaded Successfully")
    print("Shape:", data.shape)

    print("\nColumns:")
    print(data.columns)

    print("\nMissing values:")
    print(data.isnull().sum())

    return data


if __name__ == "__main__":
    load_dataset()