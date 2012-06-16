import cgi
import commands
import json
import optparse
import os
import re
import socket
import threading
import StringIO
import subprocess
import sys
import urllib
import urlparse
from wsgiref.simple_server import make_server

from codereview.engine import RenderUnifiedTableRows
from codereview.patching import ParsePatchToLines
from command.diff import createHtmlDiffFromBaseAndDiff
from command.static_handler import StaticHandler

APPID = 'xv3fo8'
STATIC_DIR_PATH = os.path.join(os.path.dirname(__file__), '../static')

kListPageTemplate = '''
<html>
<meta http-equiv="Content-Style-Type" content="text/css">
<link href="/shared/{appid}/styles.css" rel="stylesheet">
<body>
  <div style="display: table;margin-left:auto;margin-right:auto;">
    %s
  </div>
</body>
</html>
'''.replace('{appid}', APPID)

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


def getstatusoutput_with_args(args):
  proc = subprocess.Popen(
    args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
  out, _ = proc.communicate()
  return proc.wait(), out


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
  delimiter_pattern = re.compile('\\.\\.+')
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
  return kListPageTemplate % w.getvalue()


def GetMercurialRootDirectory():
  rc, output = commands.getstatusoutput('hg root')
  if rc != 0:
    return None, output
  else:
    return output, None


def SplitMercurialDiff(mode, inputs):
  if len(inputs) == 0:
    return []
  if not (mode == 'diff' or inputs[0].startswith('diff ')):
    # 'diff' does not output 'diff xxx' line when it compares files.
    return None, ('The first line of mercurial\'s diff must '
                  'start with \'diff \'.')

  results = []
  diffs = None
  for line in inputs:
    if line.startswith('diff '):
      diffs = []
      results.append((line, diffs))
    elif diffs is None:
      # diff does not output "diff ..." line
      diffs = []
      results.append(('unused?', diffs))
      diffs.append(line)
    else:
      diffs.append(line)
  return results


def SplitGitDiff(inputs):
  return SplitMercurialDiff('git', inputs)


class MercurialDiffOptionParser(optparse.OptionParser):
  def __init__(self):
    optparse.OptionParser.__init__(self)
    self.add_option('-r', '--rev', default=[], dest='revision', action='append')


def get_git_revisions(argv):
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

  diffcmds = ['git', '--no-pager', 'diff']

  if left or right:
    if delimiter:
      diffcmds.append(''.join([left if left else '',
                               delimiter,
                               right if right else '',]))
    else:
      if left:
        diffcmds.append(left)
      if right:
        diffcmds.append(right)

  if files:
    diffcmds.append('--')
    diffcmds.extend(files)

  # TODO: quote shell args
  rc, output = getstatusoutput_with_args(diffcmds)
  if rc != 0:
    return None, output

  if not output.strip():
    return None, 'No diff found.'

  split = SplitGitDiff(splitOutput(output))
  return DiffData(root, left, split, create_gitshow), None


def create_gitshow(root, left_rev, left_file):
  return ['git', 'show', '%s:%s' % (left_rev if left_rev else '', left_file)]


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
  # Remove time stamp from output of "diff".
  return '\t'.join(split[:-1])
  

def ExtractFileNamesFromDiff(mode, lines):
  left_found = False
  left = None
  right = None
  for line in lines:
    if line.startswith('--- '):
      path = ExtractFileNameFromFilenameLine(line)
      left_found = True
      if mode == 'diff':
        left = path
      elif path.startswith('a/'):
        left = path[len('a/'):]
      elif not path.startswith('/dev/null'):
        raise Exception, 'Invalid line: %s' % line
    elif line.startswith('+++ '):
      if not left_found:
        raise Exception, '--- line must come before +++ line'
      path = ExtractFileNameFromFilenameLine(line)
      if mode == 'diff':
        right = path
      elif path.startswith('b/'):
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
  params, args = parser.parse_args(argv)
  if len(params.revision) > 2:
    return None, 'too many revisions specified'

  if len(params.revision) > 0:
    left_rev = params.revision[0]
  else:
    left_rev, _, error = GetHgParents()
    if error:
      return None, error

  diffcmds = ['hg', 'diff', '--nodates', '--git']
  for revision in params.revision:
    diffcmds.append('--rev=' + revision)

  diffcmds.extend(args)

  # TODO: quote shell args
  rc, output = getstatusoutput_with_args(diffcmds)
  if rc != 0:
    return None, output
  split = SplitMercurialDiff('hg', splitOutput(output))
  return DiffData(root, left_rev, split, create_hgcat), None


def create_hgcat(root, left_rev, left_file):
  return ['hg', 'cat', '-r', left_rev, os.path.join(root, left_file)]


def diff_diff(root, argv):
  diffcmd = 'diff -u ' + ' '.join(argv)
  rc, output = commands.getstatusoutput(diffcmd)
  if rc != 256:  # TODO: Why 256?
    return None, output
  split = SplitMercurialDiff('diff', splitOutput(output))
  return DiffData(root, 'dummy', split, create_cat), None


def create_cat(root, left_rev, left_file):
  print 'left_file', `left_file`
  return 'cat "%s"' % os.path.join(root, left_file)


def createFileDiffHtml(mode, diff_data, filename):
  for i, (_, lines) in enumerate(diff_data.split):
    left_file, right_file = ExtractFileNamesFromDiff(mode, lines)
    if right_file != filename:
      continue

    if left_file:
      catcmd = diff_data.catcmd_factory(
        diff_data.root, diff_data.left_rev, left_file)
      rc, output = getstatusoutput_with_args(catcmd)
      if rc != 0:
        raise Exception, 'Failed to run "%s": %s' % (catcmd, output)
      base_lines = splitOutput(output)
    else:
      base_lines = []
    
    html, err = createHtmlDiffFromBaseAndDiff(APPID, base_lines, lines)
    if err:
      return 'Failed to create html diff: %s' % err
    else:
      return html

    
def createFileListPageHtml(mode, diff_data):
  filenames = []
  diffs = []
  for i, (_, lines) in enumerate(diff_data.split):
    _, right_file = ExtractFileNamesFromDiff(mode, lines)
    diffs.append(lines)
    filenames.append(right_file)

  return CreateFileListPageHtmlFromDiffs(diffs, filenames)


class WebDiffHandler(object):
  def __init__(self, argv, mode, root):
    self.argv = argv
    self.mode = mode
    self.root = root
    self.shared_handler = StaticHandler(STATIC_DIR_PATH)

  def __call__(self, environ, start_response):
    if environ['PATH_INFO'].startswith('/shared/'):
      return self.shared_handler(environ['PATH_INFO'][len('/shared/'):],
                                 start_response)
    if self.mode == 'git':
      diff_data, error = git_diff(self.root, self.argv)
    elif self.mode == 'hg':
      diff_data, error = hg_diff(self.root, self.argv)
    else:
      # mode == 'diff'
      diff_data, error = diff_diff(self.root, self.argv)
    
    if error:
      start_response('200 OK', [('Content-Type', 'text/plain')])
      return [error]

    qs = urlparse.parse_qs(environ['QUERY_STRING'])
    filename = qs.get('file', [''])[0]
    start_response('200 OK', [('Content-Type', 'text/html')])
    if not filename:
      return [createFileListPageHtml(self.mode, diff_data)]
    else:
      return [createFileDiffHtml(self.mode, diff_data, filename)]


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
                    'openurl': '/',
                    'clientid': APPID})
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

  if len(sys.argv) < 2:
    print >> sys.stderr, 'hg diff|git|hg'
    sys.exit(1)
  mode = sys.argv[1]
  if mode not in ('diff', 'git', 'hg'):
    print >> sys.stderr, 'Unknown command:', mode
    print >> sys.stderr, 'hg diff|git|hg'
    sys.exit(1)

  if mode == 'diff':
    root = os.getcwd()
  elif mode == 'git':
    root, err = GetGitRootDirectory()
    if err:
      print >> sys.stderr, 'Not a git repository'
      sys.exit(1)
  elif mode == 'hg':
    root, err = GetMercurialRootDirectory()
    if err:
      print >> sys.stderr, 'Not a mercurial repository'
      sys.exit(1)

  server = make_server('', 0, WebDiffHandler(sys.argv[2:], mode, root))
  port = server.socket.getsockname()[1]
  server_thread = ServerThread(server)
  server_thread.start()

  try:
    SendProxyRequest(command_port, 'localhost:%d' % port)
  finally:
    server.server_close()
    server_thread.join()


if __name__ == '__main__':
  main()
