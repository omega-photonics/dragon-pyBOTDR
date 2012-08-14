import multiprocessing as mp
import ctypes
from PyQt4 import QtCore 
from cython_corr_extra import correlate
import numpy as np
from scipy.optimize import brent, curve_fit, fmin_cg as leastsq
from fit import approximate
import chebyshev

import shared # its an empty module for IPC

def minimize(args):
    f_index, g_index = args
    pol_f_index = f_index[-2:]
    pol_g_index = g_index[-2:]
    data = dataFromShared()
    f = data[f_index]
    g = data[g_index]
    df, dg = dArraysFromShared()
    df = df[pol_f_index]
    dg = dg[pol_g_index]    
    fmin = lambda tau: -correlate(tau, f, g, df, dg) 
    appr = -f.argmax() + g.argmax()
    halfwidth = np.sum(f < f.max() / 2) / 2
    try: 
        return brent(fmin, brack=(appr - halfwidth, appr, appr + halfwidth))
    except ValueError:
        return -123.4

def aprlorentz(sp_index):
    data = dataFromShared()
    f = data[sp_index][1820:3640]
    return approximate(f, 1e-5)
    
    
def dataFromShared():
    data = np.ctypeslib.as_array(shared.scanmatrix)
    data.shape = shared.shape
    return data

def dArraysFromShared():
    df = np.ctypeslib.as_array(shared.df)
    dg = np.ctypeslib.as_array(shared.dg)
    dshape = (2, shared.shape[-2], shared.shape[-1] - 1)
    df.shape = dshape
    dg.shape = dshape
    return df, dg
    
    
def calculate(func, args):
    result = func(*args)
    return result

def calculatestar(args):
    return calculate(*args)    
   
def myprint(x):
    print x

    
class MemoryUpdater(QtCore.QObject):
    updated = QtCore.pyqtSignal()
    def __init__(self, parent=None):
        QtCore.QObject.__init__(self, parent)

    def updateShared(self, newshared_shape):
        # arrays are guaranteed to be shared
        newshared, shape = newshared_shape
        shared.scanmatrix = newshared
        
        # shape can probably be copied but it's small so it's ok.
        shared.shape = shape
        
        # now we need to update shared verison of differences
        N = shape[-3] * shape[-2] * (shape[-1] - 1)
        shared.df = mp.Array(ctypes.c_double, N, lock=False)
        shared.dg = mp.Array(ctypes.c_double, N, lock=False)
        self.updated.emit()
    
    
class Correlator(QtCore.QThread):
    measured = QtCore.pyqtSignal(np.ndarray)
    submatrix_processed = QtCore.pyqtSignal(np.ndarray)
    def __init__(self, parent=None):
        QtCore.QThread.__init__(self, parent)
        self.num = 0
        self.pool = mp.Pool(3)
        self.lastres = None
        self.dt = 1
        self.probes = None
        self.proberange = (3200, 3201)
    
    def set_probe_range(self, range):
        self.proberange = range 
    
    def process_submatrix(self, index):
        if index == (0, 0):
            self.num = 0
            self.probes = None
            self.choose_probes(index)
        self.setProbeIndex(index)
        self.findDistByIndex(index) # must be 0
   
    def choose_probes(self, index):
        scans = dataFromShared()[index]
        self.probes = []
        for i, scan in enumerate(scans):
            region = scan[self.proberange[0]:self.proberange[1]]
            pos = np.unravel_index(np.argmax(region), region.shape)[0]
            self.probes.append((i, pos + self.proberange[0]))
        print "Selected probes: {}".format(self.probes)

    def setProbeIndex(self, gIndex):
        self.probeIndex = gIndex
        #self.num = 1
        #np.save("probe".format(self.num), g[1000:2000])

    def setDt(self, dt):
        self.dt = dt
    
    def findDistByIndex(self, fIndex):
        self.dataIndex = fIndex
        self.start()
    
    # this function must be called when shared objects' place in memory change
    # it's happening on resizing of data arrays.
    def update(self): #, newshared_shape):
        # arrays are guaranteed to be shared
        #newshared, shape = newshared_shape
        #shared.scanmatrix = newshared
        
        ## shape can probably be copied but it's small so it's ok.
        #shared.shape = shape
        
        ## now we need to update shared verison of differences
        #N = shape[-2] * (shape[-1] - 1)
        #shared.df = mp.Array(ctypes.c_double, N, lock=False)
        #shared.dg = mp.Array(ctypes.c_double, N, lock=False)
        
        # now we need to restart calculator processes for them to be able to 
        # access shared arrays
        self.pool.close()
        self.pool.join()
        self.pool = mp.Pool(3)
    
    def run(self):
        print "Correlator run called"
        scanData = dataFromShared()
        df, dg = dArraysFromShared()
        print "loaded df, dg of shape {}, {}".format(df.shape, dg.shape)
        df[:] = np.diff(scanData[self.dataIndex])
        dg[:] = np.diff(scanData[self.probeIndex])
        print "Calculated diff df, dg of shape {}, {}".format(df.shape, dg.shape)
        dt = self.dt
        #np.save("data_{}".format(self.num), f[1000:2000])
        

        n_sp = shared.shape[-2]
        print "Shared data shape {}".format(shared.shape)
        res = []
        for pol in (0, 1):
            TASKS = [(self.dataIndex + (pol, i),
                      self.probeIndex + self.probes[pol]) \
                      for i in range(n_sp)]
            chunksize = len(TASKS) // 3 + 1
            res.append(self.pool.map(minimize, TASKS, chunksize=chunksize))
        preres = -np.array(res) # HACK to correspond other methods
        self.submatrix_processed.emit(preres)
        f = scanData[self.dataIndex]
        c = np.amax(f, axis=-1) - np.amin(f, axis=-1)
        av = (preres * c).sum(axis=0) / c.sum(axis=0)
        res = np.append(preres, [av], axis=0)
