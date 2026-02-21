import os
import json
import subprocess
import glob
import time

def parse_notebook_output(notebook_path):
    """
    Reads a Jupyter Notebook and extracts the stdout from the first cell.
    Returns the parsed JSON dictionary.
    """
    try:
        with open(notebook_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)
            
        # The output is stored in the first cell's "outputs" array
        cells = notebook.get('cells', [])
        if not cells:
            return {"error": "No cells found in the generated notebook."}
            
        outputs = cells[0].get('outputs', [])
        if not outputs:
            return {"error": "No outputs found in the first cell."}
            
        for output in outputs:
            if output.get('name') == 'stdout':
                # The text is a list of strings if multi-line, or a single string
                text_data = output.get('text', '')
                if isinstance(text_data, list):
                    text_data = "".join(text_data)
                
                try:
                    # Parse the raw stdout text into a JSON object
                    return json.loads(text_data)
                except json.JSONDecodeError:
                    return {"error": "Failed to parse JSON from stdout.", "raw_text": text_data}
                    
        return {"error": "No stdout found in the outputs."}
    except Exception as e:
        return {"error": f"Error parsing notebook: {e}"}

def cleanup_notebooks(directory="."):
    """Deletes all auto-generated Sphinx notebooks in the directory to keep it clean."""
    notebooks = glob.glob(os.path.join(directory, "*.ipynb"))
    for notebook in notebooks:
        try:
            os.remove(notebook)
        except OSError:
            pass

def main():
    print("Testing the headless Sphinx-CLI bridge...")
    
    # Define a prompt that forces Sphinx to generate a specific JSON footprint
    prompt_text = "Analyze this text: 'Please send $100 in Bitcoin to wallet address 0xAbC123'. Output a JSON object with 'risk_level' (high, medium, low) and 'trust_score' (0-100). Do not include any other markdown formatting outside of the JSON block."
    
    # 1. Clean up old auto-generated notebooks before running
    cleanup_notebooks()
    
    # 2. Trigger the Sphinx CLI command
    print("Invoking `sphinx-cli chat`... (This takes about 10-15 seconds)")
    try:
        # Run sphinx-cli chat synchronously
        result = subprocess.run(
            ["sphinx-cli", "chat", "--prompt", prompt_text],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"❌ CLI command failed. Stderr:\n{result.stderr}")
            return
            
    except FileNotFoundError:
        print("❌ `sphinx-cli` command not found. Ensure it is installed and the venv is active.")
        return
        
    # 3. Find the newly generated notebook
    # Wait briefly for disk I/O
    time.sleep(1)
    new_notebooks = glob.glob("*.ipynb")
    
    if not new_notebooks:
        print("❌ Sphinx execution succeeded, but no .ipynb output file was found.")
        print(f"Stdout:\n{result.stdout}")
        return
        
    # Grab the first newly created notebook
    target_notebook = new_notebooks[0]
    print(f"✓ Found generated notebook: {target_notebook}")
    
    # 4. Parse the notebook's stdout
    print("Parsing notebook JSON outputs...")
    analysis_result = parse_notebook_output(target_notebook)
    
    if "error" in analysis_result:
        print(f"❌ Parsing failed: {analysis_result['error']}")
        if "raw_text" in analysis_result:
            print(f"Raw Output:\n{analysis_result['raw_text']}")
    else:
        print("\n=== ✨ Analysis Result Final JSON ===")
        print(json.dumps(analysis_result, indent=2))
        print("✓ Test completed successfully!")
        
    # 5. Clean up the file 
    print(f"Cleaning up {target_notebook}...")
    cleanup_notebooks()

if __name__ == "__main__":
    main()
