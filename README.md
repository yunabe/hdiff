# hdiff
## Prerequisite
### Install htmlfwd
Follow [the instruction of htmlfwd](https://github.com/yunabe/htmlfwd/blob/master/README.md)

## Install hdiff
* Add hdiff/bin to PATH
* Or create a symbolic link to hdiff/bin/hdiff in a directory in PATH.

## Usage
### Show git diff

    hdiff git

### Show mercurial diff

    hdiff hg

### Show diff of files or directories

    hdiff diff

## Notes
Files in codereview and static are copied from
[rietvelt](http://code.google.com/p/rietveld/) revision 840f9bb917ba.

codereview/engine.py was modified a little from the original.
[diff](https://github.com/yunabe/hdiff/commit/c3cd511524a806ad6ca015ad15d852026209ec74),
[diff](https://github.com/yunabe/hdiff/commit/0b0df4e2b0fa3c22f59cb48ab631c12bb341eb43)
