#!/bin/bash

echo "🔍 Checking Invoice Intelligence Services..."
echo ""

# Check Docker
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose not found. Please install it."
    exit 1
fi

# Check if services are running
echo "📦 Docker Services:"
docker-compose ps

echo ""
echo "🔍 Service Health Checks:"

# Check MinIO
if curl -s http://localhost:9000/minio/health/live > /dev/null 2>&1; then
    echo "✅ MinIO is running (port 9000)"
else
    echo "❌ MinIO is NOT running"
    echo "   Start with: docker-compose up -d minio"
fi

# Check Redis
if docker exec invoice_redis redis-cli ping > /dev/null 2>&1; then
    echo "✅ Redis is running (port 6379)"
else
    echo "❌ Redis is NOT running"
    echo "   Start with: docker-compose up -d redis"
fi

# Check PostgreSQL
if docker exec invoice_postgres pg_isready > /dev/null 2>&1; then
    echo "✅ PostgreSQL is running (port 5432)"
else
    echo "❌ PostgreSQL is NOT running"
    echo "   Start with: docker-compose up -d postgres"
fi

echo ""
echo "🌐 Access Points:"
echo "   MinIO Console: http://localhost:9001"
echo "   Application: http://localhost:8000"
echo ""

# Check if application is running
if curl -s http://localhost:8000/api/v1/ready > /dev/null 2>&1; then
    echo "✅ Application is running!"
    echo "   Health Check: http://localhost:8000/api/v1/health"
    echo "   Upload Page: http://localhost:8000/frontend/upload.html"
else
    echo "⏳ Application is not running yet"
    echo "   Start with: uvicorn app.main:app --reload"
fi

echo ""
