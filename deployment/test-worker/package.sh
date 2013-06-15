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

echo "Deployment package: $OUTPUT_ARCHIVE"
echo "Copy this to $INSTALL_PATH/$ARCHIVE_NAME"
echo "cd $INSTALL_PATH"
echo "tar zxf $OUTPUT_ARCHIVE"
echo "mkdir /etc/service/dpxdt_worker/"
echo "echo '#!/bin/bash' > /etc/service/dpxdt_worker/run"
echo "echo 'exec $INSTALL_PATH/$ARCHIVE_NAME/run.sh' >> /etc/service/dpxdt_worker/run"
echo "sv start dpxdt_worker"
