#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <ESP8266WebServer.h>
#include <WiFiClient.h>
#include <ArduinoJson.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include <EEPROM.h>
#include <UniversalTelegramBot.h>
#include <WiFiClientSecure.h>
#include <ESP8266mDNS.h>

// WiFi credentials
const char* ssid = "PEACE 2GHz";
const char* password = "7660011887";

// Device name for mDNS
const char* deviceName = "itinfrastructuremonitor";

// Telegram Bot settings
#define BOT_TOKEN "7805830591:AAG3iJkoJ8BryIi32CmWN7oK7xWo-0-O-OY"  // Replace with your bot token
#define CHAT_ID "1158723052"               // Replace with your chat ID

// Web server to receive metrics and host web interface
ESP8266WebServer server(80);

// Secure client for Telegram Bot
WiFiClientSecure secured_client;
UniversalTelegramBot bot(BOT_TOKEN, secured_client);

// TFT display pins
#define TFT_CS 15
#define TFT_RST 0
#define TFT_DC 2

// Colors
#define ST77XX_LIGHTGRAY 0xC618
#define ST77XX_BLACK 0x0000
#define ST77XX_WHITE 0xFFFF
#define ST77XX_RED 0xF800
#define ST77XX_GREEN 0x07E0
#define ST77XX_BLUE 0x001F
#define ST77XX_YELLOW 0xFFE0

Adafruit_ST7735 tft = Adafruit_ST7735(TFT_CS, TFT_DC, TFT_RST);

// Store the metrics
float cpu_temp = 0;
float cpu_usage = 0;
float ram_usage = 0;
float gpu_temp = 0;
float gpu_usage = 0;
String cpu_temp_str = "N/A";
String gpu_temp_str = "N/A";
unsigned long lastUpdateTime = 0;
unsigned long lastNotificationTime = 0;
const unsigned long NOTIFICATION_COOLDOWN = 60000; // 1 minute cooldown between notifications

// Threshold settings with default values
struct Settings {
  float cpu_temp_threshold = 80.0;
  float cpu_usage_threshold = 90.0;
  float ram_usage_threshold = 90.0;
  float gpu_temp_threshold = 80.0;
  float gpu_usage_threshold = 90.0;
  bool notifications_enabled = true;
} settings;

// EEPROM address for storing settings
#define SETTINGS_ADDR 0

// Function declarations
void showStartupScreen();
void connectToWiFi();
void drawBackground();
void updateMetricsDisplay();
void showError(const char* error);
void updateMetricsWithNA();
void loadSettings();
void saveSettings();
void sendTelegramNotification(String message);
void checkThresholds();
void handleRoot();
void handleUpdateThresholds();
void handleGetThresholds();
void handleMetrics();
void setupWebServer();
void handleResetThresholds();

void setup() {
  Serial.begin(115200);
  
  // Initialize EEPROM
  EEPROM.begin(512);
  
  // Load saved settings
  loadSettings();
  
  // Initialize display
  tft.initR(INITR_BLACKTAB);
  tft.setRotation(1);
  
  // Show startup screen
  showStartupScreen();
  
  // Connect to WiFi
  connectToWiFi();
  
  // Configure Telegram client to skip certificate validation
  secured_client.setInsecure();
  
  // Display initial layout
  drawBackground();
  
  // Set up web server
  setupWebServer();
  
  // Start server
  server.begin();
  Serial.println("HTTP server started");
  
  // Send startup notification
  if (settings.notifications_enabled) {
    sendTelegramNotification("IT Infrastructure Monitoring System started. Ready to monitor your system!");
  }
  
  // Show IP on display
  tft.setTextSize(1);
  tft.setTextColor(ST77XX_WHITE);
  tft.setCursor(5, 120);
  tft.print("Server: ");
  tft.println(WiFi.localIP());
}

void setupWebServer() {
  // Set up server endpoints
  server.on("/", HTTP_GET, handleRoot);
  server.on("/update", HTTP_POST, handleUpdate);
  server.on("/thresholds", HTTP_GET, handleGetThresholds);
  server.on("/thresholds", HTTP_POST, handleUpdateThresholds);
  server.on("/metrics", HTTP_GET, handleMetrics);
  server.on("/reset", HTTP_POST, handleResetThresholds);
}

