from __future__ import division

from PyQt4 import Qt, QtCore, QtGui, uic, Qwt5 as Qwt
#import sys
import ctypes
import struct
import socket
import mysocket
import time
import multiprocessing as mp
from multiprocessing.sharedctypes import SynchronizedArray
from collections import namedtuple
import numpy as np
from scipy.optimize import brent as minimize
import array
import client
import  pciedevsettings
import peak
import pickle

from datetime import datetime
from dump import mydump
from distances import Correlator, Averager, MemoryUpdater

STARTING_N_SP_DOT = 100 # need to do smthn with settings!

HOST = "localhost"
#HOST = '192.168.1.223'    # The remote host
USBPORT = 32100             # The same port as used by the server
PCIEPORT = 32120
UNIPORT = 32140

Curve = namedtuple("Curve", "x y")

SIGNAL_TOP = 150000
SIGNAL_BOT = -10000


def myprint(x):
    print(x[100:1000])


def mypeakdetection(spectra):
    tmp_sp = Curve(spectra.x, spectra.y[:, 1100:1200])
    res = peak.detectsinglepeak(tmp_sp)
    npeaks = np.sum(res.status == peak.Status.ok)
    nfails = np.sum(res.status == peak.Status.fail)
    ncropped = np.sum(res.status == peak.Status.cropped)

    nch = len(res.status)
    
    #print "Found {} peaks, {} cropped and {} fails in {} channels"\
    #.format(npeaks, ncropped, nfails, nch)
    return  npeaks, ncropped, nfails, nch

    
DragomBase, DragonForm = uic.loadUiType("dragon.ui")
class DragonWidget(DragomBase, DragonForm):
    valueChanged = QtCore.pyqtSignal(pciedevsettings.PCIESettings)
    def __init__(self, parent=None):
        super(DragomBase, self).__init__(parent)
        self.setupUi(self)
        
        self._value = self.value()
        for widget in [ self.ch1amp, self.ch1shift, self.ch1count,
                        self.ch2amp, self.ch2count, self.ch2shift,
                        self.framelength, self.framecount]:
            widget.valueChanged.connect(self.rereadValue)
            
    def value(self):
        return pciedevsettings.PCIESettings(
            ch1amp = self.ch1amp.value(),
            ch1count = self.ch1count.value(),
            ch1shift = self.ch1shift.value(),
            ch2amp = self.ch2amp.value(),
            ch2count = self.ch2count.value(),
            ch2shift = self.ch2shift.value(),
            framelength = self.framelength.value(),
            framecount = self.framecount.value())
    
    def rereadValue(self):
        val = self.value()
        if val != self._value:
            self._value = val
            self.valueChanged.emit(val)

TermoBase, TermoForm = uic.loadUiType("botdrmainwindow.ui")
class TermoWidget(TermoBase, TermoForm):
    valueChanged = QtCore.pyqtSignal(client.USBSettings)
    def __init__(self, val, parent=None):
        super(TermoBase, self).__init__(parent)
        self.setupUi(self)
        self.setValue(val)
        for widget in [self.T1set, self.A1, self.B1, self.C1,
                       self.T2set, self.A2, self.B2, self.C2,
                       self.Tchip]:
            widget.valueChanged.connect(self.rereadValue)
    
    def setValue(self, val):
        self._value = val.settings
        valDict = val.settings._asdict()
        for prop in ["T1set", "A1", "B1", "C1",
                     "T2set", "A2", "B2", "C2", "Tchip"]:
            self.__dict__[prop].setValue(valDict[prop])
        
    def value(self):
        return client.default._replace(T1set=self.T1set.value(),
                                       T2set=self.T2set.value(),
                                       A1=self.A1.value(), A2=self.A2.value(),
                                       B1=self.B1.value(), B2=self.B2.value(),
                                       C1=self.C1.value(), C2=self.C2.value(),
                                       Tchip=self.Tchip.value())
    
    def rereadValue(self):
        val = self.value()
        if val != self._value:
            self._value = val
            self.valueChanged.emit(val)

    def showResponse(self, response):
        self.T1read.setText("T1  " + repr(response.T1))
        self.T2read.setText("T2  " + repr(response.T2))
        
        self.R1.setText("R1  " + repr(response.R1))
        self.R2.setText("R2  " + repr(response.R2))
        
