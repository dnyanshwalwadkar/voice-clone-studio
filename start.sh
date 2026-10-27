#!/usr/bin/env bash
set -e

echo "========================================================"
echo "🎙️  Starting VoiceClone Studio Web Application"
echo "========================================================"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed or not in PATH."
    exit 1
fi

# Detect Virtual Environment
if [ -d "../venv" ]; then
    echo "⚡ Using parent virtual environment (../venv)..."
    source ../venv/bin/activate
elif [ -d "venv" ]; then
    echo "⚡ Using local virtual environment (./venv)..."
    source venv/bin/activate
else
    echo "📦 Creating new virtual environment (./venv)..."
    python3 -m venv venv
    source venv/bin/activate
    echo "📥 Installing dependencies from requirements.txt..."
    pip install --upgrade pip
    pip install -r requirements.txt
fi

# Check FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️ Warning: FFmpeg is not found in PATH. Please install it (brew install ffmpeg / sudo apt install ffmpeg)."
fi

echo "🚀 Launching VoiceClone Studio on http://localhost:7860"
python3 app.py
