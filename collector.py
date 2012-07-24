from PyQt4 import QtCore

from collections import namedtuple
import multiprocessing as mp
from multiprocessing.sharedctypes import SynchronizedArray
import ctypes
import time
import numpy as np
from dump import mydump
from pciedevsettings import PCIEResponse

Curve = namedtuple("Curve", "x y")

class Precollector(QtCore.QObject):
    measured = QtCore.pyqtSignal(PCIEResponse)
    averaged = QtCore.pyqtSignal(PCIEResponse)
    reflectogrammChanged = QtCore.pyqtSignal(np.ndarray)
    def __init__(self, parent=None):
        QtCore.QObject.__init__(self,parent)
        self.state = 0
        self.response = PCIEResponse()
    
    def check_response(self, response):
        return True
        if response.activechannel != 0:
            return False
         
        dat = response.data[:response.framelength]
        dif = np.diff(dat[4:])
        minimum, maximum = dat[:2]
        here_min = min(dat[4:])
        here_max = max(dat[4:])
        average = dat[3]
        
        
        K = np.max(np.abs(dif)) / np.median(np.abs(dif))
        if K > 1000:
            print "Step detected", K
            return False
        if minimum != here_min or maximum != here_max or abs(dat[2] - 527) > 1e-5 or abs(average - np.average(dat[4:])) / average > 1e-5:
            print "Send fail detected"
            print minimum - here_min, maximum - here_max, dat[2] - 527, abs(average - np.average(dat[4:])) / average
            return False
        
        #response.data[:response.framelength] -= np.average(response.data[response.framelength-1000:response.framelength])
        response.data[:4] = 0
        return True
        
    def appendDragonResponse(self, response):
        self.reflectogrammChanged.emit(response.data[:response.framelength])
        
        

