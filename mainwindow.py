from PyQt4 import Qt, QtCore, QtGui, uic, Qwt5 as Qwt
from collector import Collector, Precollector
import pcienetclient as pcie
import  pciedevsettings
import plots
import usbdev
from usbworker import USBWorker
import time
import scanner
from datetime import datetime
import dump
from distances import Correlator, Approximator, Maximizer, MemoryUpdater
from averager import Averager
from distancecorrector import DistanceCorrector

STARTING_N_SP_DOT = 100

Base, Form = uic.loadUiType("window.ui")
class MainWindow(Base, Form):
    def __init__(self, parent=None):
        super(Base, self).__init__(parent)
        self.setupUi(self)
        
        self.otherWidget = uic.loadUi("other.ui")
        self.scannerSelect = uic.loadUi("scannerselect.ui")
        self.usbWidget = USBWidget()
        self.pcieWidget = DragonWidget()
        self.correctorWidget = CorrectorWidget()
        self.scannerWidget = ScannerWidget()
        self.scannerWidget.groupBox.setTitle("On chip scanner")
        self.DILTScannerWidget = ScannerWidget(name="DIL_Tscanner")
        self.DILTScannerWidget.groupBox.setTitle("DIL_T scanner")
        
        
        
        self.settings.addWidget(self.pcieWidget, 0, 0, 1, 1)
        self.settings.addWidget(self.usbWidget, 0, 1, 5, 1)
        self.scannerSelect.layout().insertWidget(1, self.scannerWidget)
        self.scannerSelect.layout().insertWidget(3, self.DILTScannerWidget)
        self.settings.addWidget(self.scannerSelect, 1, 0, 1, 1)
        self.settings.addWidget(self.correctorWidget, 3, 0, 1, 1)
        self.settings.addWidget(self.otherWidget, 4, 0, 1, 1)
        
        dragonrect = QtCore.QRectF(0, plots.SIGNAL_BOT, 8*6144,
                                   plots.SIGNAL_TOP - plots.SIGNAL_BOT)
        self.dragonplot = plots.Plot(dragonrect, self)
        self.temperatureplot = plots.TempPlot()
        self.spectraplot = plots.SlicePlot(self)
        self.distanceplot = plots.Plot(QtCore.QRectF(0, -500, 8*6144, 2*500), self, zeroed=True, points=True, levels=[0,0,1000,1000], ncurves=4)
        #for widget in [self.dragonplot, self.temperatureplot, self.spectraplot, self.distanceplot]:
        #    widget.setSizePolicy(QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Minimum)
        
        self.plots.addWidget(self.spectraplot, 0, 0, 1, 1)
        self.plots.addWidget(self.temperatureplot, 0, 1)
        self.plots.addWidget(self.dragonplot, 1, 1)
        self.plots.addWidget(self.distanceplot, 1, 0, 1, 1)

        self.usbWorker = USBWorker()  
        
        self.precollector = Precollector(self)
        self.collector = Collector(49140, self.scannerWidget.nsteps.value())
        self.memoryupdater = MemoryUpdater(self)
        self.correlator = Correlator(self)
        self.approximator = Approximator(self)
        self.maximizer = Maximizer(self)
        
        self.corraverager = Averager(self)
#        self.correlator.measured.connect(self.corraverager.appendDistances)
        self.appraverager = Averager(self)
