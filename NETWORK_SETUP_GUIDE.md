# Raspberry Pi Network Setup Guide

**Hardware Setup with Network Hub/Switch**

---

## Network Architecture

### Option 1: Hub/Switch with NVIDIA as Gateway (Recommended)

```
┌─────────────────────────────────────────────────────────┐
│                   Parking Lot Network                   │
│                                                         │
│  ┌──────────────────────────────────────────┐          │
│  │  Network Switch (PoE Enabled)            │          │
│  │  - 8-16 ports                            │          │
│  │  - PoE+ (802.3at) for powering Pi's     │          │
│  └───┬────┬────┬────┬────┬────┬────┬───────┘          │
│      │    │    │    │    │    │    │                   │
│      │    │    │    │    │    │    └─── To Router/SIM │
│      │    │    │    │    │    │                        │
│   ┌──┴─┐ ┌┴──┐ ┌┴──┐ ┌┴──┐ ┌┴──┐ ┌┴────────┐         │
│   │ Pi │ │Pi │ │Pi │ │Pi │ │Pi │ │ NVIDIA  │         │
│   │ #1 │ │#2 │ │#3 │ │#4 │ │#5 │ │  Orin   │         │
│   └────┘ └───┘ └───┘ └───┘ └───┘ └────┬────┘         │
│   Spot    Spot  Spot  Spot  Spot       │              │
│    12     13    14    15    16         │              │
│                                         │              │
│                                         ▼              │
│                                    Internet/Cloud      │
│                                    (4G/5G SIM)        │
└─────────────────────────────────────────────────────────┘
```

**Network Configuration:**
- **Switch:** Acts as local network hub
- **Raspberry Pis:** LAN IP range `192.168.1.101-192.168.1.1XX`
- **NVIDIA Orin:** LAN IP `192.168.1.100` (gateway to internet)
- **Internet:** NVIDIA has 4G/5G SIM card for cloud connectivity

---

## Recommended Hardware

### Network Switch
**Option 1: PoE+ Gigabit Switch (Best)**
- **Model:** TP-Link TL-SG1008P or Netgear GS308P
- **Ports:** 8-16 ports (depending on parking spots)
- **PoE:** 802.3at (25W per port) - powers Raspberry Pi + accessories
- **Speed:** Gigabit (1000 Mbps)
- **Cost:** ~$80-150

**Option 2: Non-PoE Switch (Budget)**
- **Model:** TP-Link TL-SG108 or Netgear GS308
- **Ports:** 8-16 ports
- **Power:** Each Pi needs separate USB-C power adapter
- **Speed:** Gigabit (1000 Mbps)
- **Cost:** ~$25-40

### Raspberry Pi PoE HAT (if using PoE switch)
- **Model:** Official Raspberry Pi PoE+ HAT
- **Power:** Draws power from Ethernet cable
- **Fan:** Built-in cooling fan
- **Cost:** ~$20 per unit
- **Benefit:** No need for separate power adapters!

### Ethernet Cables
- **Type:** Cat6 or Cat5e
- **Length:** Based on parking lot layout (typically 10-30 meters)
- **Quantity:** 1 per Raspberry Pi + 1 for NVIDIA
- **Cost:** ~$1-3 per cable

---

## IP Address Assignment

### Static IP Configuration

Each Raspberry Pi and NVIDIA device should have a **static IP** to ensure consistent communication.

#### IP Address Table

| Device | IP Address | Spot Number | Purpose |
|--------|-----------|-------------|---------|
| NVIDIA Orin | `192.168.1.100` | N/A | Central processing + gateway |
| Raspberry Pi #1 | `192.168.1.101` | 12 | Camera spot #12 |
| Raspberry Pi #2 | `192.168.1.102` | 13 | Camera spot #13 |
| Raspberry Pi #3 | `192.168.1.103` | 14 | Camera spot #14 |
| Raspberry Pi #4 | `192.168.1.104` | 15 | Camera spot #15 |
| Raspberry Pi #5 | `192.168.1.105` | 16 | Camera spot #16 |
| ... | ... | ... | ... |

