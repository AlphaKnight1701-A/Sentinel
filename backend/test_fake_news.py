from transformers import pipeline

print("Loading fake news model...")
pipe = pipeline("text-classification", model="mrm8488/bert-tiny-finetuned-fake-news-detection")

fake_text = "BREAKING: Saudi Arabia officially denies the US to use its soil against Iran."
real_text = "The quick brown fox jumps over the lazy dog."

print(f"Testing fake text: {fake_text}")
results_fake = pipe(fake_text, top_k=None)
print(f"RAW RESULTS FAKE: {results_fake}")

print(f"Testing real text: {real_text}")
results_real = pipe(real_text, top_k=None)
print(f"RAW RESULTS REAL: {results_real}")
