import socket
import time

class MySocket(socket.socket):
    def recvall(conn, nbytes, timeout=0.3):
        start = time.time()
        pieces = []
        recived = 0
        result = ''
        timepast = 0
        while timepast < timeout:
            bytes = conn.recv(nbytes - recived)
            pieces.append(bytes)
            recived += len(bytes)
            timepast = time.time() - start
            if recived == nbytes:
                return "".join(pieces)
        return None
