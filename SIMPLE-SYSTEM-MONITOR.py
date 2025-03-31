import os
import requests
import zipfile
import subprocess
import time
import wmi
import psutil

# Define paths
LIBRARY_PATH = "E:\\vscode\\simple-system-monitor\\library"
OHM_ZIP_URL = "https://openhardwaremonitor.org/files/openhardwaremonitor-v0.9.6.zip"

def download_ohm():
    """Downloads OpenHardwareMonitor.zip and ensures it's a valid ZIP."""
    os.makedirs(LIBRARY_PATH, exist_ok=True)
    
    zip_filename = OHM_ZIP_URL.split("/")[-1]  # Keep original name
    zip_path = os.path.join(LIBRARY_PATH, zip_filename)

    # If the file already exists, check if it's valid
    if os.path.exists(zip_path):
        try:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                print(f"✅ {zip_filename} already exists and is valid.")
                return zip_path  # File is valid, use it
        except zipfile.BadZipFile:
            print(f"⚠️ {zip_filename} is corrupt. Re-downloading...")

    print(f"🔹 Downloading {zip_filename}...")
    response = requests.get(OHM_ZIP_URL, stream=True)

    # Save to file
    with open(zip_path, "wb") as file:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                file.write(chunk)

    print("✅ Download complete!")

    # Verify if the file is a valid ZIP
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            print("✅ ZIP file is valid!")
    except zipfile.BadZipFile:
        print("❌ Downloaded file is NOT a valid ZIP. Exiting.")
        os.remove(zip_path)  # Delete the corrupt file
        return None  # Stop execution

    return zip_path

def extract_ohm(zip_path):
    """Extracts OpenHardwareMonitor if it's valid."""
    if not zip_path:
        print("❌ No valid ZIP file to extract.")
        return

    print("🔹 Extracting OpenHardwareMonitor...")
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(LIBRARY_PATH)
    print("✅ Extraction complete!")

def find_extracted_folder():
    """Finds the extracted OpenHardwareMonitor folder."""
    for item in os.listdir(LIBRARY_PATH):
        item_path = os.path.join(LIBRARY_PATH, item)
        if os.path.isdir(item_path):
            return item_path
    return None

def run_ohm():
    """Finds and runs OpenHardwareMonitor.exe."""
    ohm_folder = find_extracted_folder()
    if not ohm_folder:
        print("❌ OpenHardwareMonitor folder not found!")
        return

    ohm_exe = os.path.join(ohm_folder, "OpenHardwareMonitor.exe")
    
    if os.path.exists(ohm_exe):
        print("🚀 Launching OpenHardwareMonitor...")
        subprocess.Popen(ohm_exe, shell=True)
        time.sleep(2)  # Wait for it to initialize
    else:
        print("❌ OpenHardwareMonitor.exe not found!")

def get_temperatures():
    """Fetch and print CPU & GPU temperatures."""
    print("🔹 Fetching CPU & GPU temperatures...")

    try:
        comp = wmi.WMI(namespace="root\\OpenHardwareMonitor")
        for sensor in comp.Sensor():
            if sensor.SensorType == 'Temperature':
                print(f"{sensor.Name}: {sensor.Value}°C")
    except Exception as e:
        print(f"❌ Failed to fetch temperatures: {e}")

def get_system_usage():
    """Fetch and print CPU, RAM, and GPU usage."""
    print("\n🔹 System Usage:")
    print(f"CPU Usage: {psutil.cpu_percent()}%")
    print(f"RAM Usage: {psutil.virtual_memory().percent}%")

# Run the functions
zip_path = download_ohm()

if zip_path:
    extract_ohm(zip_path)
    run_ohm()
    time.sleep(5)  # Give OHM time to initialize
    get_temperatures()
    get_system_usage()
