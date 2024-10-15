import sys
import json
import socket
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import QThread, Signal, Slot, QTimer
import logging
import subprocess
import tempfile
import os
import shutil

class GPSThread(QThread):
    gps_update = Signal(dict)

    def __init__(self):
        super().__init__()
        self.socket_connection = None
        self.is_running = True

    def run(self):
        while self.is_running:
            try:
                if not self.socket_connection:
                    self.socket_connection = socket.create_connection(("localhost", 2947), timeout=5)
                    self.socket_connection.sendall(b'?WATCH={"enable":true,"json":true}\n')
                
                data = self.socket_connection.recv(4096).decode('utf-8')
                for line in data.splitlines():
                    report = json.loads(line)
                    self.gps_update.emit(report)
            except Exception as e:
                logging.error(f"GPS Error: {e}")
                self.is_running = False
                if self.socket_connection:
                    self.socket_connection.close()
                    self.socket_connection = None

    def stop(self):
        self.is_running = False
        if self.socket_connection:
            self.socket_connection.close()

class GPSWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.initLogging()
        self.gps_thread = GPSThread()
        self.gps_thread.gps_update.connect(self.updateUI)
        self.gps_thread.start()

    def initLogging(self):
        logging.basicConfig(filename='gpsd_timesync.log', level=logging.DEBUG,
                            format='%(asctime)s - %(levelname)s - %(message)s')

    def initUI(self):
        self.setWindowTitle("GPSD Timesync")
        
        self.statsLabel = QLabel("GPS Stats: Not Available", self)
        self.signalLabel = QLabel("Signal Strength: Unknown", self)
        self.satellitesLabel = QLabel("Satellites: None", self)
        self.ntpLabel = QLabel("NTP Servers: Not Configured", self)
        self.deviceLabel = QLabel("GPS Device: Not Detected", self)

        self.ntpButton = QPushButton("Configure NTP Servers", self)
        self.refreshButton = QPushButton("Refresh GPS Connection", self)

        layout = QVBoxLayout(self)
        layout.addWidget(self.statsLabel)
        layout.addWidget(self.signalLabel)
        layout.addWidget(self.satellitesLabel)
        layout.addWidget(self.ntpLabel)
        layout.addWidget(self.deviceLabel)
        layout.addWidget(self.ntpButton)
        layout.addWidget(self.refreshButton)

        self.ntpButton.clicked.connect(self.configureNTP)
        self.refreshButton.clicked.connect(self.refreshGPS)

    @Slot(dict)
    def updateUI(self, report):
        if report['class'] == 'TPV':
            latitude = report.get('lat', "Unknown")
            longitude = report.get('lon', "Unknown")
            time = report.get('time', "Unknown")
            self.statsLabel.setText(f"GPS Stats - Latitude: {latitude}, Longitude: {longitude}\nTime: {time}")
        elif report['class'] == 'SKY':
            self.updateSKY(report)
        elif report['class'] == 'DEVICES':
            self.updateDevices(report)

    def updateSKY(self, report):
        satellites = report.get('satellites', [])
        strengths = [sat['ss'] for sat in satellites if 'ss' in sat]
        if strengths:
            avg_strength = sum(strengths) / len(strengths)
            self.signalLabel.setText(f"Signal Strength: {avg_strength:.2f}")
        
        sat_info = [f"PRN: {sat.get('PRN', 'N/A')}, SNR: {sat.get('ss', 'N/A')}" for sat in satellites]
        self.satellitesLabel.setText(f"Satellites: {len(satellites)}\n" + "\n".join(sat_info))

    def updateDevices(self, report):
        devices = report.get('devices', [])
        if devices:
            device = devices[0]  # Assume the first device
            self.deviceLabel.setText(f"GPS Device: {device.get('path', 'Unknown')}")

    def configureNTP(self):
        try:
            script_content = '''#!/bin/bash
set -e

NTPCONF="/etc/ntp.conf"
GPSDDEFAULT="/etc/default/gpsd"

# Backup original files
cp "$NTPCONF" "${NTPCONF}.bak"
cp "$GPSDDEFAULT" "${GPSDDEFAULT}.bak"

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
    systemctl restart ntpd gpsd
elif command -v sv >/dev/null 2>&1; then
    echo "Detected runit"
    sv restart ntpd gpsd
elif command -v service >/dev/null 2>&1; then
    echo "Detected sysvinit"
    service ntpd restart
    service gpsd restart
else
    echo "Unsupported init system"
    exit 1
fi

echo "Configuration completed successfully."
exit 0
'''
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
                temp_file.write(script_content)
                temp_file_path = temp_file.name

            os.chmod(temp_file_path, 0o755)

            if shutil.which("pkexec"):
                result = subprocess.run(['pkexec', temp_file_path], capture_output=True, text=True, check=True)
                logging.info(f"NTP Configuration output: {result.stdout}")
                if result.stderr:
                    logging.warning(f"NTP Configuration warnings: {result.stderr}")
            else:
                raise Exception("pkexec is required for configuration.")
            
            os.unlink(temp_file_path)
            self.ntpLabel.setText("NTP and GPSD configured.")
            logging.info("NTP and GPSD configured successfully.")
        except subprocess.CalledProcessError as e:
            error_msg = f"Configuration Error: {e}\nOutput: {e.output}\nError: {e.stderr}"
            logging.error(error_msg)
            self.showErrorDialog("Configuration Error", error_msg)
        except Exception as e:
            error_msg = f"Unexpected error during configuration: {e}"
            logging.error(error_msg)
            self.showErrorDialog("Configuration Error", error_msg)

    def showErrorDialog(self, title, message):
        errorDialog = QtWidgets.QMessageBox(self)
        errorDialog.setWindowTitle(title)
        errorDialog.setText(message)
        errorDialog.setIcon(QtWidgets.QMessageBox.Critical)
        errorDialog.exec()

    def closeEvent(self, event):
        self.gps_thread.stop()
        self.gps_thread.wait()
        event.accept()

    def refreshGPS(self):
        self.gps_thread.stop()
        self.gps_thread.wait()
        self.gps_thread.start()

if __name__ == "__main__":
    app = QApplication([])
    widget = GPSWidget()
    widget.resize(450, 300)
    widget.show()
    sys.exit(app.exec())