**Pattern:** `192.168.1.1XX` where XX = spot number + 89
- Spot 12 → `.101`
- Spot 13 → `.102`
- etc.

---

## Raspberry Pi Network Configuration

### Method 1: Using dhcpcd (Recommended)

**Step 1:** SSH into Raspberry Pi
```bash
ssh pi@raspberrypi.local
# Default password: raspberry (change immediately!)
```

**Step 2:** Edit dhcpcd configuration
```bash
sudo nano /etc/dhcpcd.conf
```

**Step 3:** Add static IP configuration
```bash
# Add at the end of the file:

interface eth0
static ip_address=192.168.1.101/24
static routers=192.168.1.100
static domain_name_servers=8.8.8.8 8.8.4.4
```

**Change `192.168.1.101` to the correct IP for each Pi!**

**Step 4:** Reboot
```bash
sudo reboot
```

**Step 5:** Verify
```bash
hostname -I
# Should show: 192.168.1.101 (or your assigned IP)
```

---

### Method 2: Using NetworkManager (Alternative)

```bash
sudo nmcli con mod "Wired connection 1" ipv4.addresses 192.168.1.101/24
sudo nmcli con mod "Wired connection 1" ipv4.gateway 192.168.1.100
sudo nmcli con mod "Wired connection 1" ipv4.dns "8.8.8.8 8.8.4.4"
sudo nmcli con mod "Wired connection 1" ipv4.method manual
sudo nmcli con up "Wired connection 1"
```

---

## NVIDIA Orin Network Configuration

NVIDIA acts as the gateway between local Raspberry Pi network and internet.

### Two Network Interfaces

**eth0 (Local Network):** Connects to switch
- IP: `192.168.1.100`
- Subnet: `255.255.255.0`
- Purpose: Receive images from Raspberry Pis

**wwan0 or usb0 (Internet):** 4G/5G SIM modem
- IP: DHCP from carrier
- Purpose: Send data to cloud backend

### Configuration

**Step 1:** Configure local network interface
```bash
# Edit netplan configuration
sudo nano /etc/netplan/01-network-manager-all.yaml
```

**Step 2:** Add configuration
```yaml
network:
  version: 2
  renderer: NetworkManager
  ethernets:
    eth0:
      dhcp4: no
      addresses:
        - 192.168.1.100/24
      nameservers:
        addresses: [8.8.8.8, 8.8.4.4]
```

**Step 3:** Apply configuration
```bash
sudo netplan apply
```

**Step 4:** Enable IP forwarding (for internet sharing)
```bash
sudo nano /etc/sysctl.conf

# Uncomment this line:
net.ipv4.ip_forward=1

# Apply changes
sudo sysctl -p
```

**Step 5:** Configure NAT for internet sharing
```bash
# Allow Raspberry Pis to access internet through NVIDIA
sudo iptables -t nat -A POSTROUTING -o wwan0 -j MASQUERADE
sudo iptables -A FORWARD -i eth0 -o wwan0 -j ACCEPT
sudo iptables -A FORWARD -i wwan0 -o eth0 -m state --state RELATED,ESTABLISHED -j ACCEPT

# Save rules
sudo apt install iptables-persistent
sudo netfilter-persistent save
```

---

## Physical Installation Guide

### Step-by-Step Setup

#### 1. Plan Cable Routes
- Measure distances from switch to each parking spot
- Consider weatherproofing for outdoor installations
- Use cable conduits or raceways

#### 2. Install Network Switch
- Mount in weatherproof enclosure (if outdoor)
- Connect to power
- Ensure ventilation for cooling

#### 3. Install Raspberry Pi Cameras
- Mount camera above each parking spot
- Attach VL53L1X ToF sensor
- Connect PoE HAT (if using PoE)
- Run Ethernet cable from switch to Pi

#### 4. Install NVIDIA Orin
- Central location with good airflow
- Connect to switch via Ethernet
- Insert 4G/5G SIM card
- Connect power supply

#### 5. Cable Management
- Label each cable with spot number
- Use cable ties and organizers
- Document cable paths

