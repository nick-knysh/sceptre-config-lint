#!/bin/sh -l

echo "Processing $1"
result=$(python linter.py $1)
echo "$result" >> $GITHUB_OUTPUT


