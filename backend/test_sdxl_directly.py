import asyncio
from app.ml import fetch_image, score_sdxl
import sys

async def main():
    try:
        url = "https://images.unsplash.com/photo-1474511320723-9a56873867b5?q=80&w=1000&auto=format&fit=crop"
        print(f"Fetching {url}")
        sys.stdout.flush()
        img_bytes = await fetch_image(url)
        print(f"Fetched {len(img_bytes)} bytes")
        sys.stdout.flush()
        res = score_sdxl(img_bytes)
        print("SDXL Result:", res)
        sys.stdout.flush()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