#        self.approximator.measured.connect(self.appraverager.appendDistances)
        
        
        self.scanner = scanner.TimeScanner(n=self.scannerWidget.nsteps.value())
        self.DIL_Tscanner = scanner.TimeScanner(n=self.DILTScannerWidget.nsteps.value())
        #self.DIL_Tscanner.changeTemperature.connect(self.usbWorker.setDIL_T)
        
        self.updateUSBSettingsView()
        self.connectUSBSettingsWithInterface()
        self.connectScanerWidget()
        self.connectOtherWidget()
        #TODO: self.pushButton.clicked.connect(CLEAR_TEMP_PLOT)

        self.scanner.setTop(self.scannerWidget.top.value())
        self.scanner.setBottom(self.scannerWidget.bottom.value())
        self.scanner.setNdot(self.scannerWidget.nsteps.value())

        self.DIL_Tscanner.setTop(self.DILTScannerWidget.top.value())
        self.DIL_Tscanner.setBottom(self.DILTScannerWidget.bottom.value())
        self.DIL_Tscanner.setNdot(self.DILTScannerWidget.nsteps.value())
        
        
        self.corraverager.setNumber(self.scannerWidget.averageNumber.value())
        
        
        self.spectraplot.setChannel(self.otherWidget.plotChannel.value())
        
        self.corrector = DistanceCorrector(self)
        self.connectCorrectorWidget()
        self.corrector.setTargetDistance(self.correctorWidget.distance.value())
        self.corrector.setA(self.correctorWidget.A.value())
        self.corrector.setEnabled(self.correctorWidget.enabled.isChecked())
        self.corrector.setChannel(self.correctorWidget.channel.value())
        self.corrector.setReaction(self.usbWidget.spinBox_6.value())
        
        self.maximizer.measured.connect(self.corrector.appendDistances)        
        self.corrector.correct.connect(self.usbWidget.spinBox_6.setValue)
        self.usbWidget.spinBox_6.valueChanged.connect(self.corrector.setReaction)
        
        self.usbWorker.measured.connect(self.usbWidget.showResponse)
        self.usbWorker.measured.connect(self.collector.appendUSBResponse)
        self.usbWorker.statusChanged.connect(self.usbWidget.label_status.setText)
        
        
        self.temperatureplot.t0 = lambda v:self.temperatureplot.myplot(v, 0)
        self.temperatureplot.t1 = lambda v:self.temperatureplot.myplot(v, 1)
        
        self.collector.temperatureCurveChanged.connect(self.temperatureplot.t0)
        self.collector.temperatureCurve2Changed.connect(self.temperatureplot.t1)
                
        self.pcieClient = pcie.PCIENetWorker()
        self.pcieClient.setPCIESettings(self.pcieWidget.value())
        
        self.pcieClient.measured.connect(self.on_new_reflectogramm)
        self.collector.setReflectogrammLength(self.pcieWidget.framelength.value())
        
        
        self.pcieClient.start()
        #self.pcieClient.measured.connect(lambda x: self.dragonplot.myplot(x.data))
        self.isScanning = False
        self.is_scanning_cont = False
        self.is_scanning_pulsed = False
        self.enablePulseScanner(True)
        self.scannerSelect.pulse.toggled.connect(self.enablePulseScanner)        
        if self.scannerSelect.pulse.isChecked():
            self.maximizer.set_bottom(self.scannerWidget.bottom.value())
            self.maximizer.set_dt(self.scannerWidget.dt())
        else:
            self.maximizer.set_bottom(self.DILTScannerWidget.bottom.value())
            self.maximizer.set_dt(self.DILTScannerWidget.dt())

        self.pcieWidget.valueChanged.connect(self.pcieClient.setPCIESettings)

        #WARNING old code! revision may be needed
        #self.collector.reflectogrammChanged.connect(self.dragonplot.myplot)
        self.collector.spectraOnChipChanged.connect(self.spectraplot.setData)
        #self.collector.spectraChanged.connect(mypeakdetection)
        
        
        self.collector.sharedArrayChanged.connect(self.memoryupdater.updateShared)
        self.memoryupdater.updated.connect(self.correlator.update)
        self.memoryupdater.updated.connect(self.approximator.update)
        #self.scanner.dtChanged.connect(self.correlator.setDt)
        #self.scanner.dtChanged.connect(self.approximator.setDt)
        
        self.memoryupdater.updateShared((self.collector.shared, (2,) + self.collector.upScanMatrix.shape))
        #self.correlator.setDt(65535. / self.scannerWidget.nsteps.value())
        self.correlator.setDt(1.)
        self.correlator.measured.connect(self.distanceplot.myplot)

        #self.approximator.measured.connect(lambda t: self.distanceplot.myplot(t, n=1))
        
        self.scannerWidget.averageNumber.valueChanged.connect(self.corraverager.setNumber)
        self.scannerWidget.averageNumber.valueChanged.connect(self.appraverager.setNumber)
        
        self.distanceplot.d2 = lambda t: self.distanceplot.myplot(t, n=3)
        self.corraverager.measured.connect(self.distanceplot.d2)
        #self.appraverager.measured.connect(lambda t: self.distanceplot.myplot(t, n=3))

        
        self.pcieWidget.framelength.valueChanged.connect(self.collector.setReflectogrammLength)

        self.measuretimer = self.startTimer(1000)
        #self.FOL2timer = self.startTimer(self.usbWidget.FOL2_period.value())
        
        self.pcieWidget.framelength.valueChanged.connect(self.change_scan_time)
        self.pcieWidget.framecount.valueChanged.connect(self.change_scan_time)
        self.DILTScannerWidget.nsteps.valueChanged.connect(self.change_scan_time)
        
        self.change_scan_time()
        self.usbWorker.setDIL_T_scan_top(self.DILTScannerWidget.top.value())
        self.usbWorker.setDIL_T_scan_bottom(self.DILTScannerWidget.bottom.value())

        self.showMaximized()
        self.plotsOnly = False
        self.plotsFreezed = False
        
        self.DILTScannerWidget.nsteps.valueChanged.connect(self.collector.setSpectraLength)
        self.DIL_Tscanner.scanPositionChanged.connect(self.DILTScannerWidget.position.setNum)
        self.scannerWidget.nsteps.valueChanged.connect(self.collector.setSpectraLength)
        self.scanner.scanPositionChanged.connect(self.scannerWidget.position.setNum)
        self.scannerWidget.dtChanged.connect(self.maximizer.set_dt)
        self.scannerWidget.bottom.valueChanged.connect(
            self.maximizer.set_bottom)
        self.DILTScannerWidget.dtChanged.connect(self.maximizer.set_dt)
        self.DILTScannerWidget.bottom.valueChanged.connect(
            self.maximizer.set_bottom)
    
    def on_new_reflectogramm(self, pcie_dev_response):
        data = pcie_dev_response.data
        data = data[:pcie_dev_response.framelength]
        self.dragonplot.myplot(data)
        if self.isScanning:
            self.collector.appendDragonResponse(pcie_dev_response)
            submatrix_to_process = None
            if self.is_scanning_cont:
                self.collector.appendOnChipTemperature(
                    self.DIL_Tscanner.scan_position)
                self.DIL_Tscanner.scan()
                self.collector.setNextIndex(self.DIL_Tscanner.pos)
                if self.DIL_Tscanner.top_reached:
                    self.usbWorker.start_down_scan()
                elif self.DIL_Tscanner.bottom_reached:
                    self.usbWorker.start_up_scan()
                if (self.DIL_Tscanner.top_reached or
                    self.DIL_Tscanner.bottom_reached):
                    submatrix_to_process = self.DIL_Tscanner.lastsubmatrix
            if self.is_scanning_pulsed:
                self.collector.appendOnChipTemperature(
                    self.scanner.scan_position)
                self.scanner.scan()
                self.collector.setNextIndex(self.scanner.pos)
                self.usbWorker.setPFGI_TscanAmp(self.scanner.targetT)
                if (self.scanner.top_reached or
                    self.scanner.bottom_reached):
                    submatrix_to_process = self.scanner.lastsubmatrix
            if submatrix_to_process is not None:
                self.approximator.process_submatrix(submatrix_to_process)
                self.correlator.process_submatrix(submatrix_to_process)
                self.maximizer.process_submatrix(submatrix_to_process)
                

    def change_scan_time(self):
        framelength = self.pcieWidget.framelength.value()
        framecount = self.pcieWidget.framecount.value()
        ndot = self.DILTScannerWidget.nsteps.value()
        time = 2 * framelength * framecount * ndot / 133000000
        print "Estimated scan time is {} seconds".format(time)
        self.usbWorker.setDIL_T_scan_time(time)
    
        
    def enablePulseScanner(self, val):
        self.DILTScannerWidget.setEnabled(not val)
        self.scannerWidget.setEnabled(val)
        if val:
            print "scanning with pulse"
            if self.isScanning:
                self.start_DILT_scan(False)
            self.collector.setSpectraLength(self.scanner.ndot)
        else:
            print "scanning with cont"
            self.collector.setSpectraLength(self.DIL_Tscanner.ndot)
            if self.isScanning:
                self.startaccuratetimescan(False)

 
    def saveView(self):
        savepath = "/home/gleb/dumps/" + datetime.now().isoformat().replace(":", "-") + ".png"
        QtGui.QPixmap.grabWidget(self).save(savepath)
        
        
    def timerEvent(self, timer):
        if timer.timerId() == self.measuretimer:
            self.usbWorker.measure()
            
    def startaccuratetimescan(self, val):
        if val:
            self.usbWorker.setPFGI_TscanAmp(self.scanner.bot)
            self.conttimer = QtCore.QTimer()
            self.conttimer.setSingleShot(True)
            self.conttimer.setInterval(5000)
            self.conttimer.timeout.connect(self._cont)
            self.conttimer.start()

            print "wait 5 sec.."

        else:
            print "stopping pulsed scan"
            if not self.isScanning:
                self.conttimer.timeout.disconnect(self._cont)
            else:
                self.isScanning = False
                self.is_scanning_pulsed = False
                self.approximator.reset()

    def start_DILT_scan(self, val):
        if val:
            self.usbWorker.setDIL_T(self.DIL_Tscanner.bot)
            self.conttimer = QtCore.QTimer()
            self.conttimer.setSingleShot(True)
            self.conttimer.setInterval(5000)
            self.conttimer.timeout.connect(self._cont_DILT)
            self.conttimer.start()
            print "wait 5 sec.."

        else:
            print "stopping cont scan"
            if not self.isScanning:
                self.conttimer.timeout.disconnect(self._cont_DILT)
            else:
                self.isScanning = False
                self.is_scanning_cont = False
                self.approximator.reset()
            
    def mouseDoubleClickEvent(self, event):
        widgets = [self.usbWidget, self.pcieWidget, self.scannerSelect,
                   self.otherWidget, self.correctorWidget]
        if self.plotsOnly:
            for w in widgets:
                w.show()
            self.plotsOnly = False
        else:
            for w in widgets:
                w.hide()
            self.plotsOnly = True
    
    def keyPressEvent(self, event):
        print event.key()
        print "123"
        if event.key() == QtCore.Qt.Key_F1:
            print "F1 pressed"
            self.freezeGraphs()
        super(Base, self).keyPressEvent(event)
    
    def freezeGraphs(self):
        if self.plotsFreezed:
            self.collector.reflectogrammChanged.connect(self.dragonplot.myplot)
            self.collector.spectraOnChipChanged.connect(self.spectraplot.setData)
            self.collector.temperatureCurveChanged.connect(self.temperatureplot.t0)
            self.collector.temperatureCurve2Changed.connect(self.temperatureplot.t1)
            self.correlator.measured.connect(self.distanceplot.myplot)
            self.corraverager.measured.connect(self.distanceplot.d2)
        else:
            self.collector.reflectogrammChanged.disconnect(self.dragonplot.myplot)
            self.collector.spectraOnChipChanged.disconnect(self.spectraplot.setData)
            self.collector.temperatureCurveChanged.disconnect(self.temperatureplot.t0)
            self.collector.temperatureCurve2Changed.disconnect(self.temperatureplot.t1)
            self.correlator.measured.disconnect(self.distanceplot.myplot)
            self.corraverager.measured.disconnect(self.distanceplot.d2)
        
        self.plotsFreezed = not self.plotsFreezed
    
    def _cont(self):
        print "started"
        self.isScanning = True
        self.is_scanning_pulsed = True
        self.collector.clear()
        print "cleared"
        self.scanner.reset()
        print "reset"
        self.collector.setNextIndex(self.scanner.pos)
        #self.precollector.averaged.connect(self.collector.appendDragonResponse)
    
    def _cont_DILT(self):
        print "started"
        self.isScanning = True
        self.is_scanning_cont = True
        self.collector.clear()
        self.DIL_Tscanner.reset()
        self.collector.setNextIndex(self.DIL_Tscanner.pos)
        #self.precollector.averaged.connect(self.collector.appendDragonResponse)
        self.usbWorker.start_up_scan()
        
        
    def connectCorrectorWidget(self):
        self.correctorWidget.A.valueChanged.connect(self.corrector.setA)
        self.correctorWidget.channel.valueChanged.connect(self.corrector.setChannel)
        self.correctorWidget.enabled.toggled.connect(self.corrector.setEnabled)
        self.correctorWidget.distance.valueChanged.connect(self.corrector.setTargetDistance)
    
    def connectScanerWidget(self):
        self.scannerWidget.top.valueChanged.connect(self.scanner.setTop)
        self.scannerWidget.bottom.valueChanged.connect(self.scanner.setBottom)
        self.scannerWidget.nsteps.valueChanged.connect(self.scanner.setNdot)
        self.scannerWidget.accurateScan.clicked.connect(self.startaccuratetimescan)
        
        self.DILTScannerWidget.top.valueChanged.connect(self.DIL_Tscanner.setTop)
        self.DILTScannerWidget.bottom.valueChanged.connect(self.DIL_Tscanner.setBottom)
        self.DILTScannerWidget.nsteps.valueChanged.connect(self.DIL_Tscanner.setNdot)
        self.DILTScannerWidget.accurateScan.clicked.connect(self.start_DILT_scan)
    
        self.DILTScannerWidget.top.valueChanged.connect(self.usbWorker.setDIL_T_scan_top)
        self.DILTScannerWidget.bottom.valueChanged.connect(self.usbWorker.setDIL_T_scan_bottom)
    

    
    def connectOtherWidget(self):
        self.otherWidget.plotChannel.valueChanged.connect(self.spectraplot.setChannel)
        self.otherWidget.saveData.clicked.connect(self.collector.savelastscan)
        self.otherWidget.saveView.clicked.connect(self.saveView)
        self.otherWidget.flashSTM.clicked.connect(self.usbWorker.flash)
        
    def connectUSBSettingsWithInterface(self):
        widget = self.usbWidget
        widget.spinBox.valueChanged.connect(self.usbWorker.setPFGI_amplitude)
        widget.spinBox_2.valueChanged.connect(self.usbWorker.setPFGI_pedestal)
        widget.checkBox.toggled.connect(self.usbWorker.setPC4)
        widget.checkBox_2.toggled.connect(self.usbWorker.setPC5)
        widget.spinBox_5.valueChanged.connect(self.usbWorker.setDIL_I)
        widget.spinBox_6.valueChanged.connect(self.usbWorker.setDIL_T)
        widget.spinBox_7.valueChanged.connect(self.usbWorker.setPFGI_Tset)
        widget.spinBox_8.valueChanged.connect(self.usbWorker.setPFGI_TscanAmp)
        widget.spinBox_3.valueChanged.connect(self.usbWorker.setPROM_hv)
        widget.spinBox_4.valueChanged.connect(self.usbWorker.setPROM_shift)
        widget.spinBox_9.valueChanged.connect(self.usbWorker.setFOL1_I)
        widget.spinBox_10.valueChanged.connect(self.usbWorker.setFOL1_T)
        widget.spinBox_11.valueChanged.connect(self.usbWorker.setFOL2_I)
        widget.spinBox_12.valueChanged.connect(self.usbWorker.setFOL2_T)
        widget.spinBox_a1.valueChanged.connect(self.usbWorker.setA1)
        widget.spinBox_a2.valueChanged.connect(self.usbWorker.setA2)
        widget.spinBox_a3.valueChanged.connect(self.usbWorker.setA3)
        widget.spinBox_b1.valueChanged.connect(self.usbWorker.setB1)
        widget.spinBox_b2.valueChanged.connect(self.usbWorker.setB2)
        widget.spinBox_b3.valueChanged.connect(self.usbWorker.setB3)
        widget.spinBox_c1.valueChanged.connect(self.usbWorker.setC1)
        widget.spinBox_c2.valueChanged.connect(self.usbWorker.setC2)
        widget.spinBox_c3.valueChanged.connect(self.usbWorker.setC3)
        widget.spinBox_t1.valueChanged.connect(self.usbWorker.setT1set)
        widget.spinBox_t2.valueChanged.connect(self.usbWorker.setT2set)
        widget.spinBox_t3.valueChanged.connect(self.usbWorker.setT3set)
        widget.radioButton.toggled.connect(self.usbWorker.setPID)
        widget.spinBox_TScanPeriod.valueChanged.connect(self.usbWorker.setPFGI_TscanPeriod)
        widget.checkBox_3.toggled.connect(self.usbWorker.setDiode)

    def updateUSBSettingsView(self):
        widget = self.usbWidget
        file = self.usbWorker.usbSettings.file
        widget.spinBox_a1.setValue(file.value("A1").toInt()[0])
        widget.spinBox_a2.setValue(file.value("A2").toInt()[0])
        widget.spinBox_a3.setValue(file.value("A3").toInt()[0])
        widget.spinBox_b1.setValue(file.value("B1").toInt()[0])
        widget.spinBox_b2.setValue(file.value("B2").toInt()[0])
        widget.spinBox_b3.setValue(file.value("B3").toInt()[0])
        widget.spinBox_c1.setValue(file.value("C1").toInt()[0])
        widget.spinBox_c2.setValue(file.value("C2").toInt()[0])
        widget.spinBox_c3.setValue(file.value("C3").toInt()[0])
        widget.spinBox_t1.setValue(file.value("T1set").toInt()[0])
        widget.spinBox_t2.setValue(file.value("T2set").toInt()[0])
        widget.spinBox_t3.setValue(file.value("T3set").toInt()[0])
        widget.checkBox.setChecked(file.value("PC4").toBool())
        widget.checkBox_2.setChecked(file.value("PC5").toBool())
        widget.spinBox.setValue(file.value("PFGI_amplitude").toInt()[0])
        widget.spinBox_2.setValue(file.value("PFGI_pedestal").toInt()[0])
        widget.spinBox_3.setValue(file.value("PROM_hv").toInt()[0])
        widget.spinBox_4.setValue(file.value("PROM_shift").toInt()[0])
        widget.spinBox_5.setValue(file.value("DIL_I").toInt()[0])
        widget.spinBox_6.setValue(file.value("DIL_T").toInt()[0])
        widget.spinBox_7.setValue(file.value("PFGI_Tset").toInt()[0])
        widget.spinBox_8.setValue(file.value("PFGI_TscanAmp").toInt()[0])
        widget.spinBox_TScanPeriod.setValue(
            file.value("PFGI_TscanPeriod").toInt()[0])
        widget.spinBox_9.setValue(file.value("FOL1_I").toInt()[0])
        widget.spinBox_10.setValue(file.value("FOL1_T").toInt()[0])
        widget.spinBox_11.setValue(file.value("FOL2_I").toInt()[0])
        widget.spinBox_12.setValue(file.value("FOL2_T").toInt()[0])
        
    def start_FOL2_oscilation(self):
        self.killTimer(self.FOL2timer)
        self.FOL2timer = self.startTimer(self.usbWidget.FOL2_period.value())

