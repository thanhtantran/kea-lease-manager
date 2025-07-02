#!/usr/bin/env python3

from flask import Flask, render_template, request, jsonify
import csv
import json
import os
import re
from datetime import datetime
from flask_moment import Moment

app = Flask(__name__)
moment = Moment(app)

# Configuration
LEASE_FILE = "/tmp/kea-leases4.csv"
KEA_CONFIG_FILE = "/etc/kea/kea-dhcp4.conf"

def read_lease_file():
    """Read and parse the Kea lease file, handling duplicates"""
    leases = []
    lease_dict = {}  # Dictionary to track most recent lease per IP
    
    if not os.path.exists(LEASE_FILE):
        return leases, f"Lease file not found: {LEASE_FILE}"
    
    try:
        with open(LEASE_FILE, 'r') as f:
            # Skip the header line and read CSV
            reader = csv.DictReader(f)
            for row in reader:
                # Only include active leases (state 0 = default/active)
                if row.get('address') and row.get('state', '0') == '0':
                    ip_address = row.get('address', '')
                    expire_ts = row.get('expire', '0')
                    
                    # Convert expire timestamp to readable date
                    if expire_ts and expire_ts != '0':
                        try:
                            expire_date = datetime.fromtimestamp(int(expire_ts)).strftime('%Y-%m-%d %H:%M:%S')
                            expire_timestamp = int(expire_ts)
                        except:
                            expire_date = 'Invalid date'
                            expire_timestamp = 0
                    else:
                        expire_date = 'No expiration'
                        expire_timestamp = 0
                    
                    lease_data = {
                        'ip': ip_address,
                        'mac': row.get('hwaddr', ''),
                        'hostname': row.get('hostname', ''),
                        'expire': expire_date,
                        'expire_ts': expire_ts,
                        'expire_timestamp': expire_timestamp,
                        'subnet_id': row.get('subnet_id', ''),
                        'client_id': row.get('client_id', ''),
                        'valid_lifetime': row.get('valid_lifetime', ''),
                        'state': row.get('state', '0')
                    }
                    
                    # Keep only the lease with the latest expiration time for each IP
                    if ip_address not in lease_dict or expire_timestamp > lease_dict[ip_address]['expire_timestamp']:
                        lease_dict[ip_address] = lease_data
        
        # Convert dictionary back to list
        leases = list(lease_dict.values())
        
        # Sort by IP address
        leases.sort(key=lambda x: tuple(map(int, x['ip'].split('.'))))
        return leases, None
        
    except Exception as e:
        return [], f"Error reading lease file: {str(e)}"

