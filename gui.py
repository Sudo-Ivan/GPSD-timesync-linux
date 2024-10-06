import sys
import json
import socket
import subprocess
from PySide6 import QtCore, QtWidgets
from threading import Thread
import shutil
import time

class GPSWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.socket_connection = None
        self.gps_thread = Thread(target=self.updateGPSStats)
        self.is_running = True
        self.initUI()
        self.attemptConnectGPS()

    def initUI(self):
        self.setWindowTitle("GPSD Timesync")
        
        self.statsLabel = QtWidgets.QLabel("GPS Stats: Not Available", self)
        self.statsLabel.setAlignment(QtCore.Qt.AlignLeft)

        self.signalLabel = QtWidgets.QLabel("Signal Strength: Unknown", self)
        self.ntpLabel = QtWidgets.QLabel("NTP Servers: Not Configured", self)

        self.ntpButton = QtWidgets.QPushButton("Configure NTP Servers", self)

        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)
        self.layout.addWidget(self.statsLabel)
        self.layout.addWidget(self.signalLabel)
        self.layout.addWidget(self.ntpLabel)
        self.layout.addWidget(self.ntpButton)

        self.ntpButton.clicked.connect(self.configureNTP)

        self.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 8px;
            }
            QLabel {
                font-size: 12px;
            }
        """)

    def attemptConnectGPS(self):
        while not self.connectGPS():
            time.sleep(6)

    def connectGPS(self):
        try:
            self.socket_connection = socket.create_connection(("localhost", 2947))
            self.socket_connection.sendall(b'?WATCH={"enable":true,"json":true}\n')
            self.statsLabel.setText("Connected to GPSD.")
            if not self.gps_thread.is_alive():
                self.is_running = True
                self.gps_thread = Thread(target=self.updateGPSStats)
                self.gps_thread.start()
            return True
        except Exception as e:
            print(f"GPS Connection Error: {e}", file=sys.stderr)
            return False

    def updateGPSStats(self):
        while self.is_running:
            try:
                data = self.socket_connection.recv(4096).decode('utf-8')
                for line in data.splitlines():
                    report = json.loads(line)
                    if report['class'] == 'TPV':
                        latitude = report.get('lat', "Unknown")
                        longitude = report.get('lon', "Unknown")
                        self.statsLabel.setText(f"GPS Stats - Latitude: {latitude}, Longitude: {longitude}")
                    if report['class'] == 'SKY':
                        self.updateSignalStrength(report)
            except Exception as e:
                print(f"GPS Data Error: {e}", file=sys.stderr)
                self.is_running = False

    def updateSignalStrength(self, report):
        satellites = report.get('satellites', [])
        strengths = [sat['ss'] for sat in satellites if 'ss' in sat]
        if strengths:
            avg_strength = sum(strengths) / len(strengths)
            self.signalLabel.setText(f"Signal Strength: {avg_strength:.2f}")

    def configureNTP(self):
        try:
            if shutil.which("pkexec"):
                subprocess.run(['pkexec', './configure_gps.sh'], check=True)
            else:
                self.showErrorDialog("Configuration Error", "pkexec is required.")
            self.ntpLabel.setText(f"NTP and GPSD configured.")
        except subprocess.CalledProcessError as e:
            self.showErrorDialog("Configuration Error", f"An error occurred during configuration: {e}")

    def showErrorDialog(self, title, message):
        errorDialog = QtWidgets.QMessageBox(self)
        errorDialog.setWindowTitle(title)
        errorDialog.setText(message)
        errorDialog.setIcon(QtWidgets.QMessageBox.Critical)
        errorDialog.exec()

    def closeEvent(self, event):
        self.is_running = False
        if self.socket_connection:
            self.socket_connection.close()
        if self.gps_thread.is_alive():
            self.gps_thread.join()
        event.accept()

if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    widget = GPSWidget()
    widget.resize(450, 300)
    widget.show()
    sys.exit(app.exec())