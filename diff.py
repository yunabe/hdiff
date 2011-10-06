# Copyright 2011 Yu Watanabe.

import os
import sys
import commands

from codereview import engine
from codereview import patching

TEMPLATE_FILE = os.path.join(os.path.dirname(__file__), 'template/diff.html')
SCRIPT_JS_FILE = os.path.join(os.path.dirname(__file__), 'static/script.js')
STYLES_CSS_FILE = os.path.join(os.path.dirname(__file__), 'static/styles.css')

INLINE_SCRIPT = """
<script type="text/javascript">
<!--
%s
// -->
</script>""".strip()

INLINE_CSS = """
<style type="text/css">
%s
</style>""".strip()


def fillTemplate(template, params):
  for key in params:
    template = template.replace('{{%s}}' % key, params[key])
  return template


def filterNewLine(lines):
  result = []
  for line in lines:
    result.append(line.rstrip('\r\n'))
  return result

def getDiffLines(base, live):
  """Runs diff and returns lines of output.

  The result is equivalent to pathch.lines in rietvelt.
  """
  rc, output = commands.getstatusoutput('diff -u "%s" "%s"' % (base, live))
  if rc != 256:
    return None, output
  return filterNewLine(output.split('\n')), None


def createHtmlDiffFromBaseAndDiff(base_lines, chunks):
  column_width = 80
  # Makes context big to avoid collapsing unchanged parts.
  context = len(base_lines) + len(chunks)
  rows = list(engine.RenderDiffTableRows(None, base_lines, chunks, None,
                                         colwidth=column_width,
                                         context=context))
  if rows[-1] == None:
    # When engine._TableRowGenerator returns 'error'.
    del rows[-1]

  params = {
    'rows': '\n'.join(rows),
    'script.js': INLINE_SCRIPT % file(SCRIPT_JS_FILE).read(),
    'styles.css': INLINE_CSS % file(STYLES_CSS_FILE).read(),
  }

  template = file(TEMPLATE_FILE).read()
  return fillTemplate(template, params), None


def createHtmlDiff(base, live):
  diff_lines, err = getDiffLines(base, live)
  if err:
    return None, err
  chunks = patching.ParsePatchToChunks(diff_lines)
  old_lines = filterNewLine(file(base).readlines())
  new_lines_len = len(file(live).readlines())
  return createHtmlDiffFromBaseAndDiff(old_lines, chunks)


def main():
  if len(sys.argv) != 3:
    print 'Usage python diff.py file0 file1'
    sys.exit(1)

  html, err = createHtmlDiff(sys.argv[1], sys.argv[2])
  if err:
    print >> sys.stderr, err
    sys.exit(1)
  else:
    print html


if __name__ == '__main__':
  main()
