from transformers import pipeline
from PIL import Image
import io

pipe = pipeline("image-classification", model="Organika/sdxl-detector", device="cpu")
img = Image.open("cat.jpg").convert("RGB")
res = pipe(img)
print("Cat (Real):", res)

res_all = pipe(img, top_k=None)
print("Cat (Real) All:", res_all)
