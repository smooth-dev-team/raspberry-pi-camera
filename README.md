# SmoothBox Raspberry Pi Camera

Raspberry Pi Zero 2 W camera system with VL53L1X Time-of-Flight sensor integration for intelligent parking detection.

---
aa
## Overview

Each Raspberry Pi Zero 2 W:
- **Monitors one parking spot** (車庫)
- **Captures images** from Raspberry Pi Camera Module
- **Reads distance** from VL53L1X ToF sensor
- **Sends images + spot_number** to NVIDIA Jetson Orin for license plate detection
- **Implements event-based triggering** (entry, exit, verification)

---

## Hardware Requirements

### Required Components

1. **Raspberry Pi Zero 2 W**
   - 1GB RAM
   - WiFi/Ethernet connectivity
   - Raspberry Pi OS Lite (64-bit recommended)

2. **Raspberry Pi Camera Module**
   - Camera Module v2 (8MP) or v3 (12MP)
   - 15-pin ribbon cable

3. **VL53L1X Time-of-Flight Sensor**
   - Model: VL53L1X Time-of-Flight STM32 (ToF) Laser Ranging Sensor
   - I2C interface
   - Range: up to 4 meters
   - Purchase: [Pimoroni VL53L1X](https://shop.pimoroni.com/products/vl53l1x-breakout)

4. **Power Supply**
   - 5V 2.5A USB-C power adapter
   - Or PoE HAT for Power over Ethernet

5. **Network Connection**
   - LAN cable (recommended)
   - Or WiFi

### Wiring Diagram

```
VL53L1X Sensor → Raspberry Pi GPIO
---------------------------------
VIN     → Pin 1  (3.3V)
GND     → Pin 6  (Ground)
SCL     → Pin 5  (GPIO 3 / I2C SCL)
SDA     → Pin 3  (GPIO 2 / I2C SDA)
```

---

## Installation

### Step 1: Prepare Raspberry Pi OS

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3 and pip
sudo apt install python3 python3-pip -y

# Install system dependencies
sudo apt install python3-picamera2 python3-yaml python3-pil -y

# Enable I2C for ToF sensor
sudo raspi-config
# → Interface Options → I2C → Enable

# Reboot
sudo reboot
```

### Step 2: Install Python Dependencies

```bash
# Clone repository (or copy files)
cd /opt/smoothbox
sudo mkdir -p /opt/smoothbox/camera
cd /opt/smoothbox/camera

# Copy files:
# - main.py
# - config.yaml
# - requirements.txt

# Install Python packages
pip3 install -r requirements.txt

# Install VL53L1X library
pip3 install git+https://github.com/pimoroni/vl53l1x-python
```

### Step 3: Configure Device

Edit `config.yaml`:

```yaml
device:
  station_id: "rasberrysmoothbox01"  # ← Change this
  spot_number: 12                     # ← Change to your spot number

nvidia:
  ip_address: "192.168.1.100"  # ← NVIDIA Jetson Orin IP
  port: 8090
```

**Important Settings:**
- `device.spot_number`: The parking spot number this camera monitors (1-9999)
- `device.station_id`: Unique identifier for this Raspberry Pi
- `nvidia.ip_address`: IP address of the NVIDIA Jetson Orin device

### Step 4: Test Hardware

```bash
# Test camera
libcamera-hello

# Test ToF sensor
python3 -c "
import VL53L1X
tof = VL53L1X.VL53L1X(i2c_bus=1, i2c_address=0x29)
tof.open()
tof.start_ranging(1)
print(f'Distance: {tof.get_distance()}mm')
tof.stop_ranging()
tof.close()
"
```

### Step 5: Run the Application

```bash
# Test run
python3 main.py

# Expected output:
# [INFO] SmoothBoxCamera: Camera initialized - Station: rasberrysmoothbox01 | Spot: 12
# [INFO] ToFSensor: ToF sensor initialized on I2C bus 1
# [INFO] CameraHandler: Raspberry Pi camera initialized
# [INFO] NVIDIAClient: NVIDIA client configured: http://192.168.1.100:8090/receive_image
# [INFO] SmoothBoxCamera: All systems operational
```

---

## How It Works

### Event-Based Detection

The system uses the VL53L1X ToF sensor to detect vehicle presence and trigger image capture:

#### 1. Entry Event (Vehicle Arrives)
```
ToF Distance: >2000mm → <1000mm
Action: Send images for 3 minutes (1 image/second)
Purpose: Capture license plate during entry
```

#### 2. Exit Event (Vehicle Leaves)
```
ToF Distance: <1000mm → >2000mm
Action: Send 1 immediate image
Purpose: Confirm vehicle has left
```

#### 3. Periodic Verification (Vehicle Parked)
```
ToF Distance: Stays <1000mm
Action: Every 5 minutes, send images for 10 seconds
Purpose: Verify vehicle is still parked
```

### Data Sent to NVIDIA

Each image is sent with:

```json
{
  "image": "<JPEG binary data>",
  "station_id": "rasberrysmoothbox01",
  "spot_number": 12,
  "timestamp": "2024-11-10T10:00:00Z"
}
```

NVIDIA receives this, runs YOLOv11 detection, and includes `spot_number` in the backend API payload.

---

## Configuration Reference

### Distance Thresholds

```yaml
tof_sensor:
  thresholds:
    vehicle_present_mm: 1000  # Below this = vehicle present
    vehicle_absent_mm: 2000   # Above this = vehicle absent
```

**Calibration Tips:**
- Empty spot: Sensor should read >2000mm
- Vehicle parked: Sensor should read <1000mm
- Adjust thresholds based on spot height and vehicle types

### Entry Capture Settings

```yaml
tof_sensor:
  triggers:
    entry_event:
      enabled: true
      send_duration_seconds: 180  # 3 minutes
      send_interval_seconds: 1     # 1 image/second
```

**Why 3 minutes?**
- Vehicles take time to fully enter and park
- Multiple angles ensure at least one clear plate image
- NVIDIA's confirmation system (on NVIDIA side) requires 5+ detections over 3 minutes

### Periodic Verification

```yaml
tof_sensor:
  triggers:
    periodic_check:
      enabled: true
      interval_seconds: 300  # Every 5 minutes
      send_duration_seconds: 10
      send_interval_seconds: 1
```

**Purpose:**
- Heartbeat to backend confirming vehicle still parked
- Prevents false exit detection
- Backend uses this for session timeout logic

---

## systemd Service (Auto-Start)

Create `/etc/systemd/system/smoothbox-camera.service`:

```ini
[Unit]
Description=SmoothBox Raspberry Pi Camera
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/opt/smoothbox/camera
ExecStart=/usr/bin/python3 /opt/smoothbox/camera/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Enable and start:**

```bash
sudo systemctl enable smoothbox-camera
sudo systemctl start smoothbox-camera

# Check status
sudo systemctl status smoothbox-camera

# View logs
sudo journalctl -u smoothbox-camera -f
```

---

## Troubleshooting

### Camera Not Working

```bash
# Check camera is enabled
sudo raspi-config
# → Interface Options → Legacy Camera → Disable
# → Interface Options → Camera → Enable

# Test camera
libcamera-hello --list-cameras

# Check picamera2 installation
python3 -c "from picamera2 import Picamera2; print('OK')"
```

### ToF Sensor Not Detected

```bash
# Check I2C is enabled
sudo raspi-config
# → Interface Options → I2C → Enable

# Scan I2C bus (should show 0x29)
sudo i2cdetect -y 1

# Expected output:
#      0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
# 00:          -- -- -- -- -- -- -- -- -- -- -- -- --
# 10: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
# 20: -- -- -- -- -- -- -- -- -- 29 -- -- -- -- -- --
# ...
```

### NVIDIA Not Receiving Images

```bash
# Check network connectivity
ping 192.168.1.100

# Check NVIDIA endpoint is running
curl http://192.168.1.100:8090/receive_image

# Check logs
sudo journalctl -u smoothbox-camera -f | grep "Image sent"
```

### Distance Readings Incorrect

```bash
# Test ToF sensor manually
python3 -c "
import VL53L1X
import time
tof = VL53L1X.VL53L1X(i2c_bus=1, i2c_address=0x29)
tof.open()
tof.start_ranging(1)
for i in range(10):
    print(f'Distance: {tof.get_distance()}mm')
    time.sleep(0.5)
tof.stop_ranging()
tof.close()
"

# If readings are noisy, increase smoothing_window in config.yaml
```

---

## Multiple Cameras on Same Network

If you have multiple Raspberry Pi cameras on the same parking lot:

| Device | Spot Number | IP Address | Station ID |
|--------|-------------|------------|------------|
| RPi 1 | 12 | 192.168.1.101 | rasberrysmoothbox01 |
| RPi 2 | 13 | 192.168.1.102 | rasberrysmoothbox02 |
| RPi 3 | 14 | 192.168.1.103 | rasberrysmoothbox03 |

All send to same NVIDIA Jetson Orin (e.g., 192.168.1.100).

**NVIDIA Configuration:**

```yaml
# NVIDIA config.yaml
cameras:
  - station_id: "rasberrysmoothbox01"
    ip_address: "192.168.1.101"
    spot_number: 12

  - station_id: "rasberrysmoothbox02"
    ip_address: "192.168.1.102"
    spot_number: 13

  - station_id: "rasberrysmoothbox03"
    ip_address: "192.168.1.103"
    spot_number: 14
```

---

## Performance Optimization

### Reduce Image Size

```yaml
camera:
  resolution:
    width: 1280  # Reduce from 1920
    height: 720  # Reduce from 1080
  quality: 70    # Reduce from 85
```

Lower resolution = faster transmission, but may affect plate detection accuracy. Test with your YOLOv11 model.

### Adjust Capture Frequency

```yaml
# Entry: Send fewer images
entry_event:
  send_duration_seconds: 120  # Reduce from 180
  send_interval_seconds: 2     # Increase from 1

# Verification: Send less frequently
periodic_check:
  interval_seconds: 600  # Increase from 300 (10 minutes instead of 5)
```

---

## Architecture Diagram

```
┌─────────────────────────────────┐
│  Raspberry Pi Zero 2 W          │
│  (Spot #12)                     │
│                                 │
│  ┌──────────┐   ┌────────────┐ │
│  │  Camera  │   │ VL53L1X    │ │
│  │  Module  │   │ ToF Sensor │ │
│  └────┬─────┘   └─────┬──────┘ │
│       │               │        │
│  ┌────┴───────────────┴──────┐ │
│  │   main.py                 │ │
│  │   - Captures images       │ │
│  │   - Reads ToF distance    │ │
│  │   - Detects entry/exit    │ │
│  └───────────┬───────────────┘ │
└──────────────┼─────────────────┘
               │ HTTP POST
               │ image + spot_number
               ▼
┌──────────────────────────────────┐
│  NVIDIA Jetson Orin              │
│  (Central Processing)            │
│                                  │
│  ┌────────────────────────────┐  │
│  │  camera_handler.py         │  │
│  │  - Receives images         │  │
│  │  - Extracts spot_number    │  │
│  └─────────┬──────────────────┘  │
│            ▼                     │
│  ┌────────────────────────────┐  │
│  │  detector.py (YOLOv11)     │  │
│  │  - Detects license plate   │  │
│  └─────────┬──────────────────┘  │
│            ▼                     │
│  ┌────────────────────────────┐  │
│  │  confirmation.py           │  │
│  │  - Confirms plate          │  │
│  │  - Adds spot_number        │  │
│  └─────────┬──────────────────┘  │
└────────────┼────────────────────┘
             │ HTTPS POST
             │ payload + spot_number
             ▼
┌────────────────────────────────┐
│  AWS Cloud Backend              │
│  - Creates parking session     │
│  - Associates with spot #12    │
│  - Processes payment           │
└────────────────────────────────┘
```

---

## Security Notes

1. **Network Security**
   - Use private LAN for Raspberry Pi ↔ NVIDIA communication
   - NVIDIA ↔ Backend uses HTTPS + API keys

2. **Physical Security**
   - Mount Raspberry Pi in weatherproof enclosure
   - Protect camera lens from weather

3. **Data Privacy**
   - Images are sent to NVIDIA, not stored on Raspberry Pi
   - NVIDIA processes and sends only plate data to backend
   - No raw images sent to cloud

---

## Support

**Documentation:**
- NVIDIA Integration: [../Smooth-ML-NvidiaOrin/docs/](../Smooth-ML-NvidiaOrin/docs/)
- API Payload Spec: [../Smooth-ML-NvidiaOrin/docs/API_PAYLOAD_SPEC.md](../Smooth-ML-NvidiaOrin/docs/API_PAYLOAD_SPEC.md)
- System Architecture: [../config/Infrastructure.md](../config/Infrastructure.md)

**Hardware:**
- VL53L1X Datasheet: https://www.st.com/resource/en/datasheet/vl53l1x.pdf
- Raspberry Pi Camera Guide: https://www.raspberrypi.com/documentation/accessories/camera.html

**Logs:**
```bash
sudo journalctl -u smoothbox-camera -f
```