class USBNetWorker(QtCore.QThread):
    measured = QtCore.pyqtSignal(client.USBResponse)
    
    def __init__(self, settings, parent=None):
        QtCore.QThread.__init__(self, parent)
        self._settings = settings
        self._stackedsettings = None
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((HOST, USBPORT))
        self.lock = QtCore.QMutex()
        self.exiting = False
        self.stackcounter = 0
        
    def setUSBSettings(self, settings):
        #print "setting USB", settings.T1set
        if not self.isRunning():
            self._settings = settings
            self.start()
        else:
            self.lock.lock()
            self._stackedsettings = settings
            self.lock.unlock()
    
    def measure(self):
        self.start()

        
    def run(self):
        if not self.exiting:
            #print "setting in thread", self._settings.T1set
            buf = self._settings.asbuffer()
            self.socket.sendall(buf)
            self.socket.recv_into(buf, 64)
            self.measured.emit(client.USBResponse.frombuffer(buf))
            self.lock.lock()
            if self._stackedsettings != None:
                #print "restoring", self._stackedsettings.T1set
                self._settings = self._stackedsettings
                self._stackedsettings = None
                self.lock.unlock()
                #self.run()   # this crashes stack
                buf = self._settings.asbuffer()
                self.socket.sendall(buf)
                self.socket.recv_into(buf, 64)
                self.measured.emit(client.USBResponse.frombuffer(buf))
            else:
                self.lock.unlock()
 
    def stop(self):
        self.wait()
        self.exiting = True
        self.socket.close()
        
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
            response.activechannel = struct.unpack("B", self.socket.recvall(1))[0]
            response.framelength = 6 * struct.unpack("H", self.socket.recvall(2))[0]
            response.framecount = struct.unpack("I", self.socket.recvall(4))[0]
            response.dacdata = struct.unpack("I", self.socket.recvall(4))[0]
            tmpusbdata = self.socket.recvall(16)
            rawdata = self.socket.recvall(pciedevsettings.PCIESettings.MaxFrameLenght, timeout=5)
            
            data = array.array("d")
            data.fromstring(rawdata)
            data = np.array(data)
            response.data = data
            self.measured.emit(response)
            
            self.lock.lock()
            self.socket.sendall(struct.pack("I", self.settings.counts))
            self.socket.sendall(struct.pack("H", int(self.settings.framelength / 6)))
            self.socket.sendall(struct.pack("I", self.settings.framecount))
            self.socket.sendall(struct.pack("I", self.settings.dacdata))
            self.lock.unlock()
            
            self.socket.sendall(tmpusbdata)
    
    def stop(self):
        self.exiting = True
        self.wait()
        self.socket.close()

        
ScannerBase, ScannerForm = uic.loadUiType("scanner.ui")
class ScannerWidget(ScannerBase, ScannerForm):
    def __init__(self, parent=None):
        super(ScannerBase, self).__init__(parent)
        self.setupUi(self)

