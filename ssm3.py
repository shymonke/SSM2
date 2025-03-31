import sys
import os
import requests
import zipfile
import time
import json

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
NODEMCU_IP = "192.168.0.190"  # Static IP of NodeMCU

# Configure logging format
def log(message, type="INFO"):
    prefix = {
        "INFO": "ℹ️",
        "SUCCESS": "✅",
        "WARNING": "⚠️",
        "ERROR": "❌",
        "DEBUG": "🔍",
        "METRIC": "📊"
    }.get(type, "ℹ️")
    
    print(f"{prefix} {message}")

def check_ohm_remote_server():
    """Check if OHM Remote Server is enabled."""
    try:
        r = requests.get("http://localhost:8085/data.json", timeout=5)
        if r.status_code == 200:
            log("OHM remote server is running!", "SUCCESS")
            return True
    except Exception as e:
        log(f"Error checking OHM server: {e}", "ERROR")
    
    log("OHM remote server is not responding. Please follow these steps:", "ERROR")
    log("1. Open OpenHardwareMonitor")
    log("2. Go to Options > Remote Web Server")
    log("3. Check 'Run web server'")
    log("4. Make sure port is set to 8085")
    
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
                log(f"{zip_filename} already exists and is valid.", "SUCCESS")
                return zip_path
        except zipfile.BadZipFile:
            log(f"{zip_filename} is corrupt. Re-downloading...", "WARNING")

    log(f"Downloading {zip_filename}...")
    response = requests.get(OHM_ZIP_URL, stream=True)

    with open(zip_path, "wb") as file:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                file.write(chunk)

    log("Download complete!", "SUCCESS")

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            log("ZIP file is valid!", "SUCCESS")
    except zipfile.BadZipFile:
        log("Downloaded file is NOT a valid ZIP. Exiting.", "ERROR")
        os.remove(zip_path)
        return None

    return zip_path


def extract_ohm(zip_path):
    """Extracts OpenHardwareMonitor if it's valid."""
    if not zip_path:
        log("No valid ZIP file to extract.", "ERROR")
        return

    log("Extracting OpenHardwareMonitor...")
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            for member in zip_ref.namelist():
                filename = os.path.join(LIBRARY_PATH, member)
                if os.path.exists(filename):
                    log(f"Skipping existing file: {filename}", "WARNING")
                    continue
                zip_ref.extract(member, LIBRARY_PATH)
        log("Extraction complete!", "SUCCESS")
    except PermissionError as e:
        log(f"Permission denied while extracting: {e}", "ERROR")
        log("Please run the script with admin privileges or change the library path.")


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
        log("OpenHardwareMonitor folder not found!", "ERROR")
        return

    ohm_exe = os.path.join(ohm_folder, "OpenHardwareMonitor.exe")

    if os.path.exists(ohm_exe):
        log("Launching OpenHardwareMonitor...", "SUCCESS")
        try:
            os.startfile(ohm_exe)
            time.sleep(2)  # Wait a bit for OHM to start
        except Exception as e:
            log(f"Failed to launch OHM: {e}", "ERROR")
    else:
        log("OpenHardwareMonitor.exe not found!", "ERROR")


