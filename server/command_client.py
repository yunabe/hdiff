import socket
import struct
import sys

from command_pb2 import Request


def SendRequest(s, req):
  data = req.SerializeToString()
  print 'size =', len(data)
  size_data = struct.pack('<Q', # little endian & 64 bit unsigned.
                          len(data))
  print 'len(size_data) =', len(size_data)
  print 'size_data =', `size_data`
  s.sendall(size_data)
  s.sendall(data)


def ReceiveResponse(s):
  size_data = s.recv(8)
  size = struct.unpack('<Q', size_data)[0]
  print 'size =', size, type(size)
  data = s.recv(size)
  res = Response()
  res.ParseFromString(data)
  return res


def main():
  req = Request()
  page = req.page.add()
  page.name = 'hello'
  page.data = sys.stdin.read()

  s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
  s.connect('/tmp/sock')
  try:
    SendRequest(s, req)
    res = ReceiveResponse(s)
  finally:
    s.close()


if __name__ == '__main__':
  main()
