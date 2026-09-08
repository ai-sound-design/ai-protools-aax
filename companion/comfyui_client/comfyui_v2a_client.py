import json, time, requests, pathlib
import os
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HOST = "http://localhost:8188"  # ComfyUI SSH tunnel endpoint

# Create a session with retry strategy for better ngrok compatibility
session = requests.Session()
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)

# Video file path - using the test video from your test data
VIDEO_PATH = r"C:\Users\Username\model-tests\data\MMAudio_examples\noSound\sora_beach.mp4"

def get_user_inputs():
    """Sammelt Benutzereingaben für Prompt, Negative Prompt und Seed"""
    print("\n=== MMAudio Interactive Parameters ===")
    print("Geben Sie die Parameter für die Audiogenerierung ein:\n")

    prompt = input("🎵 Prompt (Default: \"\"): ").strip()
    negative_prompt = input("❌ Negative Prompt (Default: \"voices, music\"): ").strip()
    if not negative_prompt:
        negative_prompt = "voices, music"

    while True:
        seed_input = input("🎲 Seed (Default: 42): ").strip()
        if not seed_input:
            seed = 42
            break
        try:
            seed = int(seed_input)
            break
        except ValueError:
            print("   ⚠️  Bitte geben Sie eine gültige Zahl ein.")
    
    print(f"\n✅ Parameter gesetzt:")
    print(f"   Prompt: '{prompt}'")
    print(f"   Negative Prompt: '{negative_prompt}'")
    print(f"   Seed: {seed}\n")
    
    return prompt, negative_prompt, seed

print(f"🌐 Connecting to ComfyUI via SSH tunnel: {HOST}")

# Get user inputs first
prompt, negative_prompt, seed = get_user_inputs()

# Test connection first
print("🔗 Testing connection...")
try:
    test_response = session.get(f"{HOST}/system_stats", timeout=30)
    test_response.raise_for_status()
    print("✅ Connection successful!")
except requests.exceptions.RequestException as e:
    print(f"❌ Connection failed: {e}")
    exit(1)

# Check if video file exists
if not os.path.exists(VIDEO_PATH):
    print(f"❌ Video file not found: {VIDEO_PATH}")
    exit(1)

print(f"📹 Video file found: {os.path.basename(VIDEO_PATH)} ({os.path.getsize(VIDEO_PATH) / 1024 / 1024:.1f} MB)")

# 1) Upload video - try multiple ComfyUI API endpoints
print("📤 Uploading video...")
upload_success = False

# Method 1: Try /upload/image (most common ComfyUI endpoint)
try:
    with open(VIDEO_PATH, "rb") as f:
        files = {"image": ("sora_beach.mp4", f, "video/mp4")}
        r = session.post(f"{HOST}/upload/image", files=files, timeout=300)
        r.raise_for_status()
        print("✅ Video uploaded successfully via /upload/image!")
        upload_success = True
except Exception as e:
    print(f"   Method 1 (/upload/image) failed: {e}")

# Method 2: Try /api/upload if method 1 failed
if not upload_success:
    try:
        with open(VIDEO_PATH, "rb") as f:
            files = {"file": ("sora_beach.mp4", f, "video/mp4")}
            r = session.post(f"{HOST}/api/upload", files=files, timeout=300)
            r.raise_for_status()
            print("✅ Video uploaded successfully via /api/upload!")
            upload_success = True
    except Exception as e:
        print(f"   Method 2 (/api/upload) failed: {e}")

if not upload_success:
    print("❌ All upload methods failed. The video might need to be copied manually via SSH.")
    print("💡 Alternative: Copy the file directly to the ComfyUI input folder on the remote machine.")
    print("   Command: scp -P 2223 'your_video.mp4' user@<SERVER_IP>:/path/to/comfyui/input/")
    
    # Ask user if they want to continue without upload
    response = input("Continue without upload? The video must already exist on the server (y/n): ")
    if response.lower() != 'y':
        exit(1)
    print("📹 Proceeding with existing video file on server...")

# 2) Load your workflow JSON and ensure it references sora_beach.mp4
print("📋 Loading workflow...")
workflow_path = "comfyUI_workflows/mmaudio_test-API(fp16).json"
if not os.path.exists(workflow_path):
    print(f"❌ Workflow file not found: {workflow_path}")
    exit(1)

wf = json.load(open(workflow_path, "r", encoding="utf-8"))
print("✅ Workflow loaded successfully!")

# Update the video input in the workflow - Node 91 is VHS_LoadVideo
if "91" in wf and "inputs" in wf["91"]:
    wf["91"]["inputs"]["video"] = "sora_beach.mp4"  # Use the uploaded filename
    print("📹 Updated workflow to use uploaded video: sora_beach.mp4")
