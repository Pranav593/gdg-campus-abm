import sys

print(f"Python: {sys.version}\n")

packages = {
    "Mesa": "mesa",
    "NetworkX": "networkx",
    "OSMnx": "osmnx",
    "GeoPandas": "geopandas",
    "Shapely": "shapely",
    "Pandas": "pandas",
    "NumPy": "numpy",
    "Requests": "requests",
    "BeautifulSoup": "bs4",
    "Scikit-learn": "sklearn",
    "XGBoost": "xgboost",
    "Matplotlib": "matplotlib",
    "Plotly": "plotly",
}

failed = []

for name, module in packages.items():
    try:
        __import__(module)
        print(f"✓ {name}")
    except ImportError:
        print(f"✗ {name}")
        failed.append(name)

print()

if failed:
    print("Setup failed. Missing:", ", ".join(failed))
    sys.exit(1)

print("✓ Setup successful!")