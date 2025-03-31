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

# Define paths - Use AppData on Windows, or ~/.local on Linux/Mac
if os.name == 'nt':  # Windows
    LIBRARY_PATH = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'SimpleSystemMonitor')
else:  # Linux/Mac
    LIBRARY_PATH = os.path.join(os.path.expanduser('~'), '.local', 'share', 'SimpleSystemMonitor')

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

def is_ohm_running():
    """Check if OpenHardwareMonitor is already running."""
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            process_name = proc.info['name'].lower()
            if 'openhardwaremonitor' in process_name:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False

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
    """Finds and runs OpenHardwareMonitor.exe if not already running."""
    # First, check if OHM is already running
    if is_ohm_running():
        log("OpenHardwareMonitor is already running!", "SUCCESS")
        return True
        
    # If not running, launch it
    ohm_folder = find_extracted_folder()
    if not ohm_folder:
        log("OpenHardwareMonitor folder not found!", "ERROR")
        return False

    ohm_exe = os.path.join(ohm_folder, "OpenHardwareMonitor.exe")

    if os.path.exists(ohm_exe):
        log("Launching OpenHardwareMonitor...", "SUCCESS")
        try:
            os.startfile(ohm_exe)
            time.sleep(2)  # Wait a bit for OHM to start
            return True
        except Exception as e:
            log(f"Failed to launch OHM: {e}", "ERROR")
            return False
    else:
        log("OpenHardwareMonitor.exe not found!", "ERROR")
        return False


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
    """Get GPU usage from OHM first, then try other methods if that fails."""
    # First try to get GPU usage from OHM since it's likely more reliable
    try:
        r = requests.get("http://localhost:8085/data.json", timeout=5)
        data = r.json()
        gpu_load = None
        
        def find_gpu_load(node):
            nonlocal gpu_load
            if 'Children' in node:
                for child in node['Children']:
                    find_gpu_load(child)
            
            # Look for GPU or Graphics Load nodes
            if 'Text' in node and 'Value' in node:
                node_text = node['Text'].lower()
                if ('load' in node_text and ('gpu' in node_text or 'graphics' in node_text)):
                    # Also accept GPU Core, GPU Memory, etc. usages
                    try:
                        value_str = node['Value']
                        value = float(value_str.split()[0])  # Remove " %" from the end
                        gpu_load = value
                        log(f"Found GPU Load from OHM: {value}% from {node['Text']}", "DEBUG")
                    except Exception as e:
                        log(f"Error parsing GPU load value: {e}", "DEBUG")
                        pass
        
        for hw in data['Children']:
            find_gpu_load(hw)
        
        if gpu_load is not None:
            log(f"Using GPU usage from OHM: {gpu_load}%", "SUCCESS")
            return gpu_load
    except Exception as e:
        log(f"Could not get GPU usage from OHM: {e}", "DEBUG")
    
    # Fall back to nvidia-smi for NVIDIA GPUs if OHM failed
    try:
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
        
    # Last resort: try WMI for Windows
    try:
        w = wmi.WMI(namespace="root\\CIMV2")
        gpu_info = w.Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine()
        if gpu_info:
            # This is approximate and might not work on all systems
            usage = sum(int(gpu.UtilizationPercentage) for gpu in gpu_info) / len(gpu_info)
            log(f"GPU Usage (WMI): {usage}%", "DEBUG")
            return usage
    except Exception:
        pass
    
    # If everything fails, return a default value
    log("Could not determine GPU usage, using default value", "WARNING")
    return 25  # Return a reasonable default value instead of 0