void handleRoot() {
  String html = "<!DOCTYPE html>"
    "<html>"
    "<head>"
    "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
    "<meta charset='UTF-8'>"
    "<title>IT Infrastructure Monitoring System</title>"
    "<style>"
    "body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }"
    ".container { max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }"
    "h1 { color: #333; text-align: center; }"
    ".metrics { display: flex; flex-wrap: wrap; margin-bottom: 20px; }"
    ".metric { width: 48%; margin: 1%; padding: 10px; border-radius: 4px; background: #f9f9f9; box-sizing: border-box; }"
    ".metric h3 { margin-top: 0; color: #444; }"
    ".metric p { font-size: 24px; margin: 5px 0; }"
    ".green { color: green; }"
    ".yellow { color: #e6b800; }"
    ".red { color: red; }"
    "form { background: #f9f9f9; padding: 15px; border-radius: 4px; }"
    "label { display: block; margin: 10px 0 5px; }"
    "input[type='number'] { width: 100%; padding: 8px; margin-bottom: 10px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }"
    "button { background: #4CAF50; color: white; border: none; padding: 10px 15px; border-radius: 4px; cursor: pointer; font-size: 16px; margin-right: 10px; }"
    "button:hover { background: #45a049; }"
    "button.reset { background: #f44336; }"
    "button.reset:hover { background: #d32f2f; }"
    ".button-group { display: flex; justify-content: space-between; margin-top: 15px; }"
    ".toggle { display: flex; align-items: center; margin: 15px 0; }"
    ".toggle label { margin: 0 10px 0 0; }"
    ".switch { position: relative; display: inline-block; width: 60px; height: 34px; }"
    ".switch input { opacity: 0; width: 0; height: 0; }"
    ".slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #ccc; transition: .4s; border-radius: 34px; }"
    ".slider:before { position: absolute; content: ''; height: 26px; width: 26px; left: 4px; bottom: 4px; background-color: white; transition: .4s; border-radius: 50%; }"
    "input:checked + .slider { background-color: #2196F3; }"
    "input:checked + .slider:before { transform: translateX(26px); }"
    ".last-update { text-align: center; font-size: 12px; color: #666; margin-top: 20px; }"
    "</style>"
    "</head>"
    "<body>"
    "<div class='container'>"
    "<h1>IT Infrastructure Monitoring System</h1>"
    "<div class='metrics' id='metrics'>"
    "<div class='metric'><h3>CPU Temperature</h3><p id='cpu_temp'>Loading...</p></div>"
    "<div class='metric'><h3>CPU Usage</h3><p id='cpu_usage'>Loading...</p></div>"
    "<div class='metric'><h3>RAM Usage</h3><p id='ram_usage'>Loading...</p></div>"
    "<div class='metric'><h3>GPU Temperature</h3><p id='gpu_temp'>Loading...</p></div>"
    "<div class='metric'><h3>GPU Usage</h3><p id='gpu_usage'>Loading...</p></div>"
    "</div>"
    "<h2>Alert Thresholds</h2>"
    "<form id='thresholdForm'>"
    "<label for='cpu_temp_threshold'>CPU Temperature (°C):</label>"
    "<input type='number' id='cpu_temp_threshold' name='cpu_temp_threshold' min='0' max='100' step='1'>"
    "<label for='cpu_usage_threshold'>CPU Usage (%):</label>"
    "<input type='number' id='cpu_usage_threshold' name='cpu_usage_threshold' min='0' max='100' step='1'>"
    "<label for='ram_usage_threshold'>RAM Usage (%):</label>"
    "<input type='number' id='ram_usage_threshold' name='ram_usage_threshold' min='0' max='100' step='1'>"
    "<label for='gpu_temp_threshold'>GPU Temperature (°C):</label>"
    "<input type='number' id='gpu_temp_threshold' name='gpu_temp_threshold' min='0' max='100' step='1'>"
    "<label for='gpu_usage_threshold'>GPU Usage (%):</label>"
    "<input type='number' id='gpu_usage_threshold' name='gpu_usage_threshold' min='0' max='100' step='1'>"
    "<div class='toggle'>"
    "<label for='notifications_enabled'>Telegram Notifications:</label>"
    "<label class='switch'>"
    "<input type='checkbox' id='notifications_enabled' name='notifications_enabled'>"
    "<span class='slider'></span>"
    "</label>"
    "</div>"
    "<div class='button-group'>"
    "<button type='submit'>Save Thresholds</button>"
    "<button type='button' id='resetBtn' class='reset'>Reset to Defaults</button>"
    "</div>"
    "</form>"
    "<div class='last-update' id='last-update'></div>"
    "</div>"
    "<script>"
    "function getColor(value, threshold) {"
    "  if (value === 'N/A') return '';"
    "  return value < threshold * 0.75 ? 'green' : value < threshold ? 'yellow' : 'red';"
    "}"
    "function updateMetrics() {"
    "  fetch('/metrics')"
    "    .then(response => response.json())"
    "    .then(data => {"
    "      document.getElementById('cpu_temp').textContent = data.cpu_temp !== 'N/A' ? data.cpu_temp + '°C' : 'N/A';"
    "      document.getElementById('cpu_usage').textContent = data.cpu_usage + '%';"
    "      document.getElementById('ram_usage').textContent = data.ram_usage + '%';"
    "      document.getElementById('gpu_temp').textContent = data.gpu_temp !== 'N/A' ? data.gpu_temp + '°C' : 'N/A';"
    "      document.getElementById('gpu_usage').textContent = data.gpu_usage + '%';"
    "      document.getElementById('cpu_temp').className = getColor(data.cpu_temp, document.getElementById('cpu_temp_threshold').value);"
    "      document.getElementById('cpu_usage').className = getColor(data.cpu_usage, document.getElementById('cpu_usage_threshold').value);"
    "      document.getElementById('ram_usage').className = getColor(data.ram_usage, document.getElementById('ram_usage_threshold').value);"
    "      document.getElementById('gpu_temp').className = getColor(data.gpu_temp, document.getElementById('gpu_temp_threshold').value);"
    "      document.getElementById('gpu_usage').className = getColor(data.gpu_usage, document.getElementById('gpu_usage_threshold').value);"
    "      document.getElementById('last-update').textContent = 'Last updated: ' + new Date().toLocaleTimeString();"
    "    })"
    "    .catch(error => console.error('Error fetching metrics:', error));"
    "}"
    "function loadThresholds() {"
    "  fetch('/thresholds')"
    "    .then(response => response.json())"
    "    .then(data => {"
    "      document.getElementById('cpu_temp_threshold').value = data.cpu_temp_threshold;"
    "      document.getElementById('cpu_usage_threshold').value = data.cpu_usage_threshold;"
    "      document.getElementById('ram_usage_threshold').value = data.ram_usage_threshold;"
    "      document.getElementById('gpu_temp_threshold').value = data.gpu_temp_threshold;"
    "      document.getElementById('gpu_usage_threshold').value = data.gpu_usage_threshold;"
    "      document.getElementById('notifications_enabled').checked = data.notifications_enabled;"
    "    })"
    "    .catch(error => console.error('Error fetching thresholds:', error));"
    "}"
    "document.getElementById('thresholdForm').addEventListener('submit', function(e) {"
    "  e.preventDefault();"
    "  const formData = {"
    "    cpu_temp_threshold: parseFloat(document.getElementById('cpu_temp_threshold').value),"
    "    cpu_usage_threshold: parseFloat(document.getElementById('cpu_usage_threshold').value),"
    "    ram_usage_threshold: parseFloat(document.getElementById('ram_usage_threshold').value),"
    "    gpu_temp_threshold: parseFloat(document.getElementById('gpu_temp_threshold').value),"
    "    gpu_usage_threshold: parseFloat(document.getElementById('gpu_usage_threshold').value),"
    "    notifications_enabled: document.getElementById('notifications_enabled').checked"
    "  };"
    "  fetch('/thresholds', {"
    "    method: 'POST',"
    "    headers: {'Content-Type': 'application/json'},"
    "    body: JSON.stringify(formData)"
    "  })"
    "    .then(response => response.text())"
    "    .then(data => alert('Thresholds saved successfully!'))"
    "    .catch(error => console.error('Error saving thresholds:', error));"
    "});"
    "document.getElementById('resetBtn').addEventListener('click', function() {"
    "  if (confirm('Reset all thresholds to default values?')) {"
    "    fetch('/reset', { method: 'POST' })"
    "      .then(response => response.text())"
    "      .then(data => {"
    "        alert('Thresholds reset to defaults');"
    "        loadThresholds();"  // Reload the form with default values
    "        updateMetrics();"   // Update colors based on new thresholds
    "      })"
    "      .catch(error => console.error('Error resetting thresholds:', error));"
    "  }"
    "});"
    "loadThresholds();"
    "updateMetrics();"
    "setInterval(updateMetrics, 5000);"
    "</script>"
    "</body>"
    "</html>";
    
  server.send(200, "text/html", html);
}

