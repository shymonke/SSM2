import sys
import os
import requests
import zipfile
import time

# --- Module Check Only ---
required_modules = ["requests", "wmi", "psutil"]

missing_modules = []
for module in required_modules:
    try:
        __import__(module)
    except ImportError:
        missing_modules.append(module)

if missing_modules:
    print("❌ Missing modules detected:", ", ".join(missing_modules))
    print("Please install them manually using pip and run the script again.")
    sys.exit(1)

import wmi
import psutil

# Define paths
LIBRARY_PATH = "E:\\vscode\\simple-system-monitor\\library"
OHM_ZIP_URL = "https://openhardwaremonitor.org/files/openhardwaremonitor-v0.9.6.zip"
NODEMCU_IP = "192.168.0.150"  # CHANGE THIS TO YOUR NODEMCU's IP


def check_ohm_remote_server():
    """Check if OHM Remote Server is enabled."""
    try:
        r = requests.get("http://localhost:8085/data.json", timeout=2)
        if r.status_code == 200:
            print("✅ OHM remote server is running!")
            return True
    except:
        pass
    print("❌ OHM remote server is not responding. Please open OHM, go to 'Options > Remote Web Server' and enable it.")
    input("Press Enter once the server is enabled...")
    return check_ohm_remote_server()


def download_ohm():
    """Downloads OpenHardwareMonitor.zip and ensures it's a valid ZIP."""
    os.makedirs(LIBRARY_PATH, exist_ok=True)
    zip_filename = OHM_ZIP_URL.split("/")[-1]
    zip_path = os.path.join(LIBRARY_PATH, zip_filename)

    if os.path.exists(zip_path):
        try:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                print(f"✅ {zip_filename} already exists and is valid.")
                return zip_path
        except zipfile.BadZipFile:
            print(f"⚠️ {zip_filename} is corrupt. Re-downloading...")

    print(f"🔹 Downloading {zip_filename}...")
    response = requests.get(OHM_ZIP_URL, stream=True)

    with open(zip_path, "wb") as file:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                file.write(chunk)

    print("✅ Download complete!")

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            print("✅ ZIP file is valid!")
    except zipfile.BadZipFile:
        print("❌ Downloaded file is NOT a valid ZIP. Exiting.")
        os.remove(zip_path)
        return None

    return zip_path


def extract_ohm(zip_path):
    """Extracts OpenHardwareMonitor if it's valid."""
    if not zip_path:
        print("❌ No valid ZIP file to extract.")
        return

    print("🔹 Extracting OpenHardwareMonitor...")
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            for member in zip_ref.namelist():
                filename = os.path.join(LIBRARY_PATH, member)
                if os.path.exists(filename):
                    print(f"⚠️ Skipping existing file: {filename}")
                    continue
                zip_ref.extract(member, LIBRARY_PATH)
        print("✅ Extraction complete!")
    except PermissionError as e:
        print(f"❌ Permission denied while extracting: {e}")
        print("Please run the script with admin privileges or change the library path.")


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
        try:
            os.startfile(ohm_exe)
            time.sleep(2)
        except Exception as e:
            print(f"❌ Failed to launch OHM: {e}")
    else:
        print("❌ OpenHardwareMonitor.exe not found!")


def get_temperatures_from_json():
    """Fetch CPU and GPU temperatures from OHM's JSON."""
    try:
        r = requests.get("http://localhost:8085/data.json")
        data = r.json()
        cpu_temp = None
        gpu_temp = None

        def traverse(node):
            nonlocal cpu_temp, gpu_temp
            if 'Children' in node:
                for child in node['Children']:
                    traverse(child)
            if 'Text' in node and 'Temperature' in node['Text']:
                if 'CPU' in node['Text'] and cpu_temp is None:
                    cpu_temp = float(node['Value'].split(' ')[0])
                elif 'GPU' in node['Text'] and gpu_temp is None:
                    gpu_temp = float(node['Value'].split(' ')[0])

        for hw in data['Children']:
            traverse(hw)

        print(f"CPU Temp: {cpu_temp} °C, GPU Temp: {gpu_temp} °C")
        return cpu_temp, gpu_temp

    except Exception as e:
        print(f"❌ Failed to parse OHM JSON: {e}")
        return None, None


def send_to_nodemcu(cpu_temp, gpu_temp):
    try:
        url = f"http://{NODEMCU_IP}/?temp={cpu_temp}&gpu={gpu_temp}"
        r = requests.get(url, timeout=2)
        if r.status_code == 200:
            print("✅ Data sent to NodeMCU successfully!")
        else:
            print(f"⚠️ Unexpected response from NodeMCU: {r.status_code}")
    except Exception as e:
        print(f"❌ Failed to send data to NodeMCU: {e}")


# --------- EXECUTION STARTS HERE --------- #

zip_path = download_ohm()

if zip_path:
    extract_ohm(zip_path)
    run_ohm()
    time.sleep(5)

    if check_ohm_remote_server():
        cpu, gpu = get_temperatures_from_json()
        if cpu is not None and gpu is not None:
            send_to_nodemcu(cpu, gpu)
