# Copyright 2011 Yu Watanabe.

import os
import sys
import commands

from codereview import engine
from codereview import patching

TEMPLATE_FILE = os.path.join(os.path.dirname(__file__),
                             '../template/diff.html')
SCRIPT_JS_FILE = os.path.join(os.path.dirname(__file__),
                              '../static/script.js')
STYLES_CSS_FILE = os.path.join(os.path.dirname(__file__),
                               '../static/styles.css')

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


def createHtmlDiffFromBaseAndDiff(base_lines, diff_lines):
  chunks = patching.ParsePatchToChunks(diff_lines)
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
