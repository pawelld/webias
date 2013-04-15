#!/bin/bash

TMPDIR=`mktemp -d`

cat << EOF
This script prepares a zip file containing source code of the WeBIAS server 
to be published to conform with the AGPL license.

It assumes that WeBIAS has been checked out from the Subversion repository 
(it queries SVN to determine files belonging to the distribution). If you 
have added files of your own which should be distributed, you have to account 
for them manually.

The resulting file is put in the media directory.


EOF

echo "Copying files to a temporary directory ..."

svn -R list | cpio -p --make-directories $TMPDIR/webias

pushd $TMPDIR > /dev/null

echo "Zipping ..."

zip  -r source.zip webias  > /dev/null

popd > /dev/null

echo Copying source.zip to `pwd`/media/ ...

cp  $TMPDIR/source.zip media

echo "Cleaning up ..."
rm -rf $TMPDIR

echo "Done."
