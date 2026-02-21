from cortex import CortexClient

try:
    client = CortexClient(address="localhost:50051", api_key="")
    client.connect()
    print("Connected to Actian.")
    client.drop_collection("sentinel_cache")
    print("Dropped collection 'sentinel_cache'. It will be recreated on next app startup.")
except Exception as e:
    print(f"Error: {e}")
