#!/usr/bin/env bash
set -e

echo "Python version check:"
python --version

# Fail if Python 3.13
if python --version | grep -q "3.13"; then
    echo "ERROR: Python 3.13 detected. Need Python 3.11"
    exit 1
fi

pip install --upgrade pip setuptools wheel
pip install --only-binary=:all: -r requirements.txt

