import cgi
import commands
import optparse
import os
import re
import shutil
import socket
import StringIO
import sys
import tempfile

from codereview.engine import RenderUnifiedTableRows
from codereview.patching import ParsePatchToLines
from diff import createHtmlDiff, getDiffLines, createHtmlDiffFromBaseAndDiff
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
    parsed_lines = ParsePatchToLines(diff)
    rows = RenderUnifiedTableRows(None, parsed_lines)
    w.write(kListTemplate % ('diff%d.html' % i,
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


def git_main(root):
  left, right, delimiter, files, err = get_git_revisions(sys.argv)
  if err:
    print >> sys.stderr, err
    sys.exit(1)

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
    print >> sys.stderr, output
    sys.exit(1)

  if not output.strip():
    return

  split = SplitGitDiff(splitOutput(output))
  showDiffInBrowser(root, left, split, create_gitshow)


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


def hg_main(root):
  parser = MercurialDiffOptionParser()
  params, args = parser.parse_args()
  if len(params.revision) > 2:
    print >> sys.stderr, 'abort: too many revisions specified'
    sys.exit(1)

  if len(params.revision) > 0:
    left_rev = params.revision[0]
  else:
    left_rev, _, error = GetHgParents()
    if error:
      raise Exception, error

  diffcmd = 'hg diff --nodates --git'
  for revision in params.revision:
    diffcmd += ' --rev=' + revision

  diffcmd += ' ' + ' '.join(args)
    
  rc, output = commands.getstatusoutput(diffcmd)
  if rc != 0:
    print >> sys.stderr, output
  split = SplitMercurialDiff(splitOutput(output))
  showDiffInBrowser(root, left_rev, split, create_hgcat)


def create_hgcat(root, left_rev, left_file):
  return 'hg cat -r %s "%s"' % (left_rev,
                                os.path.join(root, left_file))


def showDiffInBrowser(root, left_rev, split, catcmd_factory):
  req = Request()
  filenames = []
  diffs = []
  for i, (_, lines) in enumerate(split):
    left_file, right_file = ExtractFileNamesFromDiff(lines)
    diffs.append(lines)
    filenames.append(right_file)
    if left_file:
      catcmd = catcmd_factory(root, left_rev, left_file)
      rc, output = commands.getstatusoutput(catcmd)
      if rc != 0:
        raise Exception, 'Failed to run "%s": %s' % (catcmd, output)
      base_lines = splitOutput(output)
    else:
      base_lines = []
    
    html, err = createHtmlDiffFromBaseAndDiff(base_lines, lines)
    if err:
      raise Exception, 'Failed to create html diff: %s' % err

    page = req.additional_file.add()
    page.name = 'diff%d.html' % i
    page.data = html

  page = req.page.add()
  page.name = 'list.html'
  page.data = CreateFileListPageHtmlFromDiffs(diffs, filenames)

  s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
  s.connect('/tmp/sock')
  try:
    command.SendRequest(s, req)
    command.ReceiveResponse(s)
  finally:
    s.close()


def main():
  root, err = GetGitRootDirectory()
  if not err:
    return git_main(root)

  root, err = GetMercurialRootDirectory()
  if not err:
    return hg_main(root)
  print >> sys.stderr, 'There is no Git or Mercurial repository here!'
  sys.exit(1)


if __name__ == '__main__':
  main()