void handleUpdate() {
  String message = "";
  
  if (server.hasArg("plain")) {
    message = server.arg("plain");
    Serial.println("Received metrics: " + message);
    
    // Parse the JSON
    DynamicJsonDocument doc(1024);
    DeserializationError error = deserializeJson(doc, message);
    
    if (!error) {
      // Extract the metrics
      if (doc.containsKey("cpu_temp")) {
        if (doc["cpu_temp"] == "N/A") {
          cpu_temp_str = "N/A";
        } else {
          cpu_temp = doc["cpu_temp"].as<float>();
          cpu_temp_str = String(cpu_temp, 1);
        }
      }
      
      if (doc.containsKey("cpu_usage")) {
        cpu_usage = doc["cpu_usage"].as<float>();
      }
      
      if (doc.containsKey("ram_usage")) {
        ram_usage = doc["ram_usage"].as<float>();
      }
      
      if (doc.containsKey("gpu_temp")) {
        if (doc["gpu_temp"] == "N/A") {
          gpu_temp_str = "N/A";
        } else {
          gpu_temp = doc["gpu_temp"].as<float>();
          gpu_temp_str = String(gpu_temp, 1);
        }
      }
      
      if (doc.containsKey("gpu_usage")) {
        gpu_usage = doc["gpu_usage"].as<float>();
      }
      
      lastUpdateTime = millis();
      // Update the display with new metrics
      updateMetricsDisplay();
      
      // Check if any thresholds are exceeded
      checkThresholds();
      
      // Respond with success
      server.send(200, "text/plain", "OK");
    } else {
      Serial.println("Failed to parse JSON");
      server.send(400, "text/plain", "Bad Request: Failed to parse JSON");
    }
  } else {
    server.send(400, "text/plain", "Bad Request: No data");
  }
}

