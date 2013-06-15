#!/bin/bash

source ../../common.sh

ARCHIVE_NAME=dpxdt_deployment
TEMP_DIR=/tmp/$ARCHIVE_NAME
OUTPUT_ARCHIVE=/tmp/$ARCHIVE_NAME.tar.gz
INSTALL_PATH=/usr/local/share

rm -Rf $TEMP_DIR
cp -R -L . $TEMP_DIR
find $TEMP_DIR -name '*.pyc' -or -name '.*' | xargs rm
cp $PHANTOMJS_BINARY $TEMP_DIR
cp $PDIFF_BINARY $TEMP_DIR
tar zcf $OUTPUT_ARCHIVE -C /tmp $ARCHIVE_NAME

echo "scp $OUTPUT_ARCHIVE foo@bar:$INSTALL_PATH"
echo "cd $INSTALL_PATH"
echo "tar zxf $ARCHIVE_NAME.tar.gz"
echo "cp -R $INSTALL_PATH/$ARCHIVE_NAME/runit /etc/service/dpxdt_worker"
echo "sv start dpxdt_worker"