def get_lease_history(target_ip):
    """Get all lease entries for a specific IP address"""
    history = []
    
    if not os.path.exists(LEASE_FILE):
        return history, f"Lease file not found: {LEASE_FILE}"
    
    try:
        with open(LEASE_FILE, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('address') == target_ip:
                    expire_ts = row.get('expire', '0')
                    if expire_ts and expire_ts != '0':
                        try:
                            expire_date = datetime.fromtimestamp(int(expire_ts)).strftime('%Y-%m-%d %H:%M:%S')
                        except:
                            expire_date = 'Invalid date'
                    else:
                        expire_date = 'No expiration'
                    
                    history.append({
                        'ip': row.get('address', ''),
                        'mac': row.get('hwaddr', ''),
                        'hostname': row.get('hostname', ''),
                        'expire': expire_date,
                        'expire_ts': expire_ts,
                        'subnet_id': row.get('subnet_id', ''),
                        'state': row.get('state', ''),
                        'valid_lifetime': row.get('valid_lifetime', '')
                    })
        
        # Sort by expiration timestamp (most recent first)
        history.sort(key=lambda x: int(x.get('expire_ts', '0')), reverse=True)
        return history, None
        
    except Exception as e:
        return [], f"Error reading lease file: {str(e)}"

def get_subnet_info():
    """Extract subnet information from Kea config file"""
    subnets = {}
    
    try:
        if os.path.exists(KEA_CONFIG_FILE):
            with open(KEA_CONFIG_FILE, 'r') as f:
                config_content = f.read()
                # Try to parse as JSON first
                try:
                    config_json = json.loads(config_content)
                    if 'Dhcp4' in config_json and 'subnet4' in config_json['Dhcp4']:
                        for subnet in config_json['Dhcp4']['subnet4']:
                            subnet_id = str(subnet.get('id', ''))
                            subnet_range = subnet.get('subnet', '')
                            if subnet_id and subnet_range:
                                subnets[subnet_id] = subnet_range
                except json.JSONDecodeError:
                    # Fallback to regex parsing
                    subnet_pattern = r'"id":\s*(\d+).*?"subnet":\s*"([^"]+)"'
                    matches = re.findall(subnet_pattern, config_content, re.DOTALL)
                    
                    for subnet_id, subnet_range in matches:
                        subnets[subnet_id] = subnet_range
    except Exception as e:
        print(f"Could not read Kea config: {e}")
    
    return subnets

def generate_reservation_config(ip, mac, hostname=""):
    """Generate Kea DHCP4 reservation configuration"""
    
    reservation = {
        "hw-address": mac.lower(),
        "ip-address": ip
    }
    
    if hostname:
        reservation["hostname"] = hostname
    
    # Generate the JSON config snippet
    config_snippet = {
        "reservations": [reservation]
    }
    
    # Pretty print the JSON
    json_config = json.dumps(config_snippet, indent=2)
    
    # Generate instructions
    instructions = f"""
To add this static reservation to your Kea DHCP4 configuration:

1. Edit your Kea configuration file:
   vi {KEA_CONFIG_FILE}

2. Find the subnet4 section for your network and add the reservation:

   "subnet4": [
     {{
       "subnet": "192.168.20.0/24",
       "pools": [
         {{ "pool": "192.168.20.100-192.168.20.200" }}
       ],
       "reservations": [
         {{
           "hw-address": "{mac.lower()}",
           "ip-address": "{ip}"{', "hostname": "' + hostname + '"' if hostname else ''}
         }}
       ]
     }}
   ]

3. Test the configuration:
   kea-dhcp4 -t {KEA_CONFIG_FILE}

4. Restart Kea DHCP4:
   /etc/init.d/kea-dhcp4 restart

5. Check the status:
   /etc/init.d/kea-dhcp4 status
"""
    
    return json_config, instructions

@app.route('/')
def index():
    """Main page showing lease table"""
    leases, error = read_lease_file()
    subnets = get_subnet_info()
    return render_template('lease_manager.html', leases=leases, error=error, subnets=subnets, now_timestamp=int(datetime.now().timestamp()))

@app.route('/api/leases')
def api_leases():
    """API endpoint to get lease data"""
    leases, error = read_lease_file()
    if error:
        return jsonify({"error": error}), 500
    return jsonify({"leases": leases})

@app.route('/api/lease-history/<ip>')
def api_lease_history(ip):
    """API endpoint to get lease history for specific IP"""
    history, error = get_lease_history(ip)
    if error:
        return jsonify({"error": error}), 500
    return jsonify({"history": history})

@app.route('/api/subnets')
def api_subnets():
    """API endpoint to get subnet information"""
    subnets = get_subnet_info()
    return jsonify({"subnets": subnets})

@app.route('/api/reservation', methods=['POST'])
def api_reservation():
    """Generate reservation configuration"""
    data = request.get_json()
    ip = data.get('ip', '')
    mac = data.get('mac', '')
    hostname = data.get('hostname', '')
    
    if not ip or not mac:
        return jsonify({"error": "IP and MAC address are required"}), 400
    
    json_config, instructions = generate_reservation_config(ip, mac, hostname)
    
    return jsonify({
        "json_config": json_config,
        "instructions": instructions
    })

@app.route('/refresh')
def refresh():
    """Refresh lease data"""
    return index()

# Enhanced HTML Template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kea DHCP Lease Manager</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1600px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            text-align: center;
            margin-bottom: 30px;
        }
        .header-info {
            background-color: #e8f4fd;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 10px;
        }
        .search-container {
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
            display: flex;
            gap: 15px;
            align-items: center;
            flex-wrap: wrap;
        }
        .search-input {
            padding: 8px 12px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 14px;
            min-width: 200px;
        }
        .clear-search {
            background-color: #6c757d;
            color: white;
            border: none;
            padding: 8px 12px;
            border-radius: 4px;
            cursor: pointer;
        }
        .refresh-btn {
            background-color: #28a745;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
        }
        .refresh-btn:hover {
            background-color: #218838;
        }
        .error {
            background-color: #f8d7da;
            color: #721c24;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
            border: 1px solid #f5c6cb;
        }
        .table-container {
            overflow-x: auto;
            margin-bottom: 20px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }
        th {
            background-color: #f8f9fa;
            font-weight: bold;
            position: sticky;
            top: 0;
        }
        tr:nth-child(even) {
            background-color: #f8f9fa;
        }
        tr:hover {
            background-color: #e8f4fd;
        }
        .ip-cell {
            font-family: monospace;
            font-weight: bold;
            color: #007bff;
        }
        .mac-cell {
            font-family: monospace;
            font-size: 0.9em;
        }
        .hostname-cell {
            font-weight: bold;
        }
        .action-btn {
            background-color: #007bff;
            color: white;
            border: none;
            padding: 5px 8px;
            border-radius: 3px;
            cursor: pointer;
            font-size: 0.8em;
            margin: 2px;
        }
        .action-btn:hover {
            background-color: #0056b3;
        }
        .history-btn {
            background-color: #6f42c1;
            color: white;
            border: none;
            padding: 5px 8px;
            border-radius: 3px;
            cursor: pointer;
            font-size: 0.8em;
            margin: 2px;
        }
        .history-btn:hover {
            background-color: #5a2d91;
        }
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.5);
        }
        .modal-content {
            background-color: white;
            margin: 5% auto;
            padding: 20px;
            border-radius: 8px;
            width: 90%;
            max-width: 900px;
            max-height: 80vh;
            overflow-y: auto;
        }
        .close {
            color: #aaa;
            float: right;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
        }
        .close:hover {
            color: black;
        }
        .config-box {
            background-color: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 4px;
            padding: 15px;
            margin: 10px 0;
            font-family: monospace;
            white-space: pre-wrap;
            font-size: 0.9em;
            overflow-x: auto;
        }
        .copy-btn {
            background-color: #6c757d;
            color: white;
            border: none;
            padding: 5px 10px;
            border-radius: 3px;
            cursor: pointer;
            margin-top: 10px;
        }
        .copy-btn:hover {
            background-color: #5a6268;
        }
        .stats {
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        .stat-box {
            background-color: #fff3cd;
            border: 1px solid #ffeaa7;
            border-radius: 5px;
            padding: 15px;
            text-align: center;
            flex: 1;
            min-width: 150px;
        }
        .stat-number {
            font-size: 2em;
            font-weight: bold;
            color: #856404;
        }
        .stat-label {
            color: #856404;
            font-size: 0.9em;
        }
        .no-data {
            text-align: center;
            padding: 40px;
            color: #666;
            font-style: italic;
        }
        .subnet-info {
            background-color: #d1ecf1;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .subnet-item {
            margin: 5px 0;
            font-family: monospace;
        }
        .hidden {
            display: none;
        }
        .history-table {
            width: 100%;
            margin-top: 15px;
        }
        .history-table th {
            background-color: #e9ecef;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🌐 Kea DHCP Lease Manager</h1>
        
        <div class="header-info">
            <div>
                <strong>Lease File:</strong> {{ LEASE_FILE or '/tmp/kea-leases4.csv' }}
            </div>
            <div>
                <strong>Last Updated:</strong> <span id="lastUpdate">{{ moment().format('YYYY-MM-DD HH:mm:ss') }}</span>
            </div>
            <a href="/refresh" class="refresh-btn">🔄 Refresh</a>
        </div>

        {% if subnets %}
        <div class="subnet-info">
            <strong>📊 Configured Subnets:</strong>
            {% for subnet_id, subnet_range in subnets.items() %}
            <div class="subnet-item">ID {{ subnet_id }}: {{ subnet_range }}</div>
            {% endfor %}
        </div>
        {% endif %}

        {% if error %}
        <div class="error">
            <strong>Error:</strong> {{ error }}
        </div>
        {% endif %}

        {% if leases %}
        <div class="search-container">
            <label for="searchInput"><strong>🔍 Quick Search:</strong></label>
            <input type="text" id="searchInput" class="search-input" placeholder="Search by IP, MAC, or hostname..." onkeyup="filterTable()">
            <button class="clear-search" onclick="clearSearch()">Clear</button>
            <span id="searchResults"></span>
        </div>

        <div class="stats">
            <div class="stat-box">
                <div class="stat-number" id="totalLeases">{{ leases|length }}</div>
                <div class="stat-label">Active Leases</div>
            </div>
            <div class="stat-box">
                <div class="stat-number">{{ leases|selectattr('hostname')|list|length }}</div>
                <div class="stat-label">With Hostnames</div>
            </div>
            <div class="stat-box">
                <div class="stat-number">{{ (leases|selectattr('expire_timestamp')|map(attribute='expire_timestamp')|select('>', now_timestamp)|list|length) if now_timestamp else 'N/A' }}</div>
                <div class="stat-label">Not Expired</div>
            </div>
            <div class="stat-box">
                <div class="stat-number" id="visibleLeases">{{ leases|length }}</div>
                <div class="stat-label">Visible</div>
            </div>
        </div>

        <div class="table-container">
            <table id="leasesTable">
                <thead>
                    <tr>
                        <th>IP Address</th>
                        <th>MAC Address</th>
                        <th>Hostname</th>
                        <th>Expires</th>
                        <th>Subnet ID</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {% for lease in leases %}
                    <tr class="lease-row">
                        <td class="ip-cell">{{ lease.ip }}</td>
                        <td class="mac-cell">{{ lease.mac }}</td>
                        <td class="hostname-cell">{{ lease.hostname or '-' }}</td>
                        <td>{{ lease.expire }}</td>
                        <td>{{ lease.subnet_id }}</td>
                        <td>
                            <button class="action-btn" onclick="showReservation('{{ lease.ip }}', '{{ lease.mac }}', '{{ lease.hostname }}')">
                                Make Static
                            </button>
                            <button class="history-btn" onclick="showHistory('{{ lease.ip }}')">
                                History
                            </button>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% else %}
        <div class="no-data">
            No active leases found.
        </div>
        {% endif %}
    </div>

    <!-- Modal for reservation config -->
    <div id="reservationModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeModal('reservationModal')">&times;</span>
            <h2>Static DHCP Reservation Configuration</h2>
            <div id="reservationContent"></div>
        </div>
    </div>

    <!-- Modal for lease history -->
    <div id="historyModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeModal('historyModal')">&times;</span>
            <h2 id="historyTitle">Lease History</h2>
            <div id="historyContent"></div>
        </div>
    </div>

    <script>
        function filterTable() {
            const input = document.getElementById('searchInput');
            const filter = input.value.toLowerCase();
            const table = document.getElementById('leasesTable');
            const rows = table.getElementsByClassName('lease-row');
            let visibleCount = 0;

            for (let i = 0; i < rows.length; i++) {
                const row = rows[i];
                const cells = row.getElementsByTagName('td');
                let showRow = false;

                // Search in IP, MAC, and hostname columns
                for (let j = 0; j < 3; j++) {
                    if (cells[j] && cells[j].textContent.toLowerCase().indexOf(filter) > -1) {
                        showRow = true;
                        break;
                    }
                }

                if (showRow) {
                    row.style.display = '';
                    visibleCount++;
                } else {
                    row.style.display = 'none';
                }
            }

            // Update visible count
            document.getElementById('visibleLeases').textContent = visibleCount;
            
            // Update search results
            const searchResults = document.getElementById('searchResults');
            if (filter) {
                searchResults.textContent = `Showing ${visibleCount} of ${rows.length} leases`;
            } else {
                searchResults.textContent = '';
            }
        }

        function clearSearch() {
            document.getElementById('searchInput').value = '';
            filterTable();
        }

        function showReservation(ip, mac, hostname) {
            fetch('/api/reservation', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    ip: ip,
                    mac: mac,
                    hostname: hostname
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    alert('Error: ' + data.error);
                    return;
                }
                
                const content = `
                    <h3>JSON Configuration Snippet:</h3>
                    <div class="config-box" id="jsonConfig">${data.json_config}</div>
                    <button class="copy-btn" onclick="copyToClipboard('jsonConfig')">Copy JSON</button>
                    
                    <h3>Complete Instructions:</h3>
                    <div class="config-box" id="instructions">${data.instructions}</div>
                    <button class="copy-btn" onclick="copyToClipboard('instructions')">Copy Instructions</button>
                `;
                
                document.getElementById('reservationContent').innerHTML = content;
                document.getElementById('reservationModal').style.display = 'block';
            })
            .catch(error => {
                alert('Error: ' + error.message);
            });
        }

        function showHistory(ip) {
            fetch('/api/lease-history/' + encodeURIComponent(ip))
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    alert('Error: ' + data.error);
                    return;
                }

                document.getElementById('historyTitle').textContent = `Lease History for ${ip}`;
                
                let content = `<p><strong>Total entries found:</strong> ${data.history.length}</p>`;
                
                if (data.history.length > 0) {
                    content += `
                        <table class="history-table">
                            <thead>
                                <tr>
                                    <th>MAC Address</th>
                                    <th>Hostname</th>
                                    <th>Expires</th>
                                    <th>State</th>
                                    <th>Subnet ID</th>
                                    <th>Valid Lifetime</th>
                                </tr>
                            </thead>
                            <tbody>
                    `;
                    
                    data.history.forEach(entry => {
                        content += `
                            <tr>
                                <td class="mac-cell">${entry.mac}</td>
                                <td>${entry.hostname || '-'}</td>
                                <td>${entry.expire}</td>
                                <td>${entry.state}</td>
                                <td>${entry.subnet_id}</td>
                                <td>${entry.valid_lifetime}</td>
                            </tr>
                        `;
                    });
                    
                    content += '</tbody></table>';
                } else {
                    content += '<p><em>No lease history found for this IP address.</em></p>';
                }
                
                document.getElementById('historyContent').innerHTML = content;
                document.getElementById('historyModal').style.display = 'block';
            })
            .catch(error => {
                alert('Error: ' + error.message);
            });
        }

        function closeModal(modalId) {
            document.getElementById(modalId).style.display = 'none';
        }

        function copyToClipboard(elementId) {
            const element = document.getElementById(elementId);
            const text = element.textContent;
            
            navigator.clipboard.writeText(text).then(function() {
                alert('Copied to clipboard!');
            }).catch(function(err) {
                // Fallback for older browsers
                const textArea = document.createElement('textarea');
                textArea.value = text;
                document.body.appendChild(textArea);
                textArea.select();
                document.execCommand('copy');
                document.body.removeChild(textArea);
                alert('Copied to clipboard!');
            });
        }

        // Close modal when clicking outside
        window.onclick = function(event) {
            const reservationModal = document.getElementById('reservationModal');
            const historyModal = document.getElementById('historyModal');
            
            if (event.target == reservationModal) {
                closeModal('reservationModal');
            }
            if (event.target == historyModal) {
                closeModal('historyModal');
            }
        }

        // Auto-refresh every 30 seconds (only if no modals are open)
        setInterval(function() {
            const reservationModal = document.getElementById('reservationModal');
            const historyModal = document.getElementById('historyModal');
            
            if ((!reservationModal.style.display || reservationModal.style.display === 'none') &&
                (!historyModal.style.display || historyModal.style.display === 'none')) {
                location.reload();
            }
        }, 30000);

        // Update last updated time
        document.getElementById('lastUpdate').textContent = new Date().toLocaleString();
    </script>
</body>
</html>
'''

# Create the template
import os
if not os.path.exists('templates'):
    os.makedirs('templates')

with open('templates/lease_manager.html', 'w') as f:
    f.write(HTML_TEMPLATE)

if __name__ == '__main__':
    print("Starting Enhanced Kea DHCP Lease Manager...")
    print(f"Reading lease file: {LEASE_FILE}")
    print("Web interface will be available at http://0.0.0.0:5001")
    print("\nNew Features:")
    print("- 🔍 Real-time search/filter functionality")
    print("- 📊 Subnet information display")
    print("- 📜 Lease history for each IP")
    print("- 🚫 Duplicate lease elimination")
    print("- 📈 Enhanced statistics")
    print("- 🎨 Improved responsive design")
    
    app.run(debug=False, host='0.0.0.0', port=5001)