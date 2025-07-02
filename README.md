# Kea-Lease-Manager
Simple KEA DHCP server leases manager writen by Python running on OpenWRT / or any Router you use kea-dhcp4 as DHCP server

I just switch to use from ISC DHCP to Kea DHCP on OpenWRT and unfortunately there no webgui app to see which IP has been leased and which machine get the IP to put into static IP

So, with the help of Deepseek and Claud AI, i created this simple python app to run on OpenWRT / or any Router you use kea-dhcp4 as DHCP server

## Requirements

You just need to have Python3 installed, my current is Python 3.10.13 but i assummed any Python3 can run

```
root@OpenWrt:~/kea-lease-manager# python --version
Python 3.10.13
```

## Prepare the app
clone the repo to your router 
```bash
git clone https://github.com/thanhtantran/kea-lease-manager
cd kea-lease-manager
```
or if you don't have git installed, simply download 2 file `lease_manager.py` then put into your router

## Run the app
```bash
root@OpenWrt:~/kea-lease-manager# python lease_manager.py
Starting Enhanced Kea DHCP Lease Manager...
Reading lease file: /tmp/kea-leases4.csv
Web interface will be available at http://0.0.0.0:5001

New Features:
- 🔍 Real-time search/filter functionality
- 📊 Subnet information display
- 📜 Lease history for each IP
- 🚫 Duplicate lease elimination
- 📈 Enhanced statistics
- 🎨 Improved responsive design
 * Serving Flask app 'lease_manager'
 * Debug mode: off
WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5001
 * Running on http://192.168.88.10:5001
Press CTRL+C to quit
192.168.20.100 - - [02/Jul/2025 13:14:19] "GET /refresh HTTP/1.1" 200 -
192.168.20.100 - - [02/Jul/2025 13:14:50] "GET /refresh HTTP/1.1" 200 -
192.168.20.100 - - [02/Jul/2025 13:15:21] "GET /refresh HTTP/1.1" 200 -
192.168.20.100 - - [02/Jul/2025 13:15:52] "GET /refresh HTTP/1.1" 200 -
```

then go to your router IP with port 5001 to check
![kea-lease-manager](https://github.com/user-attachments/assets/7e7e48aa-9cf8-4bbf-afa9-4d7f29d4f3db)

If you want the app start at startup, simply create an init script using procd, which is OpenWrt's process management daemon. Here’s how to do it:

### Step 1: Create an init script
Create a new file at /etc/init.d/kea-lease-manager:

```bash
vi /etc/init.d/kea-lease-manager
```
Paste the following content (adjust paths as needed):

```text
#!/bin/sh /etc/rc.common
# Init script for KEA Lease Manager

START=99
STOP=10

USE_PROCD=1
PROG=/usr/bin/python3
NAME="kea-lease-manager"
APP_DIR="/root/kea-lease-manager"
APP_CMD="lease_manager.py"

start_service() {
    procd_open_instance
    procd_set_param command "$PROG" "$APP_DIR/$APP_CMD"
    procd_set_param respawn  # Restart if it crashes
    procd_set_param stdout 1  # Redirect stdout to log
    procd_set_param stderr 1  # Redirect stderr to log
    procd_set_param env FLASK_APP="$APP_DIR/$APP_CMD"
    procd_close_instance
}

stop_service() {
    killall "$NAME" 2>/dev/null
}

restart() {
    stop
    start
}
```
Explanation:
- START=99 → Starts late in the boot process (after networking is up).
- USE_PROCD=1 → Uses OpenWrt's modern process manager (procd).
- PROG → Path to Python (/usr/bin/python3).
- APP_DIR → Directory where lease_manager.py is located.
- APP_CMD → Your Flask script.
- respawn → Automatically restarts the app if it crashes.
- stdout/stderr → Logs output to syslog.

### Step 2: Make the script executable

```bash
chmod +x /etc/init.d/kea-lease-manager
```

### Step 3: Enable the service to start at boot
```bash
/etc/init.d/kea-lease-manager enable
```

### Step 4: Start the service manually (no need to reboot yet)
```bash
/etc/init.d/kea-lease-manager start
```

### Step 5: Verify it’s running

Check logs:

```bash
logread | grep "kea-lease-manager"
```
Check process:

```bash
ps | grep "lease_manager.py"
```

Fell free to fork and edit or upgrade the app in any way you want.
