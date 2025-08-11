#!/usr/bin/env bash
set -e

echo "Installing build dependencies..."
python -m pip install --upgrade pip
python -m pip install setuptools>=68.0.0 wheel>=0.41.0

echo "Installing project dependencies..."
python -m pip install -r requirements.txt

echo "Build completed successfully!"