void handleGetThresholds() {
  DynamicJsonDocument doc(1024);
  
  doc["cpu_temp_threshold"] = settings.cpu_temp_threshold;
  doc["cpu_usage_threshold"] = settings.cpu_usage_threshold;
  doc["ram_usage_threshold"] = settings.ram_usage_threshold;
  doc["gpu_temp_threshold"] = settings.gpu_temp_threshold;
  doc["gpu_usage_threshold"] = settings.gpu_usage_threshold;
  doc["notifications_enabled"] = settings.notifications_enabled;
  
  String response;
  serializeJson(doc, response);
  
  server.send(200, "application/json", response);
}

void handleUpdateThresholds() {
  String message = "";
  
  if (server.hasArg("plain")) {
    message = server.arg("plain");
    Serial.println("Received threshold update: " + message);
    
    // Parse the JSON
    DynamicJsonDocument doc(1024);
    DeserializationError error = deserializeJson(doc, message);
    
    if (!error) {
      if (doc.containsKey("cpu_temp_threshold")) {
        settings.cpu_temp_threshold = doc["cpu_temp_threshold"].as<float>();
      }
      
      if (doc.containsKey("cpu_usage_threshold")) {
        settings.cpu_usage_threshold = doc["cpu_usage_threshold"].as<float>();
      }
      
      if (doc.containsKey("ram_usage_threshold")) {
        settings.ram_usage_threshold = doc["ram_usage_threshold"].as<float>();
      }
      
      if (doc.containsKey("gpu_temp_threshold")) {
        settings.gpu_temp_threshold = doc["gpu_temp_threshold"].as<float>();
      }
      
      if (doc.containsKey("gpu_usage_threshold")) {
        settings.gpu_usage_threshold = doc["gpu_usage_threshold"].as<float>();
      }
      
      if (doc.containsKey("notifications_enabled")) {
        settings.notifications_enabled = doc["notifications_enabled"].as<bool>();
      }
      
      // Save settings to EEPROM
      saveSettings();
      
      server.send(200, "text/plain", "Thresholds updated successfully");
    } else {
      server.send(400, "text/plain", "Failed to parse threshold JSON");
    }
  } else {
    server.send(400, "text/plain", "No data received");
  }
}