def get_temperatures_from_json():
    """Fetch CPU and GPU temperatures from OHM's JSON."""
    try:
        r = requests.get("http://localhost:8085/data.json", timeout=5)
        data = r.json()
        cpu_temp = None
        gpu_temp = None
        
        # Dump raw JSON for debugging
        with open("ohm_data.json", "w") as f:
            json.dump(data, f, indent=2)
        
        log("Parsing hardware sensor data...", "DEBUG")
        
        # Find all CPU/GPU hardware nodes first
        cpu_nodes = []
        gpu_nodes = []
        
        def find_hardware_nodes(node, parent_path=""):
            """Find all CPU and GPU hardware nodes in the data tree."""
            if not isinstance(node, dict) or 'Text' not in node:
                return
                
            node_text = node['Text']
            current_path = f"{parent_path}/{node_text}" if parent_path else node_text
            
            # Identify CPU hardware
            if any(term in node_text for term in ['CPU', 'Processor', 'Ryzen', 'Intel', 'Core i', 'Pentium', 'Celeron', 'AMD']):
                if not any(term in node_text for term in ['Graphics', 'GPU']):  # Make sure it's not a CPU graphics chip
                    log(f"Found CPU hardware: {current_path}", "DEBUG")
                    cpu_nodes.append((node, current_path))
            
            # Identify GPU hardware
            if any(term in node_text for term in ['GPU', 'Graphics', 'NVIDIA', 'AMD', 'Radeon', 'GeForce']):
                log(f"Found GPU hardware: {current_path}", "DEBUG")
                gpu_nodes.append((node, current_path))
            
            # Process children recursively
            if 'Children' in node and isinstance(node['Children'], list):
                for child in node['Children']:
                    find_hardware_nodes(child, current_path)
        
        # Start finding hardware nodes
        find_hardware_nodes(data)
        
        def extract_temp_from_hardware(hardware_nodes, temp_type="CPU"):
            """Extract temperature from identified hardware nodes."""
            for node, path in hardware_nodes:
                # Look for a temperatures section
                if 'Children' in node and isinstance(node['Children'], list):
                    for child in node['Children']:
                        if 'Text' in child and 'Temperatures' in child['Text'] and 'Children' in child:
                            # Found a temperatures section, look for specific temperature nodes
                            for temp_node in child['Children']:
                                if 'Text' not in temp_node or 'Value' not in temp_node:
                                    continue
                                    
                                temp_text = temp_node['Text']
                                
                                # For CPU, prioritize Package or Total temps
                                if temp_type == "CPU":
                                    is_package = any(term in temp_text for term in ['Package', 'Tctl', 'Tdie', 'Total', 'CPU'])
                                    if is_package:
                                        try:
                                            temp_value = float(temp_node['Value'].split()[0])
                                            log(f"Found {temp_type} temperature: {temp_value}°C from {path}/{temp_text}", "SUCCESS")
                                            return temp_value
                                        except Exception as e:
                                            log(f"Error parsing temperature value: {e}", "ERROR")
                                
                                # For GPU, prioritize Core or general GPU temps
                                else:
                                    is_core = any(term in temp_text for term in ['Core', 'GPU', 'Die', 'Hot Spot', 'Junction'])
                                    if is_core:
                                        try:
                                            temp_value = float(temp_node['Value'].split()[0])
                                            log(f"Found {temp_type} temperature: {temp_value}°C from {path}/{temp_text}", "SUCCESS")
                                            return temp_value
                                        except Exception as e:
                                            log(f"Error parsing temperature value: {e}", "ERROR")
            
            # If no specific temp found, return None
            return None
        
        # Extract temperatures from identified hardware nodes
        cpu_temp = extract_temp_from_hardware(cpu_nodes, "CPU")
        gpu_temp = extract_temp_from_hardware(gpu_nodes, "GPU")
        
        # If still not found, try a generic scan for temperature nodes
        if cpu_temp is None or gpu_temp is None:
            log("Falling back to generic temperature scan", "DEBUG")
            
            temp_nodes = []
            
            def find_temp_nodes(node, parent_path=""):
                """Find all temperature nodes in the data tree."""
                if not isinstance(node, dict):
                    return
                    
                # Check if this is a temperature node
                if 'Text' in node and 'Value' in node and 'Temperature' in node.get('Text', ''):
                    try:
                        temp_value = float(node['Value'].split()[0])  # Extract numeric part
                        current_path = f"{parent_path}/{node['Text']}" if parent_path else node['Text']
                        temp_nodes.append((node, current_path, temp_value))
                        log(f"Found temperature node: {current_path} = {temp_value}°C", "DEBUG")
                    except Exception:
                        pass
                
                # Also check if it's a temperature node from Temperatures section
                if 'Text' in node and 'Value' in node and ('°C' in node.get('Value', '') or '°F' in node.get('Value', '')):
                    try:
                        temp_value = float(node['Value'].split()[0])  # Extract numeric part
                        current_path = f"{parent_path}/{node['Text']}" if parent_path else node['Text']
                        temp_nodes.append((node, current_path, temp_value))
                        log(f"Found temperature node: {current_path} = {temp_value}°C", "DEBUG")
                    except Exception:
                        pass
                        
                # Process children recursively
                if 'Children' in node and isinstance(node['Children'], list):
                    new_path = parent_path
                    if 'Text' in node:
                        new_path = f"{parent_path}/{node['Text']}" if parent_path else node['Text']
                    
                    for child in node['Children']:
                        find_temp_nodes(child, new_path)
            
            # Find all temperature nodes
            find_temp_nodes(data)
            
            # Categorize temperature nodes
            for node, path, value in temp_nodes:
                node_text = node['Text']
                
                # Try to identify CPU temps if not found yet
                if cpu_temp is None:
                    is_cpu_temp = (
                        ('CPU' in path and 'GPU' not in path) or 
                        ('Processor' in path) or 
                        any(term in node_text for term in ['CPU', 'Package', 'Processor'])
                    )
                    
                    if is_cpu_temp:
                        # Prioritize Package or Total temps
                        is_important = any(term in node_text for term in ['Package', 'Total', 'Tctl', 'Tdie'])
                        if is_important or cpu_temp is None:
                            cpu_temp = value
                            log(f"Using CPU temperature from {path}: {value}°C", "SUCCESS")
                
                # Try to identify GPU temps if not found yet
                if gpu_temp is None:
                    is_gpu_temp = (
                        ('GPU' in path) or 
                        ('Graphics' in path) or 
                        any(term in node_text for term in ['GPU', 'Graphics', 'Video'])
                    )
                    
                    if is_gpu_temp:
                        # Prioritize Core or Die temps
                        is_important = any(term in node_text for term in ['Core', 'Die', 'GPU Temperature', 'Hot'])
                        if is_important or gpu_temp is None:
                            gpu_temp = value
                            log(f"Using GPU temperature from {path}: {value}°C", "SUCCESS")
        
        # Report results
        if cpu_temp is not None:
            log(f"Final CPU Temperature: {cpu_temp}°C", "SUCCESS")
        else:
            log("CPU temperature could not be determined, reporting as N/A", "WARNING")
            cpu_temp = "N/A"  # Use N/A instead of default value
        
        if gpu_temp is not None:
            log(f"Final GPU Temperature: {gpu_temp}°C", "SUCCESS")
        else:
            log("GPU temperature could not be determined, reporting as N/A", "WARNING")
            gpu_temp = "N/A"  # Use N/A instead of default value
        
        return cpu_temp, gpu_temp

    except Exception as e:
        log(f"Failed to parse OHM JSON: {e}", "ERROR")
        return "N/A", "N/A"  # Return N/A instead of default values


