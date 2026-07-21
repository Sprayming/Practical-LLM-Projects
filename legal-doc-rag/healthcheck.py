import socket, sys
addr = ('localhost', 8501)
sys.exit(socket.socket().connect_ex(addr))