#            np.append(dist, [av])

        if self.num == 0:
            self.num = 1
            self.firstres = res
        else:
            dist = -self.firstres + res 
            dist[2] -= 30
            self.measured.emit(dist)
        
class Approximator(QtCore.QThread):
    measured = QtCore.pyqtSignal(np.ndarray)

    def __init__(self, parent=None):
        QtCore.QThread.__init__(self, parent)
        self.num = 0
        self.pool = mp.Pool(3)
        self.lastres = None
    
    def process_submatrix(self, fIndex):
        print "New data index to approximate:", fIndex
        self.dataIndex = fIndex
        self.start()
        
    def reset(self):
        self.num = 0
        self.lastres = None
    # this function must be called when shared objects' place in memory change
    # it's happening on resizing of data arrays.
    def update(self): #, newshared_shape):
        # arrays are guaranteed to be shared
        #newshared, shape = newshared_shape
        #shared.scanmatrix = newshared
        
        ## shape can probably be copied but it's small so it's ok.
        #shared.shape = shape
        
        # we don't uses differences. we must not update them.
        #N = shape[-2] * (shape[-1] - 1)
        #shared.df = mp.Array(ctypes.c_double, N, lock=False)
        #shared.dg = mp.Array(ctypes.c_double, N, lock=False)
        
        # now we need to restart calculator processes for them to be able to 
        # access shared arrays
        self.pool.close()
        self.pool.join()
        self.pool = mp.Pool(3)
    
    def run(self):
        scanData = dataFromShared()
        #np.save("data_{}".format(self.num), f[1000:2000])
        n = shared.shape[-2]        
        TASKS = [self.dataIndex + (j,) for j in range(2)]
        res = self.pool.map(aprlorentz, TASKS, chunksize=len(TASKS) // 3 + 1)
        param, stat = [np.array(x) for x in zip(*res)]

#        print "Approximated {} dots".format(res.shape)
#        print "Res for {} dots: {}".format(res[0,:0].shape, res[0,:0])
#        
#
#        if self.dataIndex == 1:
#            dist = -self.lastres - res
#            self.measured.emit(dist)
#            bottom, top = self.scanning_interval
#            self.measured.emit(2 * top - 2 * bottom + dist)
        
        self.lastres = param
        self.measured.emit(param)
      
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
            dist = -self.firstres + res 
            dist[2] -= 30
            dist += 50
            self.measured.emit(dist)

    def set_dt(self, dt):
        self.dt = dt

    def set_bottom(self, bot):
        self.bottom = bot

    
if __name__ == "__main__":
    import pylab as plt
    import time
    chan = 180
   
    f = np.loadtxt("/home/gleb/code/C/fit_spectra/sp.dat")
    pos = np.unravel_index(np.argmax(f), f.shape)
    print pos, f.shape
    findex = 123
    gindex = 13
    shift = 13
    g = np.roll(f[gindex], shift)
    f = f[findex] 
    print f.shape
    df = np.diff(f)
    dg = np.diff(g)
    
    fmin = lambda tau: -correlate(tau, f, g, df, dg) 
    halfwidth = np.sum(f < f.max() / 2) / 2
    appr = -f.argmax() + g.argmax()
    t = time.time()
    res = brent(fmin, brack=(appr-halfwidth,appr,appr+halfwidth))
    t2 = time.time()
    print t2 - t
    res2 = leastsq(fmin, x0=[appr], disp=0)
    print time.time() - t2
#    res = pool.map(minimize, TASKS, chunksize=340)
    
    print res, res2
#    fit = np.poly1d(np.polyfit(np.arange(len(f[0])), f[0], 12))
    plt.plot(f, label='f')
    plt.plot(g, label='g')
    plt.plot(np.roll(g, int(-res)), label='res')
    plt.legend()
    plt.show()
#    plt.plot(t_corr, corr)
#    plt.plot(res[chan], 1, "+")
#    plt.show()
#    plt.plot(fit(np.arange(len(f[0]))))
#    plt.show()
#    
#    plt.plot(res/dt, "-")
#    plt.show()