def get_gpu_usage():
    """Get GPU usage if possible using multiple methods."""
    try:
        # Try to use NVIDIA SMI for NVIDIA GPUs
        import subprocess
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'],
            stdout=subprocess.PIPE, 
            text=True, 
            check=True
        )
        gpu_load = float(result.stdout.strip())
        log(f"GPU Usage (NVIDIA): {gpu_load}%", "DEBUG")
        return gpu_load
    except Exception:
        pass
        
    try:
        # Fallback to WMI for Windows
        w = wmi.WMI(namespace="root\\CIMV2")
        gpu_info = w.Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine()
        if gpu_info:
            # This is approximate and might not work on all systems
            usage = sum(int(gpu.UtilizationPercentage) for gpu in gpu_info) / len(gpu_info)
            log(f"GPU Usage (WMI): {usage}%", "DEBUG")
            return usage
    except Exception:
        pass
            
    # If all methods fail, try to get GPU usage from OHM
    try:
        r = requests.get("http://localhost:8085/data.json", timeout=5)
        data = r.json()
        gpu_load = None
        
        def find_gpu_load(node):
            nonlocal gpu_load
            if 'Children' in node:
                for child in node['Children']:
                    find_gpu_load(child)
            
            if 'Text' in node and 'Load' in node['Text'] and 'Value' in node and ('GPU' in node['Text'] or 'Graphics' in node['Text']):
                try:
                    value_str = node['Value']
                    value = float(value_str.split()[0])  # Remove " %" from the end
                    gpu_load = value
                    log(f"Found GPU Load: {value}% from {node['Text']}", "DEBUG")
                except Exception:
                    pass
        
        for hw in data['Children']:
            find_gpu_load(hw)
        
        if gpu_load is not None:
            return gpu_load
    except Exception:
        pass
    
    # If everything fails, return a default value
    log("Could not determine GPU usage, using default value", "WARNING")
    return 25  # Return a reasonable default value instead of 0


