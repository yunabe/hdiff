import cgi
import commands
import json
import optparse
import os
import re
import socket
import threading
import StringIO
import sys
import urllib
import urlparse
from wsgiref.simple_server import make_server

from codereview.engine import RenderUnifiedTableRows
from codereview.patching import ParsePatchToLines
from diff import createHtmlDiff, getDiffLines, createHtmlDiffFromBaseAndDiff

STYLES_CSS_FILE = os.path.join(os.path.dirname(__file__),
                               '../static/styles.css')

kListPageTemplate = '''
<html>
<meta http-equiv="Content-Style-Type" content="text/css">
<style type="text/css">
%s
</style>
<body>
  <div style="display: table;margin-left:auto;margin-right:auto;">
    %s
  </div>
</body>
</html>
'''

kListTemplate = '''
<div class="code" style="margin-top: 1.3em; display: table;">
  <a href="%s" >%s</a>
  <table style="padding:5px;background-color:white" cellpadding="0" cellspaceing="0">%s</table>
</div>'''


class DiffData(object):
  def __init__(self, root, left_rev, split, catcmd_factory):
    self.root = root
    self.left_rev = left_rev
    self.split = split
    self.catcmd_factory = catcmd_factory


def splitOutput(output):
  output = output.rstrip('\n')
  return map(lambda s: s.rstrip('\r'), output.split('\n'))


def GetGitRootDirectory():
  rc, output = commands.getstatusoutput('git rev-parse --show-toplevel')
  if rc != 0:
    return None, output
  else:
    return output, None


def IsValidGitRevision(revision):
  rc, _ = commands.getstatusoutput(
    'git --no-pager show "%s" -- --name-only' % revision)
  return rc == 0


def MaybeParseGitRevision(s):
  delimiter_pattern = re.compile('\.\\.+')
  delimiters = delimiter_pattern.findall(s)
  revs = delimiter_pattern.split(s)

  if len(revs) != 1 and len(revs) != 2:
    return None
  if len(delimiters) > 1:
    return None

  left = None
  right = None
  delimiter = None
  if len(delimiters) == 1:
    delimiter = delimiters[0]

  for i, rev in enumerate(revs):
    if not rev:
      continue
    if not IsValidGitRevision(rev):
      return None
    if i == 0:
      left = rev
    else:
      right = rev

  return left, right, delimiter
  

def CreateFileListPageHtmlFromDiffs(diffs, filenames):
  w = StringIO.StringIO()
  for i, diff in enumerate(diffs):
    link_url = '?' + urllib.urlencode({'file': filenames[i]})
    parsed_lines = ParsePatchToLines(diff)
    rows = RenderUnifiedTableRows(None, parsed_lines)
    w.write(kListTemplate % (link_url,
                             cgi.escape(filenames[i]),
                             '\n'.join(rows)))
  return kListPageTemplate % (file(STYLES_CSS_FILE).read(), w.getvalue())


def GetMercurialRootDirectory():
  rc, output = commands.getstatusoutput('hg root')
  if rc != 0:
    return None, output
  else:
    return output, None


def RunMercurialDiff(args):
  rc, output = commands.getstatusoutput(' '.join(
      ['hg',
       'diff',
       ] + args))
  if rc != 0:
    return None, output
  else:
    return filter(lambda s: len(s) > 0,
                  map(lambda s: s.rstrip('\r'), output.split('\n'))), None


def SplitMercurialDiff(inputs):
  if len(inputs) == 0:
    return []
  if not inputs[0].startswith('diff '):
    return None, ('The first line of mercurial\'s diff must '
                  'start with \'diff \'.')

  results = []
  diffs = None
  for line in inputs:
    if line.startswith('diff '):
      diffs = []
      results.append((line, diffs))
    else:
      diffs.append(line)
  return results


def SplitGitDiff(inputs):
  return SplitMercurialDiff(inputs)


class MercurialDiffOptionParser(optparse.OptionParser):
  def __init__(self):
    optparse.OptionParser.__init__(self)
    self.add_option('-r', '--rev', default=[], dest='revision', action='append')


