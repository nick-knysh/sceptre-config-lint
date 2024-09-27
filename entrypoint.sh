#!/bin/sh -l
cfn-lint --version

echo "Processing linter.py $1"
python /linter.py $1
if [ $? != 0 ];
then
    exit 1
fi
exit 1