def get_cpu_usage_from_ohm():
    """Get CPU usage from OpenHardwareMonitor first."""
    try:
        r = requests.get("http://localhost:8085/data.json", timeout=5)
        data = r.json()
        cpu_load = None
        
        def find_cpu_load(node):
            nonlocal cpu_load
            if 'Children' in node:
                for child in node['Children']:
                    find_cpu_load(child)
            
            # Look for CPU Load nodes
            if 'Text' in node and 'Value' in node:
                node_text = node['Text'].lower()
                if 'load' in node_text and ('cpu' in node_text or 'processor' in node_text):
                    # Prefer total/package CPU load over individual cores
                    if 'total' in node_text or 'package' in node_text or node_text == 'cpu':
                        try:
                            value_str = node['Value']
                            value = float(value_str.split()[0])  # Remove " %" from the end
                            cpu_load = value
                            log(f"Found CPU Load from OHM: {value}% from {node['Text']}", "DEBUG")
                            return
                        except Exception as e:
                            log(f"Error parsing CPU load value: {e}", "DEBUG")
                    # If not a total load but some CPU load, keep it as a fallback
                    elif cpu_load is None:
                        try:
                            value_str = node['Value']
                            value = float(value_str.split()[0])
                            cpu_load = value
                            log(f"Found fallback CPU Load from OHM: {value}% from {node['Text']}", "DEBUG")
                        except Exception:
                            pass
        
        for hw in data['Children']:
            find_cpu_load(hw)
        
        if cpu_load is not None:
            log(f"Using CPU usage from OHM: {cpu_load}%", "SUCCESS")
            return cpu_load
    except Exception as e:
        log(f"Could not get CPU usage from OHM: {e}", "DEBUG")
    
    return None


def get_ram_usage_from_ohm():
    """Get RAM usage from OpenHardwareMonitor first."""
    try:
        r = requests.get("http://localhost:8085/data.json", timeout=5)
        data = r.json()
        ram_usage = None
        
        def find_ram_usage(node):
            nonlocal ram_usage
            if 'Children' in node:
                for child in node['Children']:
                    find_ram_usage(child)
            
            # Look for Memory Load nodes
            if 'Text' in node and 'Value' in node:
                node_text = node['Text'].lower()
                if ('load' in node_text or 'used' in node_text) and ('memory' in node_text or 'ram' in node_text):
                    try:
                        value_str = node['Value']
                        value = float(value_str.split()[0])  # Remove " %" or " GB" from the end
                        ram_usage = value
                        log(f"Found RAM Usage from OHM: {value}% from {node['Text']}", "DEBUG")
                        return
                    except Exception as e:
                        log(f"Error parsing RAM usage value: {e}", "DEBUG")
        
        for hw in data['Children']:
            find_ram_usage(hw)
        
        if ram_usage is not None:
            log(f"Using RAM usage from OHM: {ram_usage}%", "SUCCESS")
            return ram_usage
    except Exception as e:
        log(f"Could not get RAM usage from OHM: {e}", "DEBUG")
    
    return None


def get_system_metrics():
    """Collect the specific required system metrics without using psutil."""
    metrics = {}
    
    try:
        # First try to get CPU and RAM metrics from OHM
        cpu_usage = get_cpu_usage_from_ohm()
        ram_usage = get_ram_usage_from_ohm()
        
        if cpu_usage is not None:
            metrics['cpu_usage'] = round(cpu_usage, 1)
        else:
            # If OHM failed, fall back to WMI or command line
            log("Falling back to alternative methods for CPU usage", "DEBUG")
            
            if os.name == 'nt':  # Windows
                # Use WMI for Windows
                try:
                    w = wmi.WMI()
                    
                    # CPU Usage - Windows
                    if 'cpu_usage' not in metrics:
                        cpu_load = w.Win32_Processor()[0].LoadPercentage
                        metrics['cpu_usage'] = round(float(cpu_load), 1) if cpu_load is not None else 0
                    
                    # RAM Usage - Windows
                    if 'ram_usage' not in metrics and ram_usage is None:
                        computer = w.Win32_ComputerSystem()[0]
                        total_ram = float(computer.TotalPhysicalMemory)
                        
                        os_info = w.Win32_OperatingSystem()[0]
                        free_ram = float(os_info.FreePhysicalMemory) * 1024  # Convert from KB to bytes
                        
                        used_ram_percent = (total_ram - free_ram) / total_ram * 100
                        metrics['ram_usage'] = round(used_ram_percent, 1)
                    
                    log(f"Got metrics via WMI: CPU {metrics.get('cpu_usage')}%, RAM {metrics.get('ram_usage')}%", "DEBUG")
                except Exception as e:
                    log(f"Error getting metrics via WMI: {e}", "ERROR")
                    # Fall back to command line in case of WMI failure
                    cmd_metrics = get_metrics_via_command_line()
                    if 'cpu_usage' not in metrics:
                        metrics['cpu_usage'] = cmd_metrics['cpu_usage']
                    if 'ram_usage' not in metrics and ram_usage is None:
                        metrics['ram_usage'] = cmd_metrics['ram_usage']
            else:
                # Use command line for Linux/Mac
                cmd_metrics = get_metrics_via_command_line()
                if 'cpu_usage' not in metrics:
                    metrics['cpu_usage'] = cmd_metrics['cpu_usage']
                if 'ram_usage' not in metrics and ram_usage is None:
                    metrics['ram_usage'] = cmd_metrics['ram_usage']
        
        # Add RAM usage from OHM if we got it
        if ram_usage is not None:
            metrics['ram_usage'] = round(ram_usage, 1)
        
        # GPU usage - Keep existing implementation which already prioritizes OHM
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


