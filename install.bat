@echo off
color 0A
title IT Infrastructure Monitoring System - Installer

echo ====================================================================
echo          IT INFRASTRUCTURE MONITORING SYSTEM INSTALLER
echo ====================================================================
echo.
echo This installer will:
echo  1. Install required Python libraries
echo  2. Download OpenHardwareMonitor (if needed)
echo  3. Set up the monitoring environment
echo  4. Configure the system to run from any directory
echo.
echo IMPORTANT PREREQUISITES:
echo  - Python 3.6 or higher must be installed
echo  - Administrator privileges are recommended for first-time setup
echo  - Your NodeMCU device should be powered on and connected to WiFi
echo.
echo Press any key to continue or CTRL+C to exit...
pause > nul

:: Check if Python is installed
echo.
echo Checking Python installation...
python --version > nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    color 0C
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    echo Press any key to exit...
    pause > nul
    exit /b 1
)
echo Python found successfully!

:: Create library directory
echo.
echo Creating library directory...
mkdir "%LOCALAPPDATA%\ITInfrastructureMonitor" 2> nul
echo Library directory configured at: %LOCALAPPDATA%\ITInfrastructureMonitor

:: Install requirements
echo.
echo Installing required Python packages...
pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    color 0E
    echo WARNING: Some packages failed to install.
    echo The monitoring system may still work with limited functionality.
    echo.
)

echo.
echo ====================================================================
echo                     STARTING MONITORING SYSTEM
echo ====================================================================
echo.
echo IMPORTANT FIRST-TIME SETUP INSTRUCTIONS:
echo.
echo When OpenHardwareMonitor starts:
echo  1. Go to Options menu
echo  2. Select "Remote Web Server"
echo  3. Check "Run web server"
echo  4. Ensure port is set to 8085
echo  5. Click OK
echo.
echo The monitoring system will then connect to your NodeMCU device
echo and begin displaying system metrics.
echo.
echo Press any key to start the monitoring system...
pause > nul

:: Run the monitoring script
color 0B
echo Starting monitoring system...
python ssm3.py --library-path "%LOCALAPPDATA%\ITInfrastructureMonitor"

echo.
echo If the system closed unexpectedly, check for errors above.
echo For help, please contact your system administrator.
echo.
echo Press any key to exit...
pause > nul
