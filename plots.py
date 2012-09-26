from PyQt4 import Qt, QtCore, QtGui, Qwt5 as Qwt
from collections import namedtuple
import numpy as np
from collector import Curve

SIGNAL_TOP = 256
SIGNAL_BOT = -256

#Curve = namedtuple("Curve", "x y")

class Plot(Qwt.QwtPlot):
    colors = [Qt.Qt.black, Qt.Qt.red, Qt.Qt.darkBlue, Qt.Qt.darkRed,
              Qt.Qt.darkGray, Qt.Qt.darkRed, Qt.Qt.darkGreen]
    def __init__(self, rect, parent=None, zeroed=False, levels=[0],
                 points=False, lines=False,  ncurves=1):
        Qwt.QwtPlot.__init__(self, parent)
        self.setAxisScale(Qwt.QwtPlot.yLeft, SIGNAL_BOT, SIGNAL_TOP)

        self.curves = []
        if ncurves == len(levels):
            self.levels = levels
        else:
            self.levels = [0] * ncurves
            
        for i in range(ncurves):
            curve = Qwt.QwtPlotCurve()
            curve.attach(self)
            if lines or (not points and not lines):
                curve.setPen(QtGui.QPen())
            if points:
                shape = Qwt.QwtSymbol.Ellipse
                color = Plot.colors[i % len(Plot.colors)]
                size = Qt.QSize(3,3)
                symbol = Qwt.QwtSymbol(shape, color,
                                       QtGui.QPen(color), Qt.QSize(3,3))
                curve.setSymbol(symbol)
                if not lines:
                    curve.setStyle(Qwt.QwtPlotCurve.NoCurve)
            self.curves.append(curve)
        self.zoom = Qwt.QwtPlotZoomer(Qwt.QwtPlot.xBottom,
                                Qwt.QwtPlot.yLeft,            
                                self.canvas())
        self.zoom.setZoomBase(rect)
        self.zeroed = zeroed
        
    def myplot(self, data, n=0):
        if type(data) is np.ndarray and data.ndim == 2:
            _x = np.arange(data.shape[1])
            for i in range(data.shape[0]):
                self.curves[n + i].setData(_x, data[i]) 
        else:
            if type(data) is Curve:
                _x = data.x
                _y = data.y
            else:
                _x = np.arange(len(data))
                _y = data
            if not self.zeroed:
                self.curves[n].setData(_x, _y)
            else:
                level = self.levels[n]
                self.curves[n].setData(_x, _y - np.average(_y[250:1250] + level))
        self.replot()


class TempPlot(Qwt.QwtPlot):
    def __init__(self, parent=None):
        Qwt.QwtPlot.__init__(self, parent)
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
    colors = [Qt.Qt.red, Qt.QColor(100,100,100), Qt.Qt.black] * 2
                  
    def __init__(self, parent=None):
        Qwt.QwtPlot.__init__(self, parent)
        self.curve = Qwt.QwtPlotCurve('')
        self.curve.attach(self)
        #self.curve.setPen(QtGui.QPen())
        self.setAxisScale(Qwt.QwtPlot.yLeft, SIGNAL_BOT, SIGNAL_TOP)
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
