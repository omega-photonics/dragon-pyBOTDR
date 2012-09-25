from collections import namedtuple
from ctypes import *

fs = "ch1amp ch1shift ch1count ch2amp ch2shift ch2count framelength framecount"
class PCIESettings(object):
    
    MaxFrameLenght = 65520 * sizeof(c_uint32)
    def __init__(self,
                 ch1amp, ch1shift, ch1count,
                 ch2amp, ch2shift, ch2count, 
                 framelength, framecount):
        self.ch1amp = ch1amp
        self.ch1shift = ch1shift
        self.ch1count = ch1count
        self.ch2amp = ch2amp
        self.ch2shift = ch2shift
        self.ch2count = ch2count        
        self.framecount = framecount
        self.framelength = framelength
    
    @property
    def dacdata(self):
        val = self.ch1amp << 24 | self.ch1shift << 16 | self.ch2amp << 8 | self.ch2shift
        return val
    
    @property
    def counts(self):
        return self.ch2count << 16 | self.ch1count
        
        
class PCIEResponse(object):
    pass
