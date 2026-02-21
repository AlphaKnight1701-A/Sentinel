import os
from dotenv import load_dotenv
from cortex import CortexClient, DistanceMetric

# Load from .env
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

def main():
    actian_url = os.environ.get("ACTIAN_VECTORAI_URL", "http://localhost:50051")
    actian_key = os.environ.get("ACTIAN_VECTORAI_API_KEY")

    print(f"Connecting to Actian VectorAI at {actian_url}...")
    
    try:
        with CortexClient(address=actian_url, api_key=actian_key) as client:
            version, uptime = client.health_check()
            print(f"✓ Connected to {version}")

            collection_name = "test_collection"
            
            # Create collection
            print(f"Creating collection '{collection_name}'...")
            client.create_collection(
                name=collection_name,
                dimension=128,
                distance_metric=DistanceMetric.COSINE,
            )
            print("✓ Collection created.")

            # Insert vectors
            print("Inserting a test vector...")
            client.upsert(
                collection_name,
                id=0,
                vector=[0.1]*128,
                payload={"name": "Test Item", "description": "This is a test vector."}
            )
            print("✓ Vector inserted.")

            # Search
            print("Searching for the test vector...")
            results = client.search(collection_name, query=[0.1]*128, top_k=2, with_payload=True)
            print(f"✓ Search completed. Found {len(results)} results:")
            for r in results:
                print(f"   ID: {r.id}, Score: {r.score:.4f}, Payload: {r.payload}")

            # Cleanup
            print(f"Cleaning up collection '{collection_name}'...")
            client.delete_collection(collection_name)
            print("✓ Cleanup completed successfully.")

    except Exception as e:
        print(f"❌ Actian VectorAI test failed: {e}")

if __name__ == "__main__":
    main()