class Collector(QtCore.QObject):
    reflectogrammChanged = QtCore.pyqtSignal(np.ndarray)
    temperatureCurveChanged = QtCore.pyqtSignal(Curve)
    temperatureCurve2Changed = QtCore.pyqtSignal(Curve)
    spectraChanged = QtCore.pyqtSignal(Curve)
    spectraOnChipChanged = QtCore.pyqtSignal(tuple)
    sharedArrayChanged = QtCore.pyqtSignal(tuple)
    def __init__(self, reflen, speclen, parent=None):
        QtCore.QObject.__init__(self, parent)
        # always waits for reflectogramm, appending temp. measurements
        # only if needed
        self.waitingForTemperature = False
        self.firstScan = True
        self.temperatureIndex = 0           # for outer stabilization 
        self.reflectogrammLength = reflen
        self.spectraLength = speclen
        self.recreatecontainer()
        self.starttime = time.time()
        self.time = np.zeros(30000)
        self.temperature = np.zeros(30000)
        self.temperature2 = np.zeros(30000)
        self.nextIndex = (0, 0, 0, 0)
        self.collected = set([])
        
    def appendDragonResponse(self, response):
        response.data[:response.framelength] -= np.average(response.data[response.framelength-1000:response.framelength])
        #response.data[:4] = 0
        direction, scanNumber, polarisation, freqindex = self.nextIndex
        self.scanMatrix[direction, scanNumber, polarisation, :, freqindex] = \
            response.data[:response.framelength]
        self.reflectogrammChanged.emit(response.data[:response.framelength]) #?
        self.collected.add(scanNumber)
        #self.waitingForTemperature = True
    
    def appendUSBResponse(self, response):
        #if self.waitingForTemperature:
        
        self.time[self.temperatureIndex] = time.time() - self.starttime
        self.temperature[self.temperatureIndex] = response.T1
        self.temperature2[self.temperatureIndex] = response.T2
        self.temperatureIndex += 1

        self.temperatureCurveChanged.emit(
            Curve(self.time[:self.temperatureIndex],
                  self.temperature[:self.temperatureIndex]))
        self.temperatureCurve2Changed.emit(
            Curve(self.time[:self.temperatureIndex],
                  self.temperature2[:self.temperatureIndex]))
        
        if self.temperatureIndex == 30000:
            for ar in self.time, self.temperature, self.temperature2:
                ar[:30000//2] = ar[30000//2:]
            
            self.temperatureIndex = 30000 // 2

        
    def appendOnChipTemperature(self, temp):
        self.onChipTemp[self.nextIndex] = temp
        upcurves = []
        downcurves = []
        for j in range(2):
            for i in range(3):
                upcurves.append(
                Curve(x=self.upOnChipTemp[i, j],
                    y=self.upScanMatrix[i, j])
                )

            for i in range(3):
                downcurves.append(
                Curve(x=self.downOnChipTemp[i, j],
                    y=self.downScanMatrix[i, j])
                )
        self.spectraOnChipChanged.emit((upcurves, downcurves))
    
    def savelastscan(self):
        direction, scanNumber, polarisation, freqindex = self.nextIndex
        if scanNumber == 0:
            return
        if scanNumber == 1:
            if 2 in self.collected:
                up_0 = self.scanMatrix[0, 2, 0]
                up_1 = self.scanMatrix[0, 2, 1]
                down_0 = self.scanMatrix[1, 2, 0]
                down_1 = self.scanMatrix[1, 2, 1]
            else:
                up_0 = self.scanMatrix[0, 0, 0]
                up_1 = self.scanMatrix[0, 0, 1]
                down_0 = self.scanMatrix[1, 0, 0]
                down_1 = self.scanMatrix[1, 0, 1]
        if scanNumber == 2:
            up_0 = self.scanMatrix[0, 1, 0]
            up_1 = self.scanMatrix[0, 1, 1]
            down_0 = self.scanMatrix[1, 1, 0]
            down_1 = self.scanMatrix[1, 1, 1]
        
        p = mp.Process(target=mydump, args=(up_0, up_1, down_0, down_1))
        p.start()
    
    def clear(self):
        self.upScanMatrix[:] = 0
        self.downScanMatrix[:] = 0
        
        self.upOnChipTemp[:] = 0
        self.downOnChipTemp[:] = 0
        self.scanIndex = 0

        self.reflectogrammIndex = 0
        self.matrixIndex = 0
        self.firstScan = True
        
        self.time[:] = 0
        self.temperature[:] = 0
        self.temperature2[:] = 0
        self.temperatureIndex = 0
        
        self.collected = set([])
        
        self.topIndexes = np.array([])
        self.bottomIndexes = np.array([])
        self.extremums = np.array([])

        self.starttime = time.time()
    
    def recreatecontainer(self):
        # 2 -- up and down scans
        # 3 -- three of down and up scans
        # 2 -- 2 polarisation state
        # 
        shape = (2, 3, 2, self.reflectogrammLength, self.spectraLength)
        N = np.prod(shape)
        print "newshape", shape
        self.shared = mp.Array(ctypes.c_double, N, lock=False)
        self.sharedArrayChanged.emit((self.shared, shape))
        
        self.scanMatrix = np.ctypeslib.as_array(self.shared)
        self.scanMatrix.shape = shape

        self.upScanMatrix = self.scanMatrix[0]
        self.downScanMatrix = self.scanMatrix[1]

        self.upScanMatrix[:] = 123
        self.downScanMatrix[:] = 123
        
        self.onChipTemp = np.zeros((2, 3, 2, self.spectraLength), dtype=int)
        self.upOnChipTemp = self.onChipTemp[0]
        self.downOnChipTemp = self.onChipTemp[1]
        self.nextIndex = (0, 0, 0, 0)

    def setSpectraLength(self, length):
        if self.spectraLength != length:
            self.spectraLength = length
            self.recreatecontainer()
        
    def setReflectogrammLength(self, lenght):
        if self.reflectogrammLength != lenght:
            self.reflectogrammLength = lenght
            self.recreatecontainer()
            
    def setNextIndex(self, index):
        self.nextIndex = index