void handleMetrics() {
  DynamicJsonDocument doc(1024);
  
  doc["cpu_temp"] = cpu_temp_str;
  doc["cpu_usage"] = cpu_usage;
  doc["ram_usage"] = ram_usage;
  doc["gpu_temp"] = gpu_temp_str;
  doc["gpu_usage"] = gpu_usage;
  
  String response;
  serializeJson(doc, response);
  
  server.send(200, "application/json", response);
}

void handleResetThresholds() {
  // Reset to default values
  settings.cpu_temp_threshold = 80.0;
  settings.cpu_usage_threshold = 90.0;
  settings.ram_usage_threshold = 90.0;
  settings.gpu_temp_threshold = 80.0;
  settings.gpu_usage_threshold = 90.0;
  settings.notifications_enabled = true;
  
  // Save to EEPROM
  saveSettings();
  
  // Update the display to show new color coding
  updateMetricsDisplay();
  
  server.send(200, "text/plain", "Settings reset to defaults");
}

void loadSettings() {
  // Read settings from EEPROM if they exist
  Settings savedSettings;
  EEPROM.get(SETTINGS_ADDR, savedSettings);
  
  // Validate settings (check if they are within reasonable bounds)
  if (savedSettings.cpu_temp_threshold > 0 && savedSettings.cpu_temp_threshold <= 100 &&
      savedSettings.cpu_usage_threshold > 0 && savedSettings.cpu_usage_threshold <= 100 &&
      savedSettings.ram_usage_threshold > 0 && savedSettings.ram_usage_threshold <= 100 &&
      savedSettings.gpu_temp_threshold > 0 && savedSettings.gpu_temp_threshold <= 100 &&
      savedSettings.gpu_usage_threshold > 0 && savedSettings.gpu_usage_threshold <= 100) {
    settings = savedSettings;
    Serial.println("Loaded settings from EEPROM");
  } else {
    // Use default settings if stored values are invalid
    Serial.println("Using default settings");
  }
}

void saveSettings() {
  EEPROM.put(SETTINGS_ADDR, settings);
  EEPROM.commit();
  Serial.println("Settings saved to EEPROM");
}

void sendTelegramNotification(String message) {
  if (millis() - lastNotificationTime < NOTIFICATION_COOLDOWN) {
    Serial.println("Notification cooldown active, skipping this notification");
    return;
  }
  
  if (bot.sendMessage(CHAT_ID, message, "")) {
    Serial.println("Telegram notification sent");
    lastNotificationTime = millis();
  } else {
    Serial.println("Failed to send Telegram notification");
  }
}

void checkThresholds() {
  if (!settings.notifications_enabled) {
    return;
  }
  
  String alertMessage = "";
  
  if (cpu_temp_str != "N/A" && cpu_temp >= settings.cpu_temp_threshold) {
    alertMessage += "⚠️ CPU Temperature: " + cpu_temp_str + "°C (Threshold: " + String(settings.cpu_temp_threshold, 1) + "°C)\n";
  }
  
  if (cpu_usage >= settings.cpu_usage_threshold) {
    alertMessage += "⚠️ CPU Usage: " + String(cpu_usage, 1) + "% (Threshold: " + String(settings.cpu_usage_threshold, 1) + "%)\n";
  }
  
  if (ram_usage >= settings.ram_usage_threshold) {
    alertMessage += "⚠️ RAM Usage: " + String(ram_usage, 1) + "% (Threshold: " + String(settings.ram_usage_threshold, 1) + "%)\n";
  }
  
  if (gpu_temp_str != "N/A" && gpu_temp >= settings.gpu_temp_threshold) {
    alertMessage += "⚠️ GPU Temperature: " + gpu_temp_str + "°C (Threshold: " + String(settings.gpu_temp_threshold, 1) + "°C)\n";
  }
  
  if (gpu_usage >= settings.gpu_usage_threshold) {
    alertMessage += "⚠️ GPU Usage: " + String(gpu_usage, 1) + "% (Threshold: " + String(settings.gpu_usage_threshold, 1) + "%)\n";
  }
  
  if (alertMessage != "") {
    alertMessage = "🚨 SYSTEM ALERT 🚨\n\n" + alertMessage;
    sendTelegramNotification(alertMessage);
  }
}