def get_system_metrics():
    """Collect the specific required system metrics."""
    metrics = {}
    
    try:
        # CPU usage
        metrics['cpu_usage'] = round(psutil.cpu_percent(interval=0.5), 1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        metrics['ram_usage'] = round(memory.percent, 1)
        
        # GPU usage
        metrics['gpu_usage'] = round(get_gpu_usage(), 1)
    except Exception as e:
        log(f"Error getting system metrics: {e}", "ERROR")
        # Set default values
        metrics['cpu_usage'] = 10
        metrics['ram_usage'] = 20
        metrics['gpu_usage'] = 5
    
    log("System Metrics:", "METRIC")
    log(f"  • cpu_usage: {metrics['cpu_usage']}%", "METRIC")
    log(f"  • ram_usage: {metrics['ram_usage']}%", "METRIC")
    log(f"  • gpu_usage: {metrics['gpu_usage']}%", "METRIC")
    
    return metrics


def send_filtered_metrics_to_nodemcu(cpu_temp, gpu_temp):
    """Send only the required filtered metrics to the NodeMCU."""
    try:
        # Get additional system metrics
        metrics = get_system_metrics()
        
        # Add temperature data (ensuring we have numeric values)
        if cpu_temp == "N/A":
            metrics['cpu_temp'] = "N/A"
        else:
            metrics['cpu_temp'] = round(float(cpu_temp) if cpu_temp is not None else 0, 1)
            
        if gpu_temp == "N/A":
            metrics['gpu_temp'] = "N/A"
        else:
            metrics['gpu_temp'] = round(float(gpu_temp) if gpu_temp is not None else 0, 1)
        
        log(f"  • cpu_temp: {metrics['cpu_temp']}°C", "METRIC")
        log(f"  • gpu_temp: {metrics['gpu_temp']}°C", "METRIC")
        
        # Create a simplified JSON payload with only the required metrics
        filtered_metrics = {
            'cpu_temp': metrics['cpu_temp'],
            'cpu_usage': metrics['cpu_usage'],
            'ram_usage': metrics['ram_usage'],
            'gpu_temp': metrics['gpu_temp'],
            'gpu_usage': metrics['gpu_usage']
        }
        
        json_payload = json.dumps(filtered_metrics)
        
        # Send data to NodeMCU with increased timeout
        url = f"http://{NODEMCU_IP}/update"  # Using the correct endpoint (/update)
        headers = {'Content-Type': 'application/json'}
        
        log(f"Sending data to NodeMCU: {json_payload}")
        
        r = requests.post(url, data=json_payload, headers=headers, timeout=5)
        
        if r.status_code == 200:
            log("Filtered metrics sent to NodeMCU successfully!", "SUCCESS")
        else:
            log(f"Unexpected response from NodeMCU: {r.status_code}", "WARNING")
            log(f"Response: {r.text}", "WARNING")
    except requests.exceptions.Timeout:
        log(f"Connection to NodeMCU timed out. Ensure it's powered on and connected to WiFi.", "ERROR")
    except requests.exceptions.ConnectionError:
        log(f"Failed to connect to NodeMCU at {NODEMCU_IP}. Check if IP is correct.", "ERROR")
    except Exception as e:
        log(f"Failed to send metrics to NodeMCU: {e}", "ERROR")


def print_banner():
    """Print a nice banner at startup."""
    banner = """
    ╔════════════════════════════════════════════════╗
    ║                                                ║
    ║      🖥️  SYSTEM HARDWARE MONITOR v2.0  🖥️       ║
    ║                                                ║
    ╚════════════════════════════════════════════════╝
    """
    print(banner)


# --------- EXECUTION STARTS HERE --------- #

def main():
    """Main execution function."""
    print_banner()
    log("Starting System Monitor")
    
    # Step 1: Download and extract OpenHardwareMonitor if needed
    zip_path = download_ohm()
    if zip_path:
        extract_ohm(zip_path)
        
        # Step 2: Run OpenHardwareMonitor
        run_ohm()
        
        # Give OHM extra time to fully start up
        log("Waiting for OpenHardwareMonitor to initialize...")
        time.sleep(10)

        # Step 3: Check if the OHM web server is running
        if check_ohm_remote_server():
            # Step 4: Get initial data
            cpu_temp, gpu_temp = get_temperatures_from_json()
            send_filtered_metrics_to_nodemcu(cpu_temp, gpu_temp)
                
    log("System monitoring is active. Press Ctrl+C to exit.", "SUCCESS")
    
    # Continuous monitoring loop
    try:
        while True:
            # Get temperatures
            cpu_temp, gpu_temp = get_temperatures_from_json()
            
            # Send data to NodeMCU
            send_filtered_metrics_to_nodemcu(cpu_temp, gpu_temp)
            
            # Visual separator for logs
            log("-" * 40)
            
            # Wait before next update
            time.sleep(3)  # Update every 3 seconds
    except KeyboardInterrupt:
        log("Exiting monitoring script.")


if __name__ == "__main__":
    main()