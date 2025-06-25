
import socket
from qgis.core import QgsMessageLog, Qgis

HOST = '0.0.0.0'
PORT = 2001

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((HOST, PORT))

QgsMessageLog.logMessage(f"Listening for UDP data on {HOST}:{PORT}", "AIS", Qgis.Info)

def listen():
    while True:
        data, addr = sock.recvfrom(1024)
        message = data.decode('utf-8')
        QgsMessageLog.logMessage(f"Received from {addr}: {message}", "AIS", Qgis.Info)

import threading
threading.Thread(target=listen, daemon=True).start()