---

## Network Testing

### Test 1: Raspberry Pi to NVIDIA Connection

**On Raspberry Pi:**
```bash
# Ping NVIDIA
ping 192.168.1.100

# Expected output:
# 64 bytes from 192.168.1.100: icmp_seq=1 ttl=64 time=0.5 ms
```

**On NVIDIA:**
```bash
# Ping Raspberry Pi
ping 192.168.1.101

# Expected output:
# 64 bytes from 192.168.1.101: icmp_seq=1 ttl=64 time=0.5 ms
```

### Test 2: Internet Connectivity

**On Raspberry Pi (through NVIDIA):**
```bash
ping 8.8.8.8

# Expected output:
# 64 bytes from 8.8.8.8: icmp_seq=1 ttl=114 time=25 ms
```

### Test 3: Image Transfer

**On Raspberry Pi:**
```bash
# Test image upload to NVIDIA
curl -X POST http://192.168.1.100:8090/receive_image \
  -F "image=@test.jpg" \
  -F "station_id=rasberrysmoothbox01" \
  -F "spot_number=12" \
  -F "timestamp=$(date -Iseconds)"

# Expected: 200 OK response
```

### Test 4: Name Resolution

**On Raspberry Pi:**
```bash
# Test DNS resolution
nslookup google.com

# Expected: Should resolve to IP address
```

---

## Configuration Files

### Raspberry Pi: /etc/dhcpcd.conf
```bash
# Interface configuration
interface eth0
static ip_address=192.168.1.101/24
static routers=192.168.1.100
static domain_name_servers=8.8.8.8 8.8.4.4
```

### Raspberry Pi: config.yaml
```yaml
device:
  station_id: "rasberrysmoothbox01"
  spot_number: 12

nvidia:
  ip_address: "192.168.1.100"  # NVIDIA local IP
  port: 8090
  protocol: "http"
  endpoint: "/receive_image"
```

### NVIDIA: config.yaml
```yaml
parking_lot:
  id: "123e4567-e89b-12d3-a456-426614174000"

cameras:
  - station_id: "rasberrysmoothbox01"
    ip_address: "192.168.1.101"
    spot_number: 12
    enabled: true

  - station_id: "rasberrysmoothbox02"
    ip_address: "192.168.1.102"
    spot_number: 13
    enabled: true

  # Add more cameras as needed
```

---

## Security Considerations

### 1. Change Default Passwords
```bash
# On each Raspberry Pi
passwd
# Change from default "raspberry" to strong password
```

### 2. SSH Key Authentication
```bash
# Generate SSH key on your admin computer
ssh-keygen -t ed25519

# Copy to each Raspberry Pi
ssh-copy-id pi@192.168.1.101
ssh-copy-id pi@192.168.1.102
# etc.

# Disable password authentication
sudo nano /etc/ssh/sshd_config
# Set: PasswordAuthentication no
sudo systemctl restart ssh
```

### 3. Firewall Rules

**On NVIDIA (allow only necessary ports):**
```bash
sudo ufw enable
sudo ufw allow from 192.168.1.0/24 to any port 8090  # Image reception
sudo ufw allow 22  # SSH
sudo ufw allow 443  # HTTPS to cloud
```

**On Raspberry Pi:**
```bash
sudo ufw enable
sudo ufw allow from 192.168.1.100 to any port 22  # SSH from NVIDIA only
```

---

## Troubleshooting

### Issue: Raspberry Pi can't reach NVIDIA

**Check:**
```bash
# Verify IP address
ip addr show eth0

# Check cable connection
ethtool eth0 | grep "Link detected"
# Should show: Link detected: yes

# Check routing table
ip route
# Should show default via 192.168.1.100
```

**Fix:**
```bash
# Restart networking
sudo systemctl restart dhcpcd
# or
sudo systemctl restart NetworkManager
```

### Issue: No internet on Raspberry Pi

**Check:**
```bash
# Can you reach NVIDIA?
ping 192.168.1.100

# Can NVIDIA reach internet?
# (SSH to NVIDIA first)
ping 8.8.8.8

# Check NAT is enabled on NVIDIA
sudo iptables -t nat -L
# Should show MASQUERADE rule
```

