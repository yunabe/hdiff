import struct

from command_pb2 import Response


def __SendProto(s, pb):
  data = pb.SerializeToString()
  print 'size =', len(data)
  size_data = struct.pack('<Q', # little endian & 64 bit unsigned.
                          len(data))
  print 'len(size_data) =', len(size_data)
  print 'size_data =', `size_data`
  s.sendall(size_data)
  s.sendall(data)


def __ReceiveProto(s, pb):
  size_data = s.recv(8)
  size = struct.unpack('<Q', size_data)[0]
  print 'size =', size, type(size)
  data = s.recv(size)
  pb.ParseFromString(data)


def SendRequest(s, req):
  __SendProto(s, req)


def ReceiveResponse(s):
  response = Response()
  __ReceiveProto(s, response)
  return response
