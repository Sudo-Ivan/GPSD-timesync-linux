import sys
import json
import socket
import time
import argparse
import logging
import subprocess
import tempfile
import os

class GPSCLITool:
    def __init__(self, debug=False, debug_output=None):
        self.socket_connection = None
        self.is_running = True
        self.debug = debug
        if debug:
            logging.basicConfig(filename=debug_output, level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
            logging.debug("Debugging mode enabled.")

    def attempt_connect_gps(self):
        while not self.connect_gps():
            time.sleep(6)

    def connect_gps(self):
        try:
            self.socket_connection = socket.create_connection(("localhost", 2947))
            self.socket_connection.sendall(b'?WATCH={"enable":true,"json":true}\n')
            print("Connected to GPSD.")
            if self.debug:
                logging.debug("Connected to GPSD successfully.")
            return True
        except Exception as e:
            error_message = f"GPS Connection Error: {e}"
            print(error_message, file=sys.stderr)
            if self.debug:
                logging.error(error_message)
            return False

    def display_gps_stats(self):
        try:
            while self.is_running:
                data = self.socket_connection.recv(4096).decode('utf-8')
                for line in data.splitlines():
                    report = json.loads(line)
                    if report['class'] == 'TPV':
                        latitude = report.get('lat', "Unknown")
                        longitude = report.get('lon', "Unknown")
                        print(f"GPS Stats - Latitude: {latitude}, Longitude: {longitude}")
                        if self.debug:
                            logging.debug(f"Latitude: {latitude}, Longitude: {longitude}")
                    if report['class'] == 'SKY':
                        self.display_signal_strength(report)
                        self.display_satellites(report)
                time.sleep(1)
        except Exception as e:
            error_message = f"GPS Data Error: {e}"
            print(error_message, file=sys.stderr)
            if self.debug:
                logging.error(error_message)
            self.is_running = False

    def display_signal_strength(self, report):
        satellites = report.get('satellites', [])
        strengths = [sat['ss'] for sat in satellites if 'ss' in sat]
        if strengths:
            avg_strength = sum(strengths) / len(strengths)
            print(f"Signal Strength: {avg_strength:.2f}")
            if self.debug:
                logging.debug(f"Signal Strength: {avg_strength:.2f}")

    def display_satellites(self, report):
        satellites = report.get('satellites', [])
        print(f"Satellites: {len(satellites)}")
        for sat in satellites:
            print(f"PRN: {sat.get('PRN', 'N/A')}, SNR: {sat.get('ss', 'N/A')}")
        if self.debug:
            logging.debug(f"Satellites: {len(satellites)}")

    def configure_ntp(self):
        try:
            print("Configuring NTP servers...")
            script_content = '''#!/bin/bash

NTPCONF="/etc/ntp.conf"
GPSDDEFAULT="/etc/default/gpsd"

if ! grep -q "127.127.28.0" "$NTPCONF"; then
    echo '
# GPS Serial data reference
server 127.127.28.0 minpoll 4 maxpoll 4
fudge 127.127.28.0 time1 0.0 refid GPS

# GPS PPS reference
server 127.127.28.1 minpoll 4 maxpoll 4 prefer
fudge 127.127.28.1 refid PPS

' >> "$NTPCONF"
fi

if grep -q '^GPSD_OPTIONS=' "$GPSDDEFAULT"; then
    sed -i 's/^GPSD_OPTIONS=".*"$/GPSD_OPTIONS="-n"/' "$GPSDDEFAULT"
else
    echo 'GPSD_OPTIONS="-n"' >> "$GPSDDEFAULT"
fi

if command -v systemctl >/dev/null 2>&1; then
    echo "Detected systemd"
    systemctl restart ntpd
elif command -v sv >/dev/null 2>&1; then
    echo "Detected runit"
    sv restart ntpd
elif command -v service >/dev/null 2>&1; then
    echo "Detected sysvinit"
    service ntpd restart
else
    echo "Unsupported init system"
    exit 1
fi

exit 0
'''
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
                temp_file.write(script_content)
                temp_file_path = temp_file.name

            os.chmod(temp_file_path, 0o755)
            subprocess.run(['sudo', temp_file_path], check=True)
            os.unlink(temp_file_path)
            print("NTP servers configured successfully.")
            if self.debug:
                logging.debug("NTP servers configured successfully.")
        except subprocess.CalledProcessError as e:
            error_message = f"Configuration Error: {e}"
            print(error_message, file=sys.stderr)
            if self.debug:
                logging.error(error_message)

    def stop(self):
        self.is_running = False
        if self.socket_connection:
            self.socket_connection.close()
        print("Stopped GPS monitoring.")

def main():
    parser = argparse.ArgumentParser(description="GPSD Command Line Tool")
    parser.add_argument('--start', action='store_true', help="Start GPS monitoring")
    parser.add_argument('--configure', action='store_true', help="Configure NTP servers using GPS")
    parser.add_argument('--debug', action='store_true', help="Enable debug mode")
    parser.add_argument('--debug-output', type=str, default='debug.log', help="Specify debug output file")

    args = parser.parse_args()

    gps_tool = GPSCLITool(debug=args.debug, debug_output=args.debug_output)

    if args.configure:
        gps_tool.configure_ntp()
    elif args.start:
        print("Starting GPS monitoring...")
        gps_tool.attempt_connect_gps()
        gps_tool.display_gps_stats()
    else:
        parser.print_help()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nUser interruption detected. Exiting...")