def get_git_revisions(argv):
  argv = argv[1:]
  has_separator = False
  files = []
  for i in xrange(len(argv)):
    if argv[i] == '--':
      files = argv[i+1:]
      argv = argv[:i]
      has_separator = True
      break

  if len(argv) == 0:
    return None, None, None, files, None

  left = None
  right = None
  for i in xrange(len(argv)):
    is_last = (i + 1 == len(argv))
    parsed = MaybeParseGitRevision(argv[i])
    if not parsed:
      if has_separator:
        return None, None, None, None, 'bad reivision: %s' % argv[i]
      else:
        return left, right, None, argv[i:] + files, None
    l, r, delim = parsed
    if delim == '...':
      return None, None, None, None, '<commit>...<commit> is not supported.'
    elif delim == '..':
      if not has_separator or is_last:
        return l, r, '..', argv[i + 1:] + files, None
      else:
        return None, None, None, None, 'Too many args before --'
    else:
      assert l
      assert not r
      assert not delim
      if not left:
        left = l
      else:
        right = l
        if not has_separator or is_last:
          return left, right, None, argv[i + 1:], None
        else:
          return None, None, None, None, 'Too many args before --'
  return left, right, None, files, None


def git_diff(root, argv):
  left, right, delimiter, files, err = get_git_revisions(argv)
  if err:
    return None, err

  if not left and right:
    left = 'HEAD'

  diffcmd = 'git --no-pager diff'

  if left or right:
    diffcmd += ' '
    if left:
      diffcmd += left
    if delimiter:
      diffcmd += delimiter
    else:
      diffcmd += ' '
    if right:
      diffcmd += right
  if files:
    diffcmd += ' -- ' + ' '.join(files)

  rc, output = commands.getstatusoutput(diffcmd)
  if rc != 0:
    return None, output

  if not output.strip():
    return None, 'No diff found.'

  split = SplitGitDiff(splitOutput(output))
  return DiffData(root, left, split, create_gitshow), None


def create_gitshow(root, left_rev, left_file):
  return 'git show %s:%s' % (left_rev if left_rev else '', left_file)


def GetHgParents():
  rc, output = commands.getstatusoutput('hg parents --template="{rev}\\n"')
  if rc != 0:
    return None, None, output
  parents = output.split()
  if len(parents) == 0:
    return None, None, 'No parent'
  elif len(parents) == 1:
    return int(parents[0]), None, None
  elif len(parents) == 2:
    return int(parents[0]), int(parents[1]), None
  else:
    return None, None, 'Too many parents :' + ', '.join(parents)


def ExtractFileNameFromFilenameLine(line):
  # Remove '--- ' or '+++ '
  line = line[4:]
  split = line.split('\t')
  if len(split) == 1:
    return line
  maybe_filename = '\t'.join(split[:-1])
  if ' ' in maybe_filename:
    return maybe_filename
  else:
    return maybe_filename + '\t'
  

def ExtractFileNamesFromDiff(lines):
  left_found = False
  left = None
  right = None
  for line in lines:
    if line.startswith('--- '):
      path = ExtractFileNameFromFilenameLine(line)
      left_found = True
      if path.startswith('a/'):
        left = path[len('a/'):]
      elif not path.startswith('/dev/null'):
        raise Exception, 'Invalid line: %s' % line
    elif line.startswith('+++ '):
      if not left_found:
        raise Exception, '--- line must come before +++ line'
      path = ExtractFileNameFromFilenameLine(line)
      if path.startswith('b/'):
        right = path[len('b/'):]
      elif not path.startswith('/dev/null'):
        raise Exception, 'Invalid line: %s' % line
      break
    else:
      if left_found:
        raise Exception, '+++ line must follow --- line'
  else:
    # break is not called.
    raise Exception, 'Either --- line or +++ line not found.'
  return left, right


def hg_diff(root, argv):
  parser = MercurialDiffOptionParser()
  params, args = parser.parse_args(argv[1:])
  if len(params.revision) > 2:
    return None, 'too many revisions specified'

  if len(params.revision) > 0:
    left_rev = params.revision[0]
  else:
    left_rev, _, error = GetHgParents()
    if error:
      return None, error

  diffcmd = 'hg diff --nodates --git'
  for revision in params.revision:
    diffcmd += ' --rev=' + revision

  diffcmd += ' ' + ' '.join(args)
    
  rc, output = commands.getstatusoutput(diffcmd)
  if rc != 0:
    return None, output
  split = SplitMercurialDiff(splitOutput(output))
  return DiffData(root, left_rev, split, create_hgcat), None


