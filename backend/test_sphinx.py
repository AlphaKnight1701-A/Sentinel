import os
from dotenv import load_dotenv

# Load from .env
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

def main():
    api_key = os.environ.get("SPHINX_API_KEY")
    if not api_key:
        print("❌ SPHINX_API_KEY not found in environment.")
        return

    print("✓ Sphinx API key detected. Let's try basic SDK initialization.")
    
    try:
        from sphinxapi import Sphinx
        client = Sphinx(api_key=api_key)
        print("✓ Sphinx client initialized successfully.")
        
        # Test basic reasoning
        print("Running a basic reasoning test...")
        response = client.reason(task="trust_signal", inputs={
            "raw_text": "Hello, this is a test string for trust signal analysis."
        })
        print(f"✓ Reasoning successful. Response keys: {list(response.keys())}")
        print(f"Risk level: {response.get('risk_level')}")
        
    except ImportError:
        print("⚠ The `sphinxapi` package is not found. Are you sure `sphinx-ai-cli` includes the SDK?")
        print("Testing via CLI instead (as a fallback).")
        import subprocess
        # Basic CLI usage for test
        try:
            result = subprocess.run(["sphinx-cli", "--help"], capture_output=True, text=True)
            if "Sphinx CLI" in result.stdout or result.returncode == 0:
                print("✓ `sphinx-cli` is successfully installed and available.")
            else:
                print(f"❌ CLI check failed: {result.stderr}")
        except FileNotFoundError:
            print("❌ `sphinx-cli` command not found.")
    except Exception as e:
        print(f"❌ Sphinx initialization or API call failed: {e}")

if __name__ == "__main__":
    main()
