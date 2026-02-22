from app.ml import get_sdxl_pipeline
from PIL import Image

pipe = get_sdxl_pipeline()
image = Image.new('RGB', (256, 256), color='red')
results = pipe(image, top_k=None)
print("RAW RESULTS:", results)
