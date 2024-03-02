#!/usr/bin/env zsh

echo "LINE STATS"
echo "----------"
radon raw daikanban/**/*.py -s | tail -n 11 | head -n 7
