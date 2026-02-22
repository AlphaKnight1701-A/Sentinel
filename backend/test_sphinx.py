import subprocess
import glob
print("Running sphinx-cli chat --prompt 'test prompt'")
subprocess.run(["sphinx-cli", "chat", "--prompt", "test prompt"], capture_output=True, text=True)
notebooks = glob.glob("**/*.ipynb", recursive=True)
print("Found notebooks:", notebooks)