Base, Form = uic.loadUiType("window.ui")
class Window(Base, Form):
    def __init__(self, parent=None):
        super(Base, self).__init__(parent)
        self.setupUi(self)
        
        
        self.temperaturesettings = TemperatureSettings(self)
        self.termo = TermoWidget(self.temperaturesettings, parent=self)
        self.dragon = DragonWidget(self)
        self.scannerwidget = ScannerWidget(self)
        self.chipscannerwidget = uic.loadUi("timescanner.ui")
        self.dragonplot = Plot(QtCore.QRectF(0, SIGNAL_BOT, 8*6144, SIGNAL_TOP - SIGNAL_BOT), self)
        self.temperatureplot = TempPlot(self)
        self.spectraplot = SlicePlot(self)
        self.distanceplot = Plot(QtCore.QRectF(0, -65535, 8*6144, 2*65535), self, zeroed=True, points=True, ncurves=2)

        

        pcie_settings = self.dragon.value()
        
        
        self.PCIEThread = PCIENetWorker(self)
        self.USBthread = USBNetWorker(self.temperaturesettings.settings, self)
        self.collector = Collector(pcie_settings.framelength, STARTING_N_SP_DOT, self)
        self.memoryupdater = MemoryUpdater(self)
        self.correlator = Correlator(self)
        self.averager = Averager(self)
        self.scanner = Scanner(self)
        self.timescanner = TimeScanner(self)
        
        self.PCIEThread.setPCIESettings(pcie_settings)
        self.PCIEThread.start()
        self.USBthread.start()
        #self.TermoTimer = QtCore.QTimer()
        #self.TermoTimer.timeout.connect(self.USBthread.measure)
        #self.TermoTimer.start(350)
        self.settings.addWidget(self.chipscannerwidget)
        self.settings.addWidget(self.scannerwidget)
        self.settings.addWidget(self.termo )
        self.settings.addWidget(self.dragon)
        
        self.plots.addWidget(self.spectraplot, 0, 0, 1, 1)
        self.plots.addWidget(self.temperatureplot, 0, 1)
        self.plots.addWidget(self.dragonplot, 1, 1)
        self.plots.addWidget(self.distanceplot, 1, 0, 1, 1)
        
        self.termo.valueChanged.connect(self.temperaturesettings.setValue)
        self.scanner.changeTemperature.connect(self.temperaturesettings.setT1)
        self.temperaturesettings.valueChanged.connect(self.USBthread.setUSBSettings)
        self.dragon.valueChanged.connect(self.PCIEThread.setPCIESettings)
        self.USBthread.measured.connect(self.termo.showResponse)
        
        self.PCIEThread.measured.connect(self.collector.appendDragonRespose)
        self.PCIEThread.measured.connect(self.USBthread.measure)
        self.USBthread.measured.connect(self.collector.appendUSBResponse)
        self.collector.reflectogrammChanged.connect(self.timescanner.measure)
        #self.PCIEThread.measured.connect(self.timescanner.accuratescan)
        self.timescanner.measured.connect(self.collector.appendOnChipTemperature)
        self.timescanner.changeTemperature.connect(self.temperaturesettings.setTchip)
        
        self.collector.temperatureCurveChanged.connect(lambda v:self.temperatureplot.myplot(v, 0))
        self.collector.temperatureCurve2Changed.connect(lambda v:self.temperatureplot.myplot(v, 1))
        self.collector.reflectogrammChanged.connect(self.dragonplot.myplot)
        self.collector.spectraOnChipChanged.connect(self.spectraplot.setData)
        self.collector.spectraChanged.connect(mypeakdetection)
        self.collector.scanPositionChanged.connect(self.chipscannerwidget.position.setNum)
        
        self.collector.sharedArrayChanged.connect(self.memoryupdater.updateShared)
        self.memoryupdater.updated.connect(self.correlator.update)
        self.memoryupdater.updated.connect(self.averager.update)
        self.timescanner.dtChanged.connect(self.correlator.setDt)
        self.timescanner.dtChanged.connect(self.averager.setDt)
        
        self.memoryupdater.updateShared((self.collector.shared, (2,) + self.collector.upScanMatrix.shape))
        self.correlator.setDt(65535. / STARTING_N_SP_DOT)
        self.correlator.measured.connect(self.distanceplot.myplot)

        self.averager.setDt(65535. / STARTING_N_SP_DOT)
        self.averager.measured.connect(lambda t: self.distanceplot.myplot(t, n=1))
        
        self.scannerwidget.clear.clicked.connect(self.collector.clear)
        self.scannerwidget.clear.clicked.connect(self.spectraplot.clear)
        self.scannerwidget.clear.clicked.connect(self.timescanner.reset)
        self.scannerwidget.scan.clicked.connect(
            lambda val: self.termo.setEnabled(not val))
            
        self.scannerwidget.scan.clicked.connect(self.startscan)
        self.scannerwidget.accurateScan.clicked.connect(self.startaccuratescan)
        self.chipscannerwidget.accurateScan.clicked.connect(self.startaccuratetimescan)
        self.chipscannerwidget.saveData.clicked.connect(self.collector.savelastscan)
        self.chipscannerwidget.saveView.clicked.connect(self.saveView)

        
        self.scannerwidget.search.clicked.connect(
            lambda val: self.termo.setEnabled(not val))
        self.scannerwidget.search.clicked.connect(self.startsearch)
        self.scannerwidget.search.clicked.connect(self.scanner.reinitSearch)
        
        self.scannerwidget.top.valueChanged.connect(self.scanner.setTop)
        self.scannerwidget.bottom.valueChanged.connect(self.scanner.setBottom)
        self.scannerwidget.nsteps.valueChanged.connect(self.scanner.setNdot)
        self.scannerwidget.channel.valueChanged.connect(self.spectraplot.setChannel)

        self.chipscannerwidget.top.valueChanged.connect(self.timescanner.setTop)
        self.chipscannerwidget.bottom.valueChanged.connect(self.timescanner.setBottom)
        self.chipscannerwidget.nsteps.valueChanged.connect(self.timescanner.setNdot)
        self.chipscannerwidget.nsteps.valueChanged.connect(self.collector.setSpectraLength)
        
        
        self.scanner.rangeFound.connect(self.scannerwidget.scan.click)
        #self.PCIEThread.measured.connect(myprint)
        
    def startscan(self, value):
        self.startcustomscan(value, self.scanner.scan)
    
    def startaccuratescan(self, value):
        self.startcustomscan(value, self.scanner.accuratescan)

    def startcustomscan(self, value, callback):
        if value:
            self.USBthread.measured.connect(self.scanner.setLastTempResponse)
            self.PCIEThread.measured.connect(callback)
            self.scanner.changeTemperature.connect(
                self.temperaturesettings.setT1)
        else:
            self.USBthread.measured.disconnect(self.scanner.setLastTempResponse)
            self.PCIEThread.measured.disconnect(callback)
            self.scanner.changeTemperature.disconnect(
                self.temperaturesettings.setT1)
                
    def startsearch(self, value):
        if value:
            # stop scans
            #self.startaccuratescan.(False)
            #self.startscan(False)
            
            self.collector.spectraChanged.connect(self.scanner.search)
            self.scanner.changeTemperature.connect(
                self.temperaturesettings.setT1)
            self.scanner.topReached.connect(self.collector.clear)
            self.scanner.topReached.connect(self.scannerwidget.top.setValue)
            self.scanner.bottomReached.connect(self.collector.clear)
            self.scanner.bottomReached.connect(self.scannerwidget.bottom.setValue)
            self.scanner.rangeFound.connect(myprint)
            self.scanner.rangeFound.connect(self.scannerwidget.search.click)
        else:
            self.collector.spectraChanged.disconnect(self.scanner.search)
            self.scanner.changeTemperature.disconnect(
                self.temperaturesettings.setT1)
            self.scanner.topReached.disconnect(self.collector.clear)
            self.scanner.topReached.disconnect(self.scannerwidget.top.setValue)
            self.scanner.bottomReached.disconnect(self.collector.clear)
            self.scanner.bottomReached.disconnect(self.scannerwidget.bottom.setValue)

            self.scanner.rangeFound.disconnect(myprint)
            self.scanner.searchstate = Scanner.REACHTOP
                
    def startaccuratetimescan(self, val):
        if val:
            self.temperaturesettings.setTchip(0)
            QtCore.QTimer.singleShot(5000, self._cont)
            print "wait 5 sec.."

        else:
            self.collector.reflectogrammChanged.disconnect(self.timescanner.accuratescan)
            self.collector.probeMatrixMeasured.disconnect(self.correlator.setProbeIndex)
            self.collector.newMatrixMeasured.disconnect(self.correlator.findDistByIndex)
            self.collector.probeMatrixMeasured.disconnect(self.averager.findDistByIndex)
            self.collector.newMatrixMeasured.disconnect(self.averager.findDistByIndex)
            self.averager.reset()
            
    def _cont(self):
        print "started"
        self.collector.clear()
        self.timescanner.reset()
        self.collector.reflectogrammChanged.connect(self.timescanner.accuratescan)
        self.collector.probeMatrixMeasured.connect(self.correlator.setProbeIndex)
        self.collector.newMatrixMeasured.connect(self.correlator.findDistByIndex)
        
        self.collector.probeMatrixMeasured.connect(self.averager.findDistByIndex)
        self.collector.newMatrixMeasured.connect(self.averager.findDistByIndex) 
 
    def closeEvent(self, event):
        self.temperaturesettings.save()
        self.PCIEThread.stop()
        self.USBthread.stop()
        
    def saveView(self):
        savepath = "/home/gleb/dumps/" + datetime.now().isoformat() + ".png"
        QtGui.QPixmap.grabWidget(self).save(savepath)
        
