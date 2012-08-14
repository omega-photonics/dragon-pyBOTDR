import socket
import threading
import struct

HOST = ''
PORT = 13131

class Sender(threading.Thread):
    def __init__(self, parent=None):
        threading.Thread.__init__(self)
        self.socket  = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((HOST, PORT))
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        self.dataready = False
        self.exiting = False 
        self.start()

    def send_data(self, array, comment):
        self.condition.acquire()
        self.dataready = True
        self.data = array, comment
        self.condition.notify()
        self.condition.release()
    
    def stop(self):
        self.condition.acquire()
        self.exiting = True
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(('localhost', PORT))
        s.close()
        self.condition.notify()
        self.condition.release()

    def run(self):
        while not self.exiting:
            self.socket.listen(1)
            conn, addr = self.socket.accept()
            print 'Secondary client connected'
            while not self.exiting:
                self.condition.acquire()
                while not self.dataready and not self.exiting:
                    self.condition.wait()
                if self.exiting:
                    self.condition.release()
                    break
                array, comment = self.data
                try:
                    conn.sendall(struct.pack('I', comment))
                    conn.sendall(struct.pack('I', array.shape[-1]))
                    data = array.tostring()
                    print len(data), 'for', array.shape
                    conn.sendall(data)
                except:
                    print 'Exception on send occured'
                    self.dataready = False
                    self.condition.release()
                    break
                self.dataready = False
                self.condition.release()
            print 'Secondary client disconnected'
            conn.close()
