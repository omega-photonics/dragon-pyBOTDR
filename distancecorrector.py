from PyQt4 import QtCore

class DistanceCorrector(QtCore.QObject):
    correct = QtCore.pyqtSignal(int)
    
    def __init__(self, parent=None):
        QtCore.QObject.__init__(self, parent)
        self.dist = []
        self.maxlen = 100
        self.enabled = False
        self.saferange = (25000, 40000)
        self.channel = 0
        
    def setEnabled(self, state):
        self.enabled = state
    
    def setChannel(self, channel):
        self.channel = channel
    
    def setA(self, A):
        print "New A is ", A
        self.A = A
        
    def setTargetDistance(self, dist):
        self.targetDist = dist
    
    def appendDistances(self, dist):
        print "Dist shape is ", dist.shape
        print "Channel is ", self.channel
        self.dist.append(dist[self.channel])
        if len(self.dist) > self.maxlen:
            self.dist.pop(0)
        self.react()
    
    def setReaction(self, reaction):
        print "New reaction set is ", reaction
        self.reaction = reaction
        
    def react(self):
        diff = self.targetDist - self.dist[-1]
        res = diff * self.A
        newreaction = self.reaction + res
        print "Last Distance is ", self.dist[-1]
        print "diff and A are", diff, self.A
        print "New reaction should be", newreaction
        if self.enabled and self.saferange[0] < newreaction < self.saferange[1]:
            self.correct.emit(int(newreaction))
        else:
            print "DistanceCorrector was trying to set values from critical range"
            print "Aborted"
