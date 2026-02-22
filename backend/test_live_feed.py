import httpx
import time
import asyncio

URL = "http://localhost:8000/live-feed"

TEST_IMAGES = {
    # ── AI-Generated / Fake (should return medium or high risk) ──────────────
    # Midjourney-style fantasy portrait
    "Fake: AI Face - Fantasy Portrait":     "https://images.pexels.com/photos/8386440/pexels-photo-8386440.jpeg",
    # Stable Diffusion landscape
    "Fake: AI Landscape - Sci-Fi City":     "https://images.pexels.com/photos/8386434/pexels-photo-8386434.jpeg",
    # AI concept art / digital painting
    "Fake: AI Concept Art":                 "https://images.pexels.com/photos/8386422/pexels-photo-8386422.jpeg",
    # GAN-generated stylized face
    "Fake: AI GAN - Stylized Face":         "https://images.pexels.com/photos/8078484/pexels-photo-8078484.jpeg",
    # AI art - surreal composite
    "Fake: AI Surreal Composite":           "https://images.pexels.com/photos/3861969/pexels-photo-3861969.jpeg",

    # ── Real Photos (should return low risk) ────────────────────────────────
    # Outdoor street photography
    "Real: Street Scene":                   "https://images.unsplash.com/photo-1477959858617-67f85cf4f1df?q=80&w=1000&auto=format&fit=crop",
    # Real human portrait (studio)
    "Real: Studio Portrait":                "https://images.unsplash.com/photo-1534528741775-53994a69daeb?q=80&w=1000&auto=format&fit=crop",
    # Architecture / cityscape
    "Real: Architecture":                   "https://images.unsplash.com/photo-1486325212027-8081e485255e?q=80&w=1000&auto=format&fit=crop",
    # Food photography
    "Real: Food":                            "https://images.unsplash.com/photo-1567620905732-2d1ec7ab7445?q=80&w=1000&auto=format&fit=crop",
    # Wildlife / animal
    "Real: Wildlife":                       "https://images.unsplash.com/photo-1474511320723-9a56873867b5?q=80&w=1000&auto=format&fit=crop",
}

async def test_endpoint(image_url: str, description: str):
    print(f"\n--- Testing: {description} ---")
    payload = {"image_url": image_url, "content_type": "image"}
    start_time = time.time()
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(URL, json=payload)
        except Exception as e:
            print(f"Failed to connect: {e}")
            return
            
    end_time = time.time()
    print("Overall Response: ", response)
    print(f"Status Code: {response.status_code}")
    print(f"Time taken: {(end_time - start_time) * 1000:.2f} ms")
    
    if response.status_code == 200:
        data = response.json()
        print(f"Risk Level:  {data.get('risk_level')}")
        print(f"Trust Score: {data.get('trust_score')}")
        print(f"Confidence:  {data.get('confidence')}")
        print(f"Reasoning:   {data.get('reasoning_summary')}")
    else:
        print(f"Error: {response.text}")

async def main():
    for desc, url in TEST_IMAGES.items():
        await test_endpoint(url, desc)
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