class Plot(Qwt.QwtPlot):
    colors = [Qt.Qt.black, Qt.Qt.red, Qt.Qt.blue]
    def __init__(self, rect, parent=None, zeroed=False, points=False, ncurves=1):
        QtCore.QObject.__init__(self, parent)
        self.curves = []
        for i in range(ncurves):
            curve = Qwt.QwtPlotCurve()
            curve.attach(self)
            if not points:
                curve.setPen(QtGui.QPen())
            else:
                curve.setStyle(Qwt.QwtPlotCurve.NoCurve)
                curve.setSymbol(Qwt.QwtSymbol(Qwt.QwtSymbol.Ellipse, Plot.colors[i],
                    QtGui.QPen(Plot.colors[i]), Qt.QSize(3,3)))
            self.curves.append(curve)
        self.zoom = Qwt.QwtPlotZoomer(Qwt.QwtPlot.xBottom,
                                Qwt.QwtPlot.yLeft,            
                                self.canvas())
        self.zoom.setZoomBase(rect)
        self.zeroed = zeroed
        
    def myplot(self, data, n=0):

        if type(data) is Curve:
            _x = data.x
            _y = data.y
        else:
            _x = np.arange(len(data))
            _y = data
        if not self.zeroed:
            self.curves[n].setData(_x, _y)
        else:
            self.curves[n].setData(_x, _y - np.average(_y[250:1250]))
        self.replot()


