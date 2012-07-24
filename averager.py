from PyQt4 import QtCore
import numpy as np

class Averager(QtCore.QThread):
    measured = QtCore.pyqtSignal(np.ndarray)
    def __init__(self, parent=None):
        QtCore.QObject.__init__(self, parent)
        self.distances = []
        self.number = 10
    
    def setNumber(self, number):
        self.number = number
    
    def appendDistances(self, distances):
        self.distances.append(distances)
        if len(self.distances) > self.number:
            self.distances.pop(0)
        if len(self.distances) >= self.number:
            self.start()
        print "averager has {} of {} samples".format(len(self.distances), self.number)
            
    def run(self):
        res = np.zeros(len(self.distances[-1]), dtype=float)
        for i in range(self.number):
            res += self.distances[-i - 1]
        res /= self.number
        self.measured.emit(res)
            
    def clear(self):
        self.distances = []
    