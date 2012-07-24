from PyQt4 import QtCore

import socket
import mysocket
import  pciedevsettings
import struct
import array
import numpy as np

HOST = "localhost"
#HOST = '192.168.1.223'    # The remote host
PCIEPORT = 32120


class PCIENetWorker(QtCore.QThread):
    measured = QtCore.pyqtSignal(pciedevsettings.PCIEResponse)

    def __init__(self, parent=None):
        QtCore.QThread.__init__(self, parent)
        self.socket = mysocket.MySocket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.socket.connect((HOST, PCIEPORT))
        self.lock = QtCore.QMutex()
        self.exiting = False
        
    def setPCIESettings(self, settings):
        self.lock.lock()
        self.settings = settings
        self.lock.unlock()
        
    def run(self):
        response = pciedevsettings.PCIEResponse()
        while not self.exiting:
            response.framelength = struct.unpack("H", self.socket.recvall(2))[0]
            response.framecount = struct.unpack("I", self.socket.recvall(4))[0]
            response.dacdata = struct.unpack("I", self.socket.recvall(4))[0]
            datasize = pciedevsettings.PCIESettings.MaxFrameLenght
            rawdata = self.socket.recvall(datasize, timeout=5)
            
            self.lock.lock()
            self.socket.sendall(struct.pack("H", int(self.settings.framelength)))
            self.socket.sendall(struct.pack("I", self.settings.framecount))
            self.socket.sendall(struct.pack("I", self.settings.dacdata))
            self.lock.unlock()
            
            data = array.array("I")
            data.fromstring(rawdata)
            data = np.array(data).astype(float) / response.framecount
            response.data = data
            self.measured.emit(response)        
    
    def stop(self):
        self.exiting = True
        self.wait()
        self.socket.close()