class TempPlot(Qwt.QwtPlot):
    def __init__(self, parent=None):
        QtCore.QObject.__init__(self, parent)
        self.curves = []
        for i in range(2):
            self.curves.append(Qwt.QwtPlotCurve())
            self.curves[i].attach(self)
        for i, col in enumerate([Qt.Qt.black, Qt.Qt.blue]):
            self.curves[i].setPen(QtGui.QPen(col))
        self.zoom = Qwt.QwtPlotZoomer(Qwt.QwtPlot.xBottom,
                                      Qwt.QwtPlot.yLeft,            
                                      self.canvas())
        self.zoom.setZoomBase(QtCore.QRectF(0, 0, 65535, 1000))
    def myplot(self, data, n):
        if type(data) is Curve:
            self.curves[n].setData(data.x, data.y)
        else:
            _x = np.arange(len(data))
            _y = data
            self.curves[n].setData(_x, _y)
        if self.zoom.zoomRectIndex() == 0:
            self.setAxisAutoScale(Qwt.QwtPlot.xBottom)
            self.setAxisAutoScale(Qwt.QwtPlot.yLeft)
            self.replot()
            self.zoom.setZoomBase(False)
        else:
            self.zoom.setZoomBase(QtCore.QRectF(0, 0, data.x[-1], 65535))
            self.setAxisAutoScale(Qwt.QwtPlot.xBottom)
            #self.setAxisAutoScale(Qwt.QwtPlot.yLeft)
            self.replot()
        
        