### Issue: PoE not powering Raspberry Pi

**Check:**
- PoE HAT is properly connected to GPIO pins
- Switch supports 802.3at (PoE+), not just 802.3af
- Cable is Cat5e or better (Cat3 won't work)
- PoE is enabled on switch port

---

## Scalability

### Adding More Cameras

**Step 1:** Assign IP address
```
Next available: 192.168.1.106
Spot number: 17
```

**Step 2:** Configure new Raspberry Pi
```bash
# Set static IP
sudo nano /etc/dhcpcd.conf
# Add: static ip_address=192.168.1.106/24
```

**Step 3:** Update config.yaml
```yaml
device:
  station_id: "rasberrysmoothbox06"
  spot_number: 17
```

**Step 4:** Add to NVIDIA config
```yaml
cameras:
  - station_id: "rasberrysmoothbox06"
    ip_address: "192.168.1.106"
    spot_number: 17
    enabled: true
```

**Step 5:** Restart services

---

## Power Consumption Estimate

### With PoE (Recommended)

| Device | Power Draw | Quantity | Total |
|--------|-----------|----------|-------|
| Raspberry Pi Zero 2 W | 3-5W | 10 | 50W |
| Camera Module | 1-2W | 10 | 20W |
| ToF Sensor | 0.5W | 10 | 5W |
| **Total per 10 spots** | | | **~75W** |
| PoE Switch | 10W | 1 | 10W |
| **Grand Total** | | | **85W** |

### Without PoE

| Device | Power Draw | Power Supply |
|--------|-----------|--------------|
| Raspberry Pi + accessories | 5-7W | USB-C 5V/3A |
| Switch | 10W | AC adapter |

---

## Cost Estimate

### For 10 Parking Spots

| Item | Quantity | Unit Price | Total |
|------|----------|-----------|-------|
| Raspberry Pi Zero 2 W | 10 | $15 | $150 |
| Camera Module v2 | 10 | $25 | $250 |
| VL53L1X ToF Sensor | 10 | $15 | $150 |
| PoE HAT | 10 | $20 | $200 |
| PoE Switch (8-port) | 2 | $100 | $200 |
| Cat6 Cable (avg 20m) | 10 | $10 | $100 |
| Weatherproof enclosures | 10 | $15 | $150 |
| Miscellaneous (mounts, etc) | - | - | $100 |
| **Total** | | | **~$1,300** |

**Per parking spot:** ~$130

---

## Maintenance

### Monthly Checks
- [ ] Verify all cameras online (`ping` sweep)
- [ ] Check switch status LEDs
- [ ] Review NVIDIA logs for connection issues
- [ ] Test internet connectivity

### Software Updates
```bash
# On each Raspberry Pi (can be automated)
sudo apt update && sudo apt upgrade -y
```

### Automated Health Monitoring

Create a script on NVIDIA to ping all Raspberry Pis:

```bash
#!/bin/bash
# /opt/smoothbox/check_cameras.sh

for ip in {101..110}; do
    if ping -c 1 -W 1 192.168.1.$ip > /dev/null; then
        echo "✓ 192.168.1.$ip is online"
    else
        echo "✗ 192.168.1.$ip is OFFLINE"
        # Send alert
    fi
done
```

---

## Summary

**Recommended Setup:**
- ✅ PoE+ Gigabit Switch (8-16 ports)
- ✅ Raspberry Pi with PoE HAT (one per spot)
- ✅ Static IP addresses (`192.168.1.101-1.1XX`)
- ✅ NVIDIA as gateway with 4G/5G SIM
- ✅ Cat6 Ethernet cables

**Benefits:**
- Single power source (PoE)
- Reliable Gigabit connection
- Easy to scale (just add more Pis)
- Centralized internet via NVIDIA

**Next Steps:**
1. Purchase equipment
2. Set up test bench with 2-3 Pis
3. Verify image transfer works
4. Deploy to production parking lot
