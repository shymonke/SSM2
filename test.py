import wmi

def get_cpu_temp():
    w = wmi.WMI(namespace="root\\WMI")
    sensors = w.MSAcpi_ThermalZoneTemperature()
    
    if sensors:
        temp = sensors[0].CurrentTemperature / 10.0 - 273.15  # Convert to Celsius
        return round(temp, 2)
    
    return "Temperature sensor not available"

print(f"CPU Temperature: {get_cpu_temp()}°C")