class SlicePlot(Qwt.QwtPlot):
    colors = [Qt.Qt.red, Qt.QColor(100,100,100), Qt.Qt.black]
                  
    def __init__(self, parent=None):
        QtCore.QObject.__init__(self, parent)
        self.curve = Qwt.QwtPlotCurve('')
        self.curve.attach(self)
        #self.curve.setPen(QtGui.QPen())
        self.zoom = Qwt.QwtPlotZoomer(Qwt.QwtPlot.xBottom,
                                      Qwt.QwtPlot.yLeft,            
                                      self.canvas())
        self.zoom.setZoomBase(QtCore.QRectF(-1000, SIGNAL_BOT, 2*65535+2000, SIGNAL_TOP - SIGNAL_BOT))
        self.curve.setStyle(Qwt.QwtPlotCurve.NoCurve)
        self.curve.setSymbol(Qwt.QwtSymbol(Qwt.QwtSymbol.Ellipse, QtGui.QBrush(Qt.Qt.black),
                 QtGui.QPen(), Qt.QSize(3,3)))
        self.channel = 1000
        self.colorNum = 0
        self.upcurves = []
        self.downcurves = []
        self.updatacurves = []
        self.downdatacurves = []
        
    def setChannel(self, val):
        self.channel = val
        self.myplot()
    def setData(self, data):
        self.updatacurves, self.downdatacurves = data[0], data[1]
        self.myplot()
    
    def myplot(self):
        ndatacurves = len(self.upcurves) + len(self.downcurves)
        #print len(self.upcurves), "UpCurves,", len(self.downcurves), "DownCurves"
        #print len(self.updatacurves), "UpDataCurves,", len(self.downdatacurves), "DownDataCurves"
        
        for curves, datacurves in \
            [(self.upcurves, self.updatacurves),
             (self.downcurves, self.downdatacurves)]:
            while len(curves) < len(datacurves):
                color = SlicePlot.colors[len(curves)]
                curves.append(Qwt.QwtPlotCurve(''))
                curves[-1].attach(self)
                curves[-1].setStyle(Qwt.QwtPlotCurve.NoCurve)
                curves[-1].setSymbol(Qwt.QwtSymbol(Qwt.QwtSymbol.Ellipse, QtGui.QBrush(color),
                        QtGui.QPen(color), Qt.QSize(3,3)))
            for i, datacurve in enumerate(datacurves):
                curves[i].setData(datacurve.x, datacurve.y[self.channel])
        
        self.replot()        
    
    def clear(self):
        self.detachItems()
        self.upcurves = []
        self.downcurves = []
        self.updatacurves = []
        self.downdatacurves = []
        
        
