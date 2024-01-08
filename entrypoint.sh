#!/bin/sh -l
cfn-lint --version
echo "Processing $1"
python /linter.py $1

