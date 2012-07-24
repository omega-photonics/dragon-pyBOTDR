import sys
from PyQt4 import QtGui
from mainwindow import MainWindow

def main():
    app = QtGui.QApplication(sys.argv)
    wnd = MainWindow()
    wnd.show()
    sys.exit(app.exec_())
    
if __name__ == "__main__":
    main()
