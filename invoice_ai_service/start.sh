#!/bin/bash

# Invoice Intelligence Microservice - Quick Start Script

echo "🚀 Starting Invoice Intelligence Microservice..."
echo ""

# Check if docker-compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose is not installed. Please install it first."
    exit 1
fi

# Start infrastructure services
echo "📦 Starting infrastructure services (PostgreSQL, Redis, MinIO)..."
docker-compose up -d

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 10

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "🐍 Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing Python dependencies..."
pip install -q -r requirements.txt

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file..."
    cp .env.example .env
fi

# Create logs directory
mkdir -p logs

echo ""
echo "✅ Setup complete!"
echo ""
echo "🌐 Starting FastAPI application..."
echo ""
echo "Access points:"
echo "  - Frontend: http://localhost:8000/frontend/index.html"
echo "  - API Docs: http://localhost:8000/docs"
echo "  - Health Check: http://localhost:8000/api/v1/health"
echo "  - MinIO Console: http://localhost:9001 (minioadmin/minioadmin)"
echo ""

# Start the application
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
