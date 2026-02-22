import httpx
import asyncio
import json

URL = "http://localhost:8000/live-feed"

async def test_twitter_payload():
    payload = {
        "post_text": "Is this real or AI? Found it on the street today #citylife 🏙️",
        "profile_display_name": "Urban Explorer",
        "profile_username": "@city_walker99",
        "media_urls": [
            "https://images.pexels.com/photos/8386440/pexels-photo-8386440.jpeg"
        ],
        "content_type": "post"
    }

    print("Sending payload...")
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(URL, json=payload)
    
    print("Status:", response.status_code)
    if response.status_code == 200:
        data = response.json()
        print("Risk:", data.get("risk_level"))
        print("Summary:", data.get("reasoning_summary"))
        print("\n--- Additional Info ---")
        print("Diffusion Score:", data.get("diffusion_score"))
        print("GAN Score:", data.get("gan_score"))
        print("Faces Detected:", data.get("faces_detected"))
    else:
        print("Error:", response.text)

if __name__ == "__main__":
    asyncio.run(test_twitter_payload())
