import torch
from transformers import AutoImageProcessor, AutoModelForImageClassification

model_id = "umm-maybe/AI-image-detector"
print(f"Loading {model_id}...")

processor = AutoImageProcessor.from_pretrained(model_id)
model = AutoModelForImageClassification.from_pretrained(model_id)

dummy_input = torch.randn(1, 3, 224, 224)

print("Exporting to ONNX...")
torch.onnx.export(
    model, 
    dummy_input, 
    "general_ai_detector.onnx",
    export_params=True,
    opset_version=17,
    do_constant_folding=True,
    input_names=['pixel_values'],
    output_names=['logits'],
    dynamic_axes={'pixel_values': {0: 'batch_size'}, 'logits': {0: 'batch_size'}}
)

print("✅ ONNX export complete: general_ai_detector.onnx")
