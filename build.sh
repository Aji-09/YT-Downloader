#!/bin/bash
# Install system dependencies
apt-get update && apt-get install -y ffmpeg
# Install Python dependencies
pip install -r requirements.txt
