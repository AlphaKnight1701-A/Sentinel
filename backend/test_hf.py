import warnings
from transformers import pipeline
import logging

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO)

print("Testing SDXL...")
pipe_sdxl = pipeline("image-classification", model="Organika/sdxl-detector", device="cpu")
from PIL import Image
import numpy as np
dummy_img = Image.fromarray(np.zeros((224, 224, 3), dtype=np.uint8))
res_sdxl = pipe_sdxl(dummy_img)
print(f"SDXL result: {res_sdxl}")

print("\nTesting GAN...")
pipe_gan = pipeline("image-classification", model="dima806/deepfake_vs_real_image_detection", device="cpu")
res_gan = pipe_gan(dummy_img)
print(f"GAN result: {res_gan}")