def create_hgcat(root, left_rev, left_file):
  return 'hg cat -r %s "%s"' % (left_rev,
                                os.path.join(root, left_file))


def createFileDiffHtml(diff_data, filename):
  for i, (_, lines) in enumerate(diff_data.split):
    left_file, right_file = ExtractFileNamesFromDiff(lines)
    if right_file != filename:
      continue

    if left_file:
      catcmd = diff_data.catcmd_factory(
        diff_data.root, diff_data.left_rev, left_file)
      rc, output = commands.getstatusoutput(catcmd)
      if rc != 0:
        raise Exception, 'Failed to run "%s": %s' % (catcmd, output)
      base_lines = splitOutput(output)
    else:
      base_lines = []
    
    html, err = createHtmlDiffFromBaseAndDiff(base_lines, lines)
    if err:
      return 'Failed to create html diff: %s' % err
    else:
      return html

    
def createFileListPageHtml(diff_data):
  filenames = []
  diffs = []
  for i, (_, lines) in enumerate(diff_data.split):
    _, right_file = ExtractFileNamesFromDiff(lines)
    diffs.append(lines)
    filenames.append(right_file)

  return CreateFileListPageHtmlFromDiffs(diffs, filenames)


class WebDiffHandler(object):
  def __init__(self, argv, mode, root):
    self.argv = argv
    self.mode = mode
    self.root = root

  def __call__(self, environ, start_response):
    if self.mode == 'git':
      diff_data, error = git_diff(self.root, self.argv)
    else:
      diff_data, error = hg_diff(self.root, self.argv)
    
    if error:
      start_response('200 OK', [('Content-Type', 'text/plain')])
      return [error]

    qs = urlparse.parse_qs(environ['QUERY_STRING'])
    filename = qs.get('file', [''])[0]
    start_response('200 OK', [('Content-Type', 'text/html')])
    if not filename:
      return [createFileListPageHtml(diff_data)]
    else:
      return [createFileDiffHtml(diff_data, filename)]


class ServerThread(threading.Thread):
  def __init__(self, server):
    threading.Thread.__init__(self)
    self.server = server

  def run(self):
    self.server.serve_forever()


def SendProxyRequest(command_port, addr):
  sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  sock.connect(('localhost', command_port))
  req = json.dumps({'host': addr,
                    'openurl': '/'})
  sock.send(req)
  try:
    sock.recv(4096)
  finally:
    sock.close()


def load_command_port():
  rcpath = os.path.join(os.path.expanduser('~'), '.htmlfwdrc')
  try:
    setting = file(rcpath, 'r').read()
  except Exception, e:
    print e
    return -1
  m = re.compile('command_port=(\d+)').search(setting)
  if m:
    return int(m.group(1))
  else:
    return -1


def main():
  command_port = load_command_port()
  if command_port == -1:
    print >> sys.stderr, 'Failed to load command_port from .htmlfwdrc'
    command_port = 9999

  mode = ''
  if not mode:
    root, err = GetGitRootDirectory()
    if not err:
      mode = 'git'
  if not mode:
    root, err = GetMercurialRootDirectory()
    if not err:
      mode = 'hg'

  if not mode:
    print >> sys.stderr, 'There is no Git or Mercurial repository here!'
    sys.exit(1)

  if mode == 'git':
    diff_data, error = git_diff(root, sys.argv)
  else:
    diff_data, error = hg_diff(root, sys.argv)

  if error:
    print >> sys.stderr, mode + ':', error
    sys.exit(1)

  server = make_server('', 0, WebDiffHandler(sys.argv, mode, root))
  port = server.socket.getsockname()[1]
  server_thread = ServerThread(server)
  server_thread.start()

  try:
    SendProxyRequest(command_port, 'localhost:%d' % port)
  finally:
    server.server_close()
    server_thread.join()

  showDiffInBrowser(diff_data.root, diff_data.left_rev,
                    diff_data.split, diff_data.catcmd_factory)


if __name__ == '__main__':
  main()
