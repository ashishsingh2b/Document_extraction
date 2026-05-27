# ⚡ START HERE - Invoice Intelligence Microservice

## 🚨 You Got an Error? Here's the Fix!

### Error: "Connection refused" to MinIO/Redis/PostgreSQL

**This means docker-compose services are not running.**

## ✅ Solution: Start Services First

### Step 1: Start Docker Services
```bash
cd invoice_ai_service
docker-compose up -d
```

Wait 30 seconds for services to start:
```bash
sleep 30
```

### Step 2: Verify Services are Running
```bash
docker-compose ps
```

You should see:
```
NAME                  STATUS
invoice_minio         Up
invoice_postgres      Up  
invoice_redis         Up
```

### Step 3: Now Start the Application
```bash
# Make sure you're in the virtual environment
source venv/bin/activate

# Start the app
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 🎯 Quick Verification

### Check if services are accessible:
```bash
# Check MinIO
curl http://localhost:9000/minio/health/live

# Check Redis
redis-cli ping

# Check PostgreSQL
docker exec invoice_postgres pg_isready
```

### Check application health:
```bash
curl http://localhost:8000/api/v1/health
```

## 🐛 Still Having Issues?

### Issue: Docker services won't start
```bash
# Stop everything
docker-compose down

# Start fresh
docker-compose up -d

# Check logs
docker-compose logs -f
```

### Issue: Port already in use
```bash
# Check what's using port 8000
lsof -i :8000

# Kill the process or use a different port
uvicorn app.main:app --reload --port 8001
```

### Issue: MinIO bucket not created
```bash
# Restart MinIO init
docker-compose restart minio-init

# Or create manually at http://localhost:9001
```

## ✅ Correct Startup Order

1. **Start Docker services** → `docker-compose up -d`
2. **Wait 30 seconds** → `sleep 30`
3. **Verify services** → `docker-compose ps`
4. **Start application** → `uvicorn app.main:app --reload`
5. **Test upload** → http://localhost:8000/frontend/upload.html

## 🚀 One-Line Startup (After First Time)

```bash
docker-compose up -d && sleep 30 && source venv/bin/activate && uvicorn app.main:app --reload
```

## 📞 Need Help?

The application will now start even if services are down, but you'll need them for:
- ✅ **MinIO** - File storage (uploads won't work without it)
- ✅ **Redis** - Job queue (async processing needs it)
- ✅ **PostgreSQL** - Database (audit logs need it)

**Check health status**: http://localhost:8000/api/v1/health

---

**Now try starting again!** 🚀
