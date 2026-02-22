from app.ml import get_sdxl_pipeline
from PIL import Image
import urllib.request
import io
url = "https://images.pexels.com/photos/8386440/pexels-photo-8386440.jpeg"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as response:
    img_bytes = response.read()
pipe = get_sdxl_pipeline()
img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
print("SDXL Raw Results:", pipe(img))