BaseUSB, FormUSB = uic.loadUiType("botdrmainwindow.ui")
class USBWidget(BaseUSB, FormUSB):
    valuesChanged = QtCore.pyqtSignal(usbdev.USBSettings)
    def __init__(self, parent=None):
        super(BaseUSB, self).__init__(parent)
        self.setupUi(self)
        
    def showResponse(self, response):
        self.label_t1.setText(str(response.T1))
        self.label_t2.setText(str(response.T2))
        self.label_t3.setText(str(response.T3))
        self.label_r1.setText(str(response.R1))
        self.label_r2.setText(str(response.R2))
        self.label_r3.setText(str(response.R3))
        self.label_f1.setText(str(response.F1))
        self.label_f2.setText(str(response.F2))
        self.label_f3.setText(str(response.F3))
        self.label_19.setText(str(response.temp_C))

        
import pickle
DragomBase, DragonForm = uic.loadUiType("dragon.ui")
class DragonWidget(DragomBase, DragonForm):
    valueChanged = QtCore.pyqtSignal(pciedevsettings.PCIESettings)
    def __init__(self, parent=None):
        super(DragomBase, self).__init__(parent)
        self.setupUi(self)
        try:
            self._value = pickle.load(open("pciesettings.ini", "r"))
        except IOError:
            self._value = self.value()
        else:
            for name in ["ch1amp", "ch1shift", "ch1count", "ch2amp",
                         "ch2count", "ch2shift", "framelength", "framecount"]:
                self.__dict__[name].setValue(self._value.__dict__[name])
            
        for widget in [ self.ch1amp, self.ch1shift, self.ch1count,
                        self.ch2amp, self.ch2count, self.ch2shift,
                        self.framelength, self.framecount]:
            widget.valueChanged.connect(self.rereadValue)
        self.framelength.editingFinished.connect(self.selfCorrect)
    
    def selfCorrect(self):
        val = self.framelength.value()
        if val % 6 != 0:
            self.framelength.setValue(val // 6 * 6)
        
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
            pickle.dump(val, open("pciesettings.ini", "w"))
            self._value = val
            self.valueChanged.emit(val)

            
ScannerBase, ScannerForm = uic.loadUiType("timescanner.ui")
class ScannerWidget(ScannerBase, ScannerForm):
    dtChanged = QtCore.pyqtSignal(float)
    def __init__(self, parent=None, name="timescaner"):
        super(ScannerBase, self).__init__(parent)
        self.setupUi(self)
        
        self.valueable = ["top", "bottom", "averageNumber", "nsteps"]
        self.checkable = []
        self.textabel = ["position"]
        self.name = name
        
        try:
            f = open("%s.ini" % self.name, "r")
        except IOError:
            pass
        else:
            state = pickle.load(f)
            self.setstate(state)
            f.close()
        
        for widget in [self.__dict__[x] for x in self.valueable]:
            widget.valueChanged.connect(self.savestate)
        for widget in [self.__dict__[x] for x in self.checkable]:
            widget.stateChanged.connect(self.savestate)
        
        dt_emitter = lambda x: self.dtChanged.emit(self.dt())
        for widget in [self.top, self.bottom, self.nsteps]:
            widget.valueChanged.connect(dt_emitter)
    
    def dt(self):
        return (float(self.top.value() - self.bottom.value()) /
              (self.nsteps.value() + 1))

    def setstate(self, state):
        for key in self.valueable:
            self.__dict__[key].setValue(state[key])
        for key in self.checkable:
            self.__dict__[key].setChecked(state[key])
    
    def getstate(self):
        return dict(zip(self.valueable, [self.__dict__[key].value() for key in self.valueable]))
                
    def savestate(self):
        state = self.getstate()
        with open("%s.ini" % self.name, "w") as f:
            pickle.dump(state, f)        

       


CorrectorBase, CorrectorForm = uic.loadUiType("distancecorrector.ui")
class CorrectorWidget(CorrectorBase, CorrectorForm):
    def __init__(self, parent=None):
        super(CorrectorBase, self).__init__(parent)
        self.setupUi(self)
        
        self.valueable = ["channel", "distance", "A"]
        self.checkable = ["enabled"]
        
        try:
            f = open("distancecorrector.ini", "r")
        except IOError:
            pass
        else:
            state = pickle.load(f)
            self.setstate(state)
            f.close()
        
        for widget in [self.__dict__[x] for x in self.valueable]:
            widget.valueChanged.connect(self.savestate)
        for widget in [self.__dict__[x] for x in self.checkable]:
            widget.stateChanged.connect(self.savestate)
            
    
    def setstate(self, state):
        for key in self.valueable:
            self.__dict__[key].setValue(state[key])
        for key in self.checkable:
            self.__dict__[key].setChecked(state[key])
    
    def getstate(self):
        return {"enabled": self.enabled.isChecked(),
                "channel": self.channel.value(),
                "distance": self.distance.value(),
                "A": self.A.value()
                }
                
    def savestate(self):
        state = self.getstate()
        with open("distancecorrector.ini", "w") as f:
            pickle.dump(state, f)