def get_metrics_via_command_line():
    """Get CPU and RAM metrics via command line tools."""
    metrics = {'cpu_usage': 0, 'ram_usage': 0}
    import subprocess
    
    try:
        if os.name == 'nt':  # Windows
            # CPU usage via typeperf (Windows command line)
            cpu_cmd = "typeperf -sc 1 \"\\Processor(_Total)\\% Processor Time\""
            cpu_result = subprocess.run(cpu_cmd, shell=True, capture_output=True, text=True)
            if cpu_result.returncode == 0:
                # Parse the output: "timestamp","value"
                lines = cpu_result.stdout.strip().split('\n')
                if len(lines) >= 2:
                    value_line = lines[1].strip('"').split('","')
                    if len(value_line) >= 2:
                        metrics['cpu_usage'] = round(float(value_line[1]), 1)
            
            # RAM usage via wmic (Windows command line)
            memory_cmd = "wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /Value"
            memory_result = subprocess.run(memory_cmd, shell=True, capture_output=True, text=True)
            if memory_result.returncode == 0:
                output = memory_result.stdout.strip()
                free_mem = None
                total_mem = None
                
                for line in output.split('\n'):
                    if "=" in line:
                        key, value = line.split('=', 1)
                        if "FreePhysicalMemory" in key:
                            free_mem = float(value)
                        elif "TotalVisibleMemorySize" in key:
                            total_mem = float(value)
                
                if free_mem is not None and total_mem is not None and total_mem > 0:
                    used_percent = (total_mem - free_mem) / total_mem * 100
                    metrics['ram_usage'] = round(used_percent, 1)
        else:  # Linux/Mac
            # CPU usage via top or mpstat
            try:
                # Try mpstat first
                cpu_cmd = "mpstat 1 1 | grep -A 5 '%idle' | tail -n 1 | awk '{print 100 - $NF}'"
                cpu_result = subprocess.run(cpu_cmd, shell=True, capture_output=True, text=True)
                if cpu_result.returncode == 0 and cpu_result.stdout.strip():
                    metrics['cpu_usage'] = round(float(cpu_result.stdout.strip()), 1)
                else:
                    # Fall back to top
                    cpu_cmd = "top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{print 100 - $1}'"
                    cpu_result = subprocess.run(cpu_cmd, shell=True, capture_output=True, text=True)
                    if cpu_result.returncode == 0 and cpu_result.stdout.strip():
                        metrics['cpu_usage'] = round(float(cpu_result.stdout.strip()), 1)
            except Exception:
                metrics['cpu_usage'] = 0
            
            # RAM usage via free
            try:
                mem_cmd = "free | grep Mem | awk '{print $3/$2 * 100.0}'"
                mem_result = subprocess.run(mem_cmd, shell=True, capture_output=True, text=True)
                if mem_result.returncode == 0 and mem_result.stdout.strip():
                    metrics['ram_usage'] = round(float(mem_result.stdout.strip()), 1)
            except Exception:
                metrics['ram_usage'] = 0
    
    except Exception as e:
        log(f"Error getting metrics via command line: {e}", "ERROR")
        metrics['cpu_usage'] = 10  # Default values
        metrics['ram_usage'] = 20
    
    log(f"Got metrics via command line: CPU {metrics['cpu_usage']}%, RAM {metrics['ram_usage']}%", "DEBUG")
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
    log(f"Using library path: {LIBRARY_PATH}")
    
    # Step 1: Download and extract OpenHardwareMonitor if needed
    zip_path = download_ohm()
    if zip_path:
        extract_ohm(zip_path)
        
        # Step 2: Run OpenHardwareMonitor if not already running
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