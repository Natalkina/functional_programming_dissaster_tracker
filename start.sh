#!/bin/bash

echo "🌍 Disaster Tracker - Start..."
echo ""

pip install -q -r requirements.txt

echo "Open: http://localhost:8000"
echo ""

python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
