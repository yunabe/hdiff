import tempfile
import unittest
import shutil
import os
import commands

import webdiff


class Mercurial(unittest.TestCase):
  def setUp(self):
    commands.getstatusoutput('hg update -C tip')
    commands.getstatusoutput('rm -rf `hg status -u | sed "s/\? //"`')

  def tearDown(self):
    pass

  def testSplit(self):
    inputs = [ 'diff -r 840f9bb917ba COPYING',
               '--- a/COPYING   Thu Sep 22 21:00:54 2011 +0300',
               '+++ b/COPYING   Sun Oct 02 12:24:05 2011 +0900',
               '@@ -200,3 +200,4 @@',
               ' foo',
               '+bar',
               'diff -r 840f9bb917ba TODO',
               '--- a/TODO      Thu Sep 22 21:00:54 2011 +0300',
               '+++ b/TODO      Sun Oct 02 12:24:05 2011 +0900',
               '@@ -67,3 +67,4 @@',
               ' hoge',
               '+piyo',
               '+hogehoge',
               ]
    results = webdiff.SplitMercurialDiff(inputs)
    self.assertEqual(2, len(results))
    self.assertEqual('diff -r 840f9bb917ba COPYING', results[0][0])
    self.assertEqual(5, len(results[0][1]))
    self.assertEqual('diff -r 840f9bb917ba TODO', results[1][0])
    self.assertEqual(6, len(results[1][1]))

  def testParser(self):
    parser = webdiff.MercurialDiffOptionParser()
    args = ['-r', '1', '-r', '2']
    options, remains = parser.parse_args(args)
    self.assertEqual(['1', '2'], options.revision)

    parser = webdiff.MercurialDiffOptionParser()
    args = ['sample.txt', '-r', '1', '--rev', '2']
    options, remains = parser.parse_args(args)
    self.assertEqual(['1', '2'], options.revision)
    self.assertEqual(['sample.txt'], remains)

  def testGetHgParents(self):
    self.assertEqual((6, None, None), webdiff.GetHgParents())
    commands.getstatusoutput('hg update -r 5')
    commands.getstatusoutput('hg merge')
    self.assertEqual((5, 6, None), webdiff.GetHgParents())


class TempDir(object):
  def __init__(self):
    self.path = None

  def __enter__(self):
    self.path = tempfile.mkdtemp()
    return self

  def __exit__(self, type, value, traceback):
    if not self.path:
      return
    try:
      shutil.rmtree(self.path)
    except OSError, e:
      if e.errorno != 2:
        raise
    self.path = None


class TempRepository(object):
  def __init__(self):
    self.nodes = []

  def setUp(self):
    rc, output = commands.getstatusoutput('hg init rep')
    if rc != 0:
      raise Exception, output
    os.chdir('rep')
    self.executeCommands(
      ['echo Please read. > README',
       'hg add README',
       'hg commit -m "Added README."', # 0
       'echo Additional comments. >> README',
       'hg add README',
       'hg commit -m "Added addtional comments to README."', # 1
       'echo foo > bar',
       'hg add bar',
       'hg commit -m "Added bar"', # 2
       'hg update -r 1',
       'echo hoge > piyo',
       'hg add piyo',
       'hg commit -m "Added piyo"', # 3
       'hg merge',
       'hg commit -m "Merged."', # 4
       'echo foofoo >> piyo',
       'hg commit -m "Added foofoo to piyo."', # 5
       'hg update -r 4',
       'echo hogehoge >> bar',
       'hg commit -m "Added hogehoge to bar."', # 6
       ])

  def executeCommands(self, cmds):
    for cmd in cmds:
      rc, output = commands.getstatusoutput(cmd)
      if rc != 0:
        raise Exception, output


if __name__ == '__main__':
  with TempDir() as tmpdir:
    os.chdir(tmpdir.path)
    tmprep = TempRepository()
    tmprep.setUp()
    unittest.main()
