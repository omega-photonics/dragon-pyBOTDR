from PyQt4 import QtCore
import numpy as np
from collections import namedtuple

Position = namedtuple("Position", "direction scannumber polarization freqindex")

class TimeScanner(QtCore.QObject):
    scanPositionChanged = QtCore.pyqtSignal(int)
    changeTemperature = QtCore.pyqtSignal(int)
    nextIndexChanged = QtCore.pyqtSignal(tuple)
    topReached = QtCore.pyqtSignal(int)
    bottomReached = QtCore.pyqtSignal(int)
    boundaryReached = QtCore.pyqtSignal(tuple)
    measured = QtCore.pyqtSignal(int)
    dtChanged = QtCore.pyqtSignal(float)
    bottomChanged = QtCore.pyqtSignal(int)
    UP, DOWN = 0, 1
    def __init__(self, n=100, parent=None):
        QtCore.QObject.__init__(self, parent)
        self.direction = TimeScanner.UP
        self.top = 65535
        self.bot = 0
        self.ndot = n
        self.nscans = 3
        #self.period = 60 # is not used for now
        self.debugprint = False
        self.updaterange()
        
    def setTop(self, top):
        self.top = top
        self.updaterange()
        
    def setBottom(self, bot):
        self.bot = bot
        self.updaterange()
        
    def setNdot(self, n):
        self.ndot = n
        self.updaterange()
    
    def updaterange(self):
        self.range = np.array(np.linspace(self.bot, self.top, self.ndot), dtype=int)
        self.temperatureList = np.append(self.range, self.range[::-1])
        self.dtChanged.emit(float(self.range[1]-self.range[0]))
        self.bottomChanged.emit(self.range[0])
        # for each scan we have 2 directions,
        # for each dirrection we have 2 polarization states
        self.statesNumber = self.nscans * self.ndot * 2 * 2 
        self.reset()
        
    def measure(self):
        targetT = self.temperatureList[self.pos.freqindex]
        if self.pos.direction == TimeScanner.UP:
            self.measured.emit(targetT)
        else:
            self.measured.emit(2 * self.top - targetT)
    
    def stateToPos(self, state):
        rest, polarization = divmod(state, 2)
        rest, tempindex = divmod(rest, self.ndot)
        rest, direction = divmod(rest, 2)
        rest, scannumber = divmod(rest, self.nscans)
        assert rest == 0, "Index calculation failed"
        if direction == TimeScanner.DOWN:
            tempindex = self.ndot - tempindex - 1  
        pos = Position(direction, scannumber, polarization, tempindex)
        return pos
    
    def inc(self):
        if self.state is None:
            self.state = 0
            self.pos = self.stateToPos(self.state)
            return
            
        self.state = self.state + 1 
        if self.state == self.statesNumber:
            self.state = self.ndot * 2 * 2 
        self.pos = self.stateToPos(self.state)
    
    def scan(self):
        self.inc()
        pos = self.pos
        if self.debugprint:
            self.debugprint = False
            print "debug print! pos:", self.pos
            
        self.nextIndexChanged.emit(pos)
        targetT = self.temperatureList[pos.freqindex]
        self.changeTemperature.emit(targetT)
        if pos.direction == TimeScanner.UP:
            self.scanPositionChanged.emit(targetT)
        else:
            self.scanPositionChanged.emit(2 * self.top - targetT)
        if pos.freqindex == 0 and \
            pos.direction == TimeScanner.DOWN and \
            pos.polarization == 1:
            print "bottom reached! pos:", self.pos
            self.debugprint = True
            self.bottomReached.emit(pos.scannumber)
            self.boundaryReached.emit((pos.direction, pos.scannumber))

        if pos.freqindex == self.ndot - 1 and \
            pos.polarization == 1 and \
            pos.direction == TimeScanner.UP :
            print "top reached! pos:", self.pos
            self.debugprint = True
            self.topReached.emit(pos.scannumber)
            self.boundaryReached.emit((pos.direction, pos.scannumber))
            
        
    def reset(self):
        self.state = None
        self.pos = None