void drawBackground() {
  tft.fillScreen(ST77XX_BLACK);
  
  // Draw header
  tft.setTextSize(1);
  tft.setTextColor(ST77XX_WHITE);
  tft.setCursor(5, 5);
  tft.println("IT Infrastructure Monitor");
  
  // Draw separator line
  tft.drawFastHLine(0, 15, tft.width(), ST77XX_WHITE);
}

void showStartupScreen() {
  tft.fillScreen(ST77XX_BLACK);
  tft.setTextSize(1);  // Using smaller text size to fit all three lines
  tft.setTextColor(ST77XX_WHITE);
  
  // Calculate positions for all three lines
  int16_t x1, y1;
  uint16_t w, h;
  
  // First line: "IT"
  const char* line1 = "IT";
  tft.getTextBounds(line1, 0, 0, &x1, &y1, &w, &h);
  int16_t x = (tft.width() - w) / 2;
  int16_t y = (tft.height() / 2) - (h * 2); // Position above center
  
  tft.setCursor(x, y);
  tft.println(line1);
  
  // Second line: "Infrastructure"
  const char* line2 = "Infrastructure";
  tft.getTextBounds(line2, 0, 0, &x1, &y1, &w, &h);
  x = (tft.width() - w) / 2;
  y = (tft.height() / 2) - h; // Position at center
  
  tft.setCursor(x, y);
  tft.println(line2);
  
  // Third line: "Monitoring System"
  const char* line3 = "Monitoring System";
  tft.getTextBounds(line3, 0, 0, &x1, &y1, &w, &h);
  x = (tft.width() - w) / 2;
  y = (tft.height() / 2) + h; // Position below center
  
  tft.setCursor(x, y);
  tft.println(line3);
  
  delay(2000);
}

void connectToWiFi() {
  tft.fillScreen(ST77XX_BLACK);
  tft.setTextSize(1);
  tft.setTextColor(ST77XX_WHITE);
  tft.setCursor(5, 20);
  tft.print("Connecting to WiFi");
  
  WiFi.begin(ssid, password);
  int dots = 0;
  
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    tft.setCursor(5 + (dots * 6), 40);
    tft.print(".");
    dots = (dots + 1) % 20;
    if (dots == 0) {
      tft.fillRect(5, 40, 120, 10, ST77XX_BLACK);
    }
  }
  
  // Initialize mDNS
  if (MDNS.begin(deviceName)) {
    MDNS.addService("http", "tcp", 80);
    Serial.println("mDNS responder started");
    Serial.print("You can now connect to http://");
    Serial.print(deviceName);
    Serial.println(".local");
  } else {
    Serial.println("Error setting up mDNS responder!");
  }
  
  tft.fillScreen(ST77XX_BLACK);
  tft.setCursor(5, 30);
  tft.println("Connected!");
  tft.setCursor(5, 50);
  tft.print("IP: ");
  tft.println(WiFi.localIP());
  delay(2000);
}

