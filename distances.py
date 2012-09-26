import multiprocessing as mp
import ctypes
from PyQt4 import QtCore 
import pycorrmax
import numpy as np
#from scipy.optimize import brent, curve_fit, fmin_cg as leastsq
#from fit import approximate
#import chebyshev

import shared # its an empty module for IPC

    
def dataFromShared():
    data = np.ctypeslib.as_array(shared.scanmatrix)
    data.shape = shared.shape
    return data
    
class MemoryUpdater(QtCore.QObject):
    updated = QtCore.pyqtSignal()
    def __init__(self, parent=None):
        QtCore.QObject.__init__(self, parent)
    def updateShared(self, newshared_shape):
        newshared, shape = newshared_shape
        shared.scanmatrix = newshared
        shared.shape = shape
        self.updated.emit()
    
    
class Correlator(QtCore.QThread):
    measured = QtCore.pyqtSignal(np.ndarray)
    submatrix_processed = QtCore.pyqtSignal(np.ndarray)
    def __init__(self, parent=None):
        QtCore.QThread.__init__(self, parent)
        self.num = 0
        self.lastres = None
        self.dt = 1
        self.argmax = pycorrmax.Argmax()    

    def process_submatrix(self, index):
        self.findDistByIndex(index) # must be 0
   
    def setDt(self, dt):
        self.dt = dt
    
    def findDistByIndex(self, fIndex):
        self.dataIndex = fIndex
        self.start()
    
    def update(self): 
        pass

    def run(self):
        scanData = dataFromShared()
        f = scanData[self.dataIndex]
        dt = self.dt
        n_sp = shared.shape[-2]
        res = [self.argmax(pol)[0] for pol in f]
        preres = -np.array(res) # HACK to correspond other methods
#        self.submatrix_processed.emit(preres)
        self.measured.emit(preres)
#        res = preres[:]
#
#        if self.num == 0:
#            self.num = 1
#            self.firstres = res
#        else:
#            dist = -self.firstres + res 
#            self.measured.emit(dist)
        
      
class Maximizer(QtCore.QThread):
    measured = QtCore.pyqtSignal(np.ndarray)
    def __init__(self, parent=None):
        QtCore.QThread.__init__(self, parent)
    
    def process_submatrix(self, index):
        scan = dataFromShared()[index]
        pos = self.bottom + self.dt * scan.argmax(axis=-1)
        self.measured.emit(pos)

    def set_dt(self, dt):
        self.dt = dt

    def set_bottom(self, bot):
        self.bottom = bot

class Chebyshev(QtCore.QThread):
    measured = QtCore.pyqtSignal(np.ndarray)
    submatrix_processed = QtCore.pyqtSignal(np.ndarray)
    def __init__(self, parent=None):
        QtCore.QThread.__init__(self, parent)
        self.dist = None
        self.level = 50.
    
    def process_submatrix(self, index):
        self.dataindex = index
        self.start()

    def run(self):
        index = self.dataindex
        scan = dataFromShared()[index]
        preres = np.array([chebyshev.calc_argmax(pol) for pol in scan])
        
        f = scan
        c = np.amax(f, axis=-1) - np.amin(f, axis=-1)
        av = (preres * c).sum(axis=0) / c.sum(axis=0)
        res = np.append(preres, [av], axis=0)
#            np.append(dist, [av])

        self.submatrix_processed.emit(preres)
        if self.dataindex == (0, 0):
            self.firstres = res
        else:
            self.dist = -self.firstres + res 
            self.dist[2] -= 30
            self.dist += self.level
            self.measured.emit(self.dist)

    def set_dt(self, dt):
        self.dt = dt

    def set_bottom(self, bot):
        self.bottom = bot
    
    def set_level(self, level):
        if self.dist is not None:
            self.dist += (level - self.level)
            self.measured.emit(self.dist)
        self.level = level