class Collector(QtCore.QObject):
    reflectogrammChanged = QtCore.pyqtSignal(np.ndarray)
    temperatureCurveChanged = QtCore.pyqtSignal(Curve)
    temperatureCurve2Changed = QtCore.pyqtSignal(Curve)
    scanPositionChanged = QtCore.pyqtSignal(int)
    spectraChanged = QtCore.pyqtSignal(Curve)
    spectraOnChipChanged = QtCore.pyqtSignal(tuple)
    sharedArrayChanged = QtCore.pyqtSignal(tuple)
    probeMatrixMeasured = QtCore.pyqtSignal(tuple)
    newMatrixMeasured = QtCore.pyqtSignal(tuple)
    def __init__(self, reflen, speclen, parent=None):
        QtCore.QObject.__init__(self, parent)
        # always waits for reflectogramm, appending temp. measurements
        # only if needed
        self.waitingForTemperature = False
        self.firstScan = True
        self.scanIndex = 0
        self.matrixIndex = 0
        self.reflectogrammIndex = 0
        self.temperatureIndex = 0           # for outer stabilization 
        self.reflectogrammLength = reflen
        self.spectraLength = speclen
        self.recreatecontainer()
        self.starttime = time.time()
        self.time = np.zeros(30000)
        self.temperature = np.zeros(30000)
        self.temperature2 = np.zeros(30000)
        
    def appendDragonRespose(self, response):
        #print "Active channel", response.activechannel
        if response.activechannel != 0:
            return
        
        #print "Data shape", response.data.shape
        #print "Matrix shape", self.ch1matrix.shape
        #print "Frame count", response.framecount
        #print "Frame lenght", response.framelength
        if self.waitingForTemperature:
            print "Temperature mesurements are too slow"
            return
        
        d = np.diff(response.data[:response.framelength])
        K = np.max(np.abs(d)) / np.median(np.abs(d))
        if K > 1000:
            print "Step detected", K
            return
        response.data[:response.framelength] -= np.average(response.data[-1000:])
        
        if self.matrixIndex % 2 == 0:
            matrix = self.upScanMatrix
            #print self.upScanMatrix[self.matrixIndex // 2,:,self.reflectogrammIndex].shape
            #print response.data[:response.framelength].shape
            #print self.matrixIndex // 2, self.reflectogrammIndex, response.framelength
            self.upScanMatrix[self.matrixIndex // 2,:,self.reflectogrammIndex] = response.data[:response.framelength]
            self.lastIndex = (self.matrixIndex // 2, self.reflectogrammIndex)
            self.lastdir = "up"
        else:
            matrix = self.downScanMatrix
            self.downScanMatrix[self.matrixIndex // 2,:, -self.reflectogrammIndex-1] = response.data[:response.framelength]
            self.lastIndex = (self.matrixIndex // 2, -self.reflectogrammIndex-1)
            self.lastdir = "down"
        
        
        self.reflectogrammIndex += 1
        if self.reflectogrammIndex == self.spectraLength:
            self.reflectogrammIndex = 0
            if self.firstScan:
                self.probeMatrixMeasured.emit((self.matrixIndex % 2, self.matrixIndex//2))
                self.firstScan = False
            else:
                self.newMatrixMeasured.emit((self.matrixIndex % 2, self.matrixIndex//2))
            self.matrixIndex += 1
            
            if self.matrixIndex % 2 == 0:
                self.scanIndex += 1

            if self.matrixIndex == 6:
                self.matrixIndex = 2

        self.reflectogrammChanged.emit(response.data[:response.framelength]) #?

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
            
            self.temperatureIndex = 30000 // 2 + 1 
            #s = Curve(x=self.temperature, y=self.ch1matrix)
            #self.spectraChanged.emit(s)
            #self.waitingForTemperature = False
    
    def appendOnChipTemperature(self, temp):
        if self.lastdir == "up":
            self.upOnChipTemp[self.lastIndex] = temp
            self.scanPositionChanged.emit(temp)
        else:
            self.downOnChipTemp[self.lastIndex] = temp
            self.scanPositionChanged.emit(-temp + 2 * self.downOnChipTemp[self.lastIndex[0],-1])
        
        upcurves = []
        for i in range(3):
            upcurves.append(
            Curve(x=self.upOnChipTemp[i],
                  y=self.upScanMatrix[i])
            )
        downcurves = []
        for i in range(3):
            downcurves.append(
            Curve(x=-self.downOnChipTemp[i] + 2 * self.downOnChipTemp[i,-1],
                  y=self.downScanMatrix[i])
            )
        self.spectraOnChipChanged.emit((upcurves, downcurves))
    
    def savelastscan(self):
        print "self.scanIndex:", self.scanIndex
        if self.scanIndex == 0:
            return
        if self.scanIndex == 1:
            up = self.upScanMatrix[0]
            down = self.downScanMatrix[0]
        if self.scanIndex % 2 == 0:
            up = self.upScanMatrix[1]
            down = self.downScanMatrix[1]
        if self.scanIndex % 2 == 1:
            up = self.upScanMatrix[2]
            down = self.downScanMatrix[2]
        
        p = mp.Process(target=mydump, args=(up, down))
        p.start()
    
    def clear(self):
        #print "collector.clean"
        self.upScanMatrix[:] = 0
        self.downScanMatrix[:] = 0
        
        self.upOnChipTemp[:] = 0
        self.downOnChipTemp[:] = 0
        self.scanIndex = 0

        self.reflectogrammIndex = 0
        self.matrixIndex = 0
        self.firstScan = True
        
        #self.onchiptemp = np.array([], dtype=int)
        
        self.time[:] = 0
        self.temperature[:] = 0
        self.temperature2[:] = 0
        self.temperatureIndex = 0
        
        self.topIndexes = np.array([])
        self.bottomIndexes = np.array([])
        self.extremums = np.array([])

        self.starttime = time.time()
    
    def recreatecontainer(self):
        # 2 -- up and down scans
        # 3 -- three of down and up scans
        # 
        N = 2 * 3 * self.reflectogrammLength * self.spectraLength 
        shape = (2, 3, self.reflectogrammLength, self.spectraLength)
        
        self.shared = mp.Array(ctypes.c_double, N, lock=False)
        self.sharedArrayChanged.emit((self.shared, shape))
        
        scanMatrix = np.ctypeslib.as_array(self.shared)
        scanMatrix.shape = shape

        self.upScanMatrix = scanMatrix[0]
        self.downScanMatrix = scanMatrix[1]

        self.upScanMatrix[:] = 0
        self.downScanMatrix[:] = 0
        
        self.upOnChipTemp = np.zeros((3, self.spectraLength), dtype=int)
        self.downOnChipTemp = np.zeros((3, self.spectraLength), dtype=int)

    def setSpectraLength(self, length):
        self.spectraLength = length
        self.recreatecontainer()
        
    def setReflectogrammLength(self, lenght):
        self.reflectogrammLength = lenght
        self.recreatecontainer()
            
                
class TemperatureSettings(QtCore.QObject):
    valueChanged = QtCore.pyqtSignal(client.USBSettings)
    def __init__(self, parent=None):
        QtCore.QObject.__init__(self, parent)
        try:
            f = open("tempsetings.pickle", "r")
        except IOError:
            self.settings = client.default
        else:
            self.settings = pickle.load(f)
            f.close()
            
    def setValue(self, val):
        self.settings = val
        self.valueChanged.emit(self.settings)
    
    def setT1(self, T1):
        self.settings = self.settings._replace(T1set=T1)
        self.valueChanged.emit(self.settings)
    def setA1(self, A1):
        self.settings = self.settings._replace(A1=A1)
        self.valueChanged.emit(self.settings)
    def setB1(self, B1):
        self.settings = self.settings._replace(B1=B1)
        self.valueChanged.emit(self.settings)
    def setC1(self, C1):
        self.settings = self.settings._replace(C1=C1)
        self.valueChanged.emit(self.settings)
        
    def setT2(self, T2):
        self.settings = self.settings._replace(T2set=T2)
        self.valueChanged.emit(self.settings)
    def setA2(self, A2):
        self.settings = self.settings._replace(A2=A2)
        self.valueChanged.emit(self.settings)
    def setB2(self, B2):
        self.settings = self.settings._replace(B2=B2)
        self.valueChanged.emit(self.settings)
    def setC2(self, C2):
        self.settings = self.settings._replace(C2=C2)
        self.valueChanged.emit(self.settings)
    def setTchip(self, T):
        self.settings = self.settings._replace(Tchip=T)
        self.valueChanged.emit(self.settings)        

    def save(self):
        f = open("tempsetings.pickle", "w")
        pickle.dump(self.settings, f)
        f.close()
    
def main():
    app = QtGui.QApplication(sys.argv)
    wnd = Window()
    wnd.show()
    sys.exit(app.exec_())
    
if __name__ == "__main__":
    main()