void updateMetricsDisplay() {
  // Clear previous values
  tft.fillRect(0, 20, tft.width(), tft.height()-20, ST77XX_BLACK);
  
  tft.setTextSize(1);
  
  // CPU Temperature
  tft.setTextColor(ST77XX_WHITE);
  tft.setCursor(5, 25);
  tft.print("CPU Temp: ");
  if(cpu_temp_str != "N/A") {
    // Use CPU temperature threshold specifically
    uint16_t color;
    if (cpu_temp < settings.cpu_temp_threshold * 0.75) color = ST77XX_GREEN;
    else if (cpu_temp < settings.cpu_temp_threshold) color = ST77XX_YELLOW;
    else color = ST77XX_RED;
    
    tft.setTextColor(color);
    tft.print(cpu_temp_str);
    tft.print("C");
  } else {
    tft.print("N/A");
  }
  
  // CPU Usage
  tft.setTextColor(ST77XX_WHITE);
  tft.setCursor(5, 40);
  tft.print("CPU Usage: ");
  
  // Use CPU usage threshold specifically
  uint16_t cpuUsageColor;
  if (cpu_usage < settings.cpu_usage_threshold * 0.75) cpuUsageColor = ST77XX_GREEN;
  else if (cpu_usage < settings.cpu_usage_threshold) cpuUsageColor = ST77XX_YELLOW;
  else cpuUsageColor = ST77XX_RED;
  
  tft.setTextColor(cpuUsageColor);
  tft.print(cpu_usage, 1);
  tft.print("%");
  
  // RAM Usage
  tft.setCursor(5, 55);
  tft.setTextColor(ST77XX_WHITE);
  tft.print("RAM Usage: ");
  
  // Use RAM usage threshold specifically
  uint16_t ramUsageColor;
  if (ram_usage < settings.ram_usage_threshold * 0.75) ramUsageColor = ST77XX_GREEN;
  else if (ram_usage < settings.ram_usage_threshold) ramUsageColor = ST77XX_YELLOW;
  else ramUsageColor = ST77XX_RED;
  
  tft.setTextColor(ramUsageColor);
  tft.print(ram_usage, 1);
  tft.print("%");
  
  // GPU Temperature
  tft.setTextColor(ST77XX_WHITE);
  tft.setCursor(5, 70);
  tft.print("GPU Temp: ");
  if(gpu_temp_str != "N/A") {
    // Use GPU temperature threshold specifically
    uint16_t gpuTempColor;
    if (gpu_temp < settings.gpu_temp_threshold * 0.75) gpuTempColor = ST77XX_GREEN;
    else if (gpu_temp < settings.gpu_temp_threshold) gpuTempColor = ST77XX_YELLOW;
    else gpuTempColor = ST77XX_RED;
    
    tft.setTextColor(gpuTempColor);
    tft.print(gpu_temp_str);
    tft.print("C");
  } else {
    tft.print("N/A");
  }
  
  // GPU Usage
  tft.setCursor(5, 85);
  tft.setTextColor(ST77XX_WHITE);
  tft.print("GPU Usage: ");
  
  // Use GPU usage threshold specifically
  uint16_t gpuUsageColor;
  if (gpu_usage < settings.gpu_usage_threshold * 0.75) gpuUsageColor = ST77XX_GREEN;
  else if (gpu_usage < settings.gpu_usage_threshold) gpuUsageColor = ST77XX_YELLOW;
  else gpuUsageColor = ST77XX_RED;
  
  tft.setTextColor(gpuUsageColor);
  tft.print(gpu_usage, 1);
  tft.print("%");
  
  // Status display
  tft.setTextColor(ST77XX_WHITE);
  tft.setCursor(5, 100);
  tft.print("Last update: ");
  int seconds = (millis() - lastUpdateTime) / 1000;
  if (seconds < 60) {
    tft.print(seconds);
    tft.print("s ago");
  } else {
    tft.print(seconds / 60);
    tft.print("m ");
    tft.print(seconds % 60);
    tft.print("s ago");
  }
  
  // Alert status
  tft.setCursor(5, 115);
  tft.setTextColor(settings.notifications_enabled ? ST77XX_GREEN : ST77XX_RED);
  tft.print("Alerts: ");
  tft.print(settings.notifications_enabled ? "ON" : "OFF");
}

void showError(const char* error) {
  static String lastError;
  if (lastError != error) {
    tft.fillRect(0, 20, tft.width(), tft.height()-20, ST77XX_BLACK);
    updateMetricsWithNA();
    lastError = error;
  }
}

void updateMetricsWithNA() {
  tft.setTextSize(1);
  tft.setTextColor(ST77XX_WHITE);
  
  // CPU Temp
  tft.setCursor(5, 25);
  tft.print("CPU Temp: N/A");
  
  // CPU Usage
  tft.setCursor(5, 40);
  tft.print("CPU Usage: N/A");
  
  // RAM Usage
  tft.setCursor(5, 55);
  tft.print("RAM Usage: N/A");
  
  // GPU Temp
  tft.setCursor(5, 70);
  tft.print("GPU Temp: N/A");
  
  // GPU Usage
  tft.setCursor(5, 85);
  tft.print("GPU Usage: N/A");
  
  // Status
  tft.setCursor(5, 100);
  tft.print("Connection lost");
}

void loop() {
  server.handleClient();
  
  // Check if we've lost connection to the PC
  if (millis() - lastUpdateTime > 10000) { // 10 seconds timeout
    showError("No data from PC");
  }
  
  // Allow the CPU to perform other tasks
  delay(10);
}