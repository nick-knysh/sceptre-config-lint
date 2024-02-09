#!/bin/sh -l
cfn-lint --version

echo "Processing linter.py $1"
python /linter.py $1

