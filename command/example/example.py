import socket
import threading
from wsgiref.simple_server import make_server

from server.command_pb2 import Request
from server.command_pb2 import Response
from server import command


def SendProxyRequest(addr):
  req = Request()
  s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
  s.connect('/tmp/sock')
  req.mode = Request.PROXY
  req.proxy_addr = addr
  try:
    command.SendRequest(s, req)
    command.ReceiveResponse(s)
  finally:
    s.close()


def say_hello(environ, start_response):
  start_response('200 OK', [('Content-Type', 'text/plain')])
  return ['Hello World\n']

      
class ServerThread(threading.Thread):
  def __init__(self, server):
    threading.Thread.__init__(self)
    self.server = server

  def run(self):
    self.server.serve_forever()


def main():
  server = make_server('', 0, say_hello)
  port = server.socket.getsockname()[1]
  server_thread = ServerThread(server)
  server_thread.start()

  try:
    SendProxyRequest('localhost:%d' % port)
  finally:
    server.server_close()
    server_thread.join()


if __name__ == '__main__':
  main()