else:
    print("⚠️  Warning: Could not find video input node in workflow")

# Update MMAudioSampler parameters - Node 92
if "92" in wf and wf["92"]["class_type"] == "MMAudioSampler":
    wf["92"]["inputs"]["prompt"] = prompt
    wf["92"]["inputs"]["negative_prompt"] = negative_prompt
    wf["92"]["inputs"]["seed"] = seed
    print(f"🎵 Updated MMAudioSampler parameters:")
    print(f"   Prompt: '{prompt}'")
    print(f"   Negative Prompt: '{negative_prompt}'")
    print(f"   Seed: {seed}")
else:
    print("⚠️  Warning: Could not find MMAudioSampler node in workflow")

# 3) Kick off the job - ComfyUI expects workflow wrapped in "prompt" key
print("🚀 Submitting workflow to ComfyUI...")
# ComfyUI API requires the workflow to be wrapped in a "prompt" object
prompt_data = {
    "prompt": wf,
    "client_id": "python_client"
}
pr = session.post(f"{HOST}/prompt", json=prompt_data, timeout=30)
pr.raise_for_status()
prompt_id = pr.json()["prompt_id"]
print(f"✅ Workflow submitted! Job ID: {prompt_id}")

# 4) Poll for completion
print("⏳ Processing... (this may take several minutes)")
start_time = time.time()
while True:
    hr = session.get(f"{HOST}/history/{prompt_id}")
    hr.raise_for_status()
    hist = hr.json()
    
    # ComfyUI returns a complex status object, not just a string
    entry = hist.get(prompt_id, {})
    status_obj = entry.get("status", {})
    
    # Check if it's the new format with status_str and completed fields
    if isinstance(status_obj, dict):
        status_str = status_obj.get("status_str", "unknown")
        completed = status_obj.get("completed", False)
        
        elapsed = time.time() - start_time
        print(f"   Status: {status_str} (elapsed: {elapsed:.1f}s)", end='\r')
        
        if completed and status_str == "success":
            print(f"\n✅ Processing completed successfully! (took {elapsed:.1f}s)")
            break
        elif status_str == "error":
            print(f"\n❌ Processing failed after {elapsed:.1f}s")
            print(f"Error details: {status_obj}")
            raise RuntimeError(hist)
    else:
        # Fallback for old format (simple string)
        elapsed = time.time() - start_time
        print(f"   Status: {status_obj if status_obj else 'processing'} (elapsed: {elapsed:.1f}s)", end='\r')
        
        if status_obj == "completed":
            print(f"\n✅ Processing completed! (took {elapsed:.1f}s)")
            break
        elif status_obj == "error":
            print(f"\n❌ Processing failed after {elapsed:.1f}s")
            raise RuntimeError(hist)
    
    time.sleep(2)  # Check every 2 seconds

# 5) Find the saved FLAC from SaveAudio node (107)
entry = hist[prompt_id]
outputs = entry.get("outputs", {})

# Look specifically for SaveAudio node (107) output
save_audio_node = outputs.get("107", {})
files = save_audio_node.get("gltf", [])  # SaveAudio might use different key

# If not found, try common output keys
if not files:
    files = save_audio_node.get("files", [])
if not files:
    files = save_audio_node.get("audio", [])

# Debug: print the actual output structure
print(f"🔍 Debug - Available outputs: {list(outputs.keys())}")
if "107" in outputs:
    print(f"🔍 Debug - SaveAudio node keys: {list(save_audio_node.keys())}")
    print(f"🔍 Debug - SaveAudio content: {save_audio_node}")

# Fallback: search all nodes for any file output
file_info = None
if files and len(files) > 0:
    file_info = files[0]
else:
    # Search all nodes for file outputs
    for node_id, node_output in outputs.items():
        for key, value in node_output.items():
            if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
                if "filename" in value[0]:
                    file_info = value[0]
                    print(f"🔍 Found file in node {node_id}, key {key}: {file_info}")
                    break
        if file_info:
            break

if not file_info:
    print("❌ No output file found in history")
    print(f"Available outputs structure: {outputs}")
    raise RuntimeError("No output file in history")

# 6) Download it
print("📥 Downloading generated audio...")
fn = file_info["filename"]; sf = file_info.get("subfolder","")
audio = session.get(f"{HOST}/view", params={"filename": fn, "subfolder": sf, "type": "output"}, timeout=60)
audio.raise_for_status()

output_path = f"comfyUI_outputs/output_{prompt_id}.flac"
pathlib.Path(output_path).write_bytes(audio.content)
print(f"✅ Audio saved as: {output_path}")
print(f"📊 File size: {len(audio.content) / 1024:.1f} KB")
