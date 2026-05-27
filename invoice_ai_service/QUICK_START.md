# ⚡ Quick Start - Invoice Intelligence Microservice

## 🚀 Start in 3 Commands

```bash
# 1. Start infrastructure
docker-compose up -d && sleep 30

# 2. Install dependencies
python -m venv venv && source venv/bin/activate && pip install -r requirements.txt

# 3. Run application
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 🌐 Access Points

- **Upload**: http://localhost:8000/frontend/upload.html
- **API Docs**: http://localhost:8000/docs
- **Health**: http://localhost:8000/api/v1/health
- **MinIO**: http://localhost:9001 (minioadmin/minioadmin)

## 📤 Test Upload

### Web Interface
1. Go to http://localhost:8000/frontend/upload.html
2. Drag & drop invoice file
3. Click "Upload & Process"
4. Get Job ID

### cURL
```bash
curl -X POST "http://localhost:8000/api/v1/upload" \
  -F "file=@invoice.pdf"
```

## ✅ Verify

```bash
# Check health
curl http://localhost:8000/api/v1/health

# Check services
docker-compose ps

# View logs
tail -f logs/audit.log
```

## 🎯 What Works Now

✅ File upload (PDF, Image, Excel, DOCX)  
✅ MinIO storage  
✅ Security scanning  
✅ Duplicate detection  
✅ Health monitoring  
✅ Web interface  

## 📋 Next: Phase 4

After testing uploads, we'll implement:
- PDF/Image/Excel/DOCX extraction
- **Multi-invoice separation** (for merged PDFs)
- Indian GST compliance

## 🐛 Quick Fixes

```bash
# Restart services
docker-compose restart

# Check logs
docker-compose logs -f

# Rebuild
docker-compose down && docker-compose up -d
```

---

**Ready to test!** 🚀 See `READY_TO_TEST.md` for detailed instructions.
