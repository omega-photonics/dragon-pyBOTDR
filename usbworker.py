from test04 import MyDevice as USBDevice
import usbdev
from PyQt4 import QtCore
import time
PID = 0x5797
VID = 0x0483
INTERFACE = 1

class USBWorker(QtCore.QThread):
    measured = QtCore.pyqtSignal(usbdev.USBResponse)
    statusChanged = QtCore.pyqtSignal(str)
    def __init__(self, parent=None):
        QtCore.QThread.__init__(self, parent)
        self.usbDevice = USBDevice(pid=PID, vid=VID, interface_id=INTERFACE)

        self.usbSettings = usbdev.USBSettings()
        self._stackedsettings = None
        self.lock = QtCore.QMutex()
        self.exiting = False
        self.stackcounter = 0
        self.running = False
        self.debugprintcounter = 0
    
    def __getattr__(self, name):
        print "called {}".format(name)
        def func(*args):
            
            ret = getattr(self.usbSettings, name)(*args)
            self.measure()
            return ret
        return func 
    
    def setPFGI_TscanAmp(self, val):
        self.usbSettings.setPFGI_TscanAmp(val)
        self.measure()
    
    def setDIL_T(self, val):
        self.usbSettings.setDIL_T_scan_state(0xFF)
        self.usbSettings.setDIL_T(val)
        self.measure() 
        
    def setFlashFlag(self, val):
        if type(val) == bool:
            if val:
                self.usbSettings.buffer[62] = 0xAA
            else:
                self.usbSettings.buffer[62] = 0x00
        else:
            self.usbSettings.buffer[62] = val
    
    def flash(self):
        self.setFlashFlag(True)
        self.measure()
        self.setFlashFlag(False)

    def start_up_scan(self):
        print "USB: Scanning UP"
        self.usbSettings.setDIL_T_scan_state(1)
        self.measure(0)
        self.usbSettings.setDIL_T_scan_state(0)

    def start_down_scan(self):
        print "USB: Scanning DOWN"
        self.usbSettings.setDIL_T_scan_state(2)
        self.measure(0)
        self.usbSettings.setDIL_T_scan_state(0)

    def break_scan(self):
        self.usbSettings.setDIL_T(self.lastDIL_t)
        self.usbSettings.setDIL_T_scan_state(0xFF)
        self.measure()
    
    def setDIL_T_scan_time(self, val):
        self.usbSettings.setDIL_T_scan_time(val)
        self.measure()
    
    def setDIL_T_scan_top(self, val):
        self.usbSettings.setDIL_T_scan_top(val)
        self.measure()

    def setDIL_T_scan_bottom(self, val):
        self.usbSettings.setDIL_T_scan_bottom(val)
        self.measure()

#    def measure(self):
#        print "Start measuring USB"
#        if self.isRunning():
#            return
#        self.start()

    
    def measure(self, debugprint=0):
        self.debugprintcounter += debugprint
        enter = time.time()
        if self.usbDevice.handle != None:
            buf = self.usbDevice.read(64)
        if self.usbDevice.handle == None or len(buf) != 64:
            try:
                self.usbDevice.close()
            except Exception, err: 
                print "Can not close device"
                print err 
            try: 
                self.usbDevice.open()
            except Exception, err: 
                print "Can not open device"
                print  err 
                
            if self.usbDevice.handle == None:
               self.statusChanged.emit("Connecting")
               return
            else:
               self.statusChanged.emit("Working")
               buf = self.usbDevice.read(64)
         
                
        response = usbdev.USBResponse()
        response.frombuffer(buf)
        if self.debugprintcounter:
#            print "read from usb: \n", buf
            self.debugprintcounter -= 1
        self.measured.emit(response)
        self.lastDIL_t = response.DIL_T_scan_pos
        self.usbSettings.setPFGI_TscanPeriod(0) # some hack
        if self.debugprintcounter:
            print "send to usb: \n", self.usbSettings.buffer
        self.usbSettings.buffer[63] = 44 # marker
        ret = self.usbDevice.write(self.usbSettings.buffer)
        self.setFlashFlag(0)
        if ret != 64:
            try:
                self.usbDevice.close()
            except Exception, err: 
                print "Can not close device"
                print err 
            try: 
                self.usbDevice.open()
            except Exception, err: 
                print "Can not open device"
                print  err 
                
            if self.usbDevice.handle == None:
                self.statusChanged.emit("Connecting")
                return
            else:
                self.statusChanged.emit("Working")
#        print "DIL_T read from USB:", response.DIL_T_scan_pos
#        print "Read/write usb cycle completed in {}".format(time.time()- enter)
        #return response
