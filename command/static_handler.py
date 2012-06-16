import os

CONTENT_TYPE_MAP = {
  '.html': 'text/html',
  '.css': 'text/css',
  '.js': 'text/javascript',
  '.jpeg': 'image/jpeg',
  '.jpg': 'image/jpeg',
  '.png': 'image/png',
  '.gif': 'image/gif',
  }

class StaticHandler(object):
  def __init__(self, root):
    self.__root = root

  def __call__(self, path, start_response):
    filepath = os.path.join(self.__root, path)
    if not os.path.isfile(filepath):
      return self.__send404(start_response)
    _, ext = os.path.splitext(filepath)
    content_type = CONTENT_TYPE_MAP.get(ext, '')
    if not content_type:
      return self.__send404(start_response)
    start_response('200 OK',
                   [('Content-Type', content_type),
                    ('Cache-Control', 'private, max-age=31536000'),  # 1 year
                    ])
    return [file(filepath).read()]

  def __send404(self, start_response):
    start_response('404 Not Found', [])
    return ['404 Not Found']
