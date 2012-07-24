import usb 
import sys 
import os 
import time 
from array import array 

class DeviceDescriptor: 
    def __init__(self, vendor_id, product_id, interface_id) : 
        self.vendor_id = vendor_id 
        self.product_id = product_id 
        self.interface_id = interface_id 

    def get_device(self) : 
        buses = usb.busses() 
        for bus in buses : 
            for device in bus.devices : 
                if device.idVendor == self.vendor_id : 
                    if device.idProduct == self.product_id : 
                        return device 
        return None 

class MyDevice(object):
    def __init__(self, vid, pid, interface_id=0, in_ep=0x81, out_ep=0x01): 
        # The actual device (PyUSB object) 
        self.device_descriptor = DeviceDescriptor(vid, pid, interface_id)
        self.device = self.device_descriptor.get_device() 
        # Handle that is used to communicate with device. Setup in L{open} 
        self.handle = None 
        self.in_ep = in_ep
        self.out_ep = out_ep
    
    def open(self): 
        self.device = self.device_descriptor.get_device() 
        if not self.device: 
            print "Cable isn't plugged in" 
        try: 
            self.handle = self.device.open() 
            self.handle.claimInterface(self.device_descriptor.interface_id) 
        except usb.USBError, err: 
            print >> sys.stderr, err 


    def close(self):   
        """ Release device interface """ 
        try: 
            self.handle.releaseInterface() 
            self.handle.reset() 
        except Exception, err: 
            print >> sys.stderr, err 
        self.handle, self.device = None, None 
        
    def write(self, buf, timeout=1000): 
        return self.handle.bulkWrite(self.out_ep,buf,timeout) 
        
    def read(self, n, timeout=1000):
        new = time.time()
        ret = array("B")
        tup = self.handle.bulkRead(self.in_ep, n, timeout)
        #print "read in", time.time() - new
        ret.fromlist(list(tup)); 
        return ret
    
    def wait(self, period=0.3):
        self.open()
        while self.device is None or self.handle is None:
            time.sleep(period)
            self.open()
            
    def waitwrite(self, buf):
        while True:
            try:
                return self.write(buf)
            except usb.USBError:
                print "Usb disconnected on write"

                self.close()
                self.wait()
                
    def waitread(self, nbytes):
        while True:
            try:
                return self.read(nbytes)
            except usb.USBError:
                print "Usb disconnected on read"
                self.close()
                self.wait()
        
    
if __name__ == '__main__':
    xfps = MyDevice()
    if xfps:
        print "Device found"

    xfps.open() 
    #xfps.my_bulk_write() 
 
