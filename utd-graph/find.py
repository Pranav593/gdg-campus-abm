import pandas as pd

df = pd.read_csv("names.csv")

keywords = ["Engineering", "Jindal", "Management", "Science",
            "Student Union", "Library", "McDermott", "Parking", "Lot"]

for k in keywords:
    hits = df[df["name"].str.contains(k, case=False)]
    print(f"\n--- {k} ---")
    for _, r in hits.iterrows():
        print(f"  {r['name']}   [{r['building']}, {r['amenity']}]")