#!/bin/sh -l
cfn-lint --version

echo "Processing linter.py $1"
CODE=$(python /linter.py $1)
exit $CODE
