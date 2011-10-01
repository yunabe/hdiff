import cgi
import commands
import os
import shutil
import socket
import StringIO
import sys
import tempfile

from codereview.engine import RenderUnifiedTableRows
from codereview.patching import ParsePatchToLines
from diff import createHtmlDiff, getDiffLines
from server.command_pb2 import Request
from server.command_pb2 import Response
from server import command

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


def GitDiffNameOnly(extra_args):
  rc, output = commands.getstatusoutput(' '.join(
      ['git',
       '--no-pager',
       'diff',
       '--name-only',
       '--no-ext-diff',
       ] + extra_args))
  if rc != 0:
    return None, output
  else:
    return filter(lambda s: len(s) > 0,
                  map(lambda s: s.strip(), output.split('\n'))), None


def GetGitRootDirectory():
  rc, output = commands.getstatusoutput('git rev-parse --show-toplevel')
  if rc != 0:
    return None, output
  else:
    return output, None


def StoreBaseFiles(tmpdir, files):
  for i, filename in enumerate(files):
    tmpfile = os.path.join(tmpdir, 'base%d' % i)
    os.environ['WEBDIFF_TMPFILE'] = tmpfile
    rc, output = commands.getstatusoutput('git difftool "%s"' % filename)
    if rc != 0:
      print >> sys.stderr, output
      return False
  return True


def CreateFileListPageHtml(tmpdir, files):
  w = StringIO.StringIO()
  for i, filename in enumerate(files):
    lines, _ = getDiffLines(os.path.join(tmpdir, 'base%d' % i), filename)
    parsed_lines = ParsePatchToLines(lines)
    rows = RenderUnifiedTableRows(None, parsed_lines)
    w.write(kListTemplate % ('diff%d.html' % i,
                             cgi.escape(filename),
                             '\n'.join(rows)))
  return kListPageTemplate % (file(STYLES_CSS_FILE).read(), w.getvalue())


def ConstructRequest(tmpdir, files):
  req = Request()
  if len(files) > 1:
    page = req.page.add()
    page.name = 'list.html'
    page.data = CreateFileListPageHtml(tmpdir, files)

  for i, filename in enumerate(files):
    html, err = createHtmlDiff(os.path.join(tmpdir, 'base%d' % i), filename)
    if err:
      print >> sys.stderr, err
      continue

    if len(files) == 1:
      page = req.page.add()
    else:
      page = req.additional_file.add()
    page.name = 'diff%d.html' % i
    page.data = html
  return req


def main():
  root, err = GetGitRootDirectory()
  if err:
    print >> sys.stderr, err
    sys.exit(1)

  files, err = GitDiffNameOnly(sys.argv[1:])
  if err:
    print >> sys.stderr, "Error:", err
    return
  # Names of files returned by git diff are based on root dir.
  os.chdir(root)
  if len(files) == 0:
    return

  if len(files) > 1:
    files.reverse()
    print 'Sorry, multiple diff is not suported.'
    print 'Shwoing diff of %s' % files[0]

  try:
    tmpdir = tempfile.mkdtemp()
    StoreBaseFiles(tmpdir, files)
    req = ConstructRequest(tmpdir, files)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect('/tmp/sock')
    try:
      command.SendRequest(s, req)
      command.ReceiveResponse(s)
    finally:
      s.close()
  finally:
    try:
      shutil.rmtree(tmpdir) # delete directory
    except OSError, e:
      if e.errno != 2:
        raise


if __name__ == '__main__':
  main()
