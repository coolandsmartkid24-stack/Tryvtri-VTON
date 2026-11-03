# Local Development Guide (Windows / Linux)

This guide explains how to run the TryVtri FASHN VTON 1.5 system locally for development and testing.

---

## 1. Prerequisites

- Python 3.10+ (Python 3.14 compatible)
- Node.js 18+ and npm
- A free Supabase project (or in-memory mock fallback)

---

## 2. Backend Setup

1. **Activate virtual environment**:
   ```powershell
   cd "E:\VTON_GARMENTS\VTON TESTING\fashn-vton-1.5"
   .\.venv\Scripts\Activate.ps1
   ```

2. **Configure `.env`**:
   Copy `.env.example` to `.env` and configure:
   ```env
   ENVIRONMENT=development
   ADMIN_USERNAME=admin
   ADMIN_PASSWORD=your_secure_password
   JWT_SECRET=your_jwt_secret_key

   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_SECRET_KEY=sb_secret_your_key
   ```

3. **Start FastAPI backend**:
   ```powershell
   uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
   ```
   - OpenAPI Documentation: `http://localhost:8000/docs`
   - Health check: `http://localhost:8000/health`
   - Admin Dashboard (embedded): `http://localhost:8000/dashboard`

---

## 3. React Admin Dashboard Setup

1. **Install dependencies**:
   ```powershell
   cd dashboard
   npm install
   ```

2. **Run Vite development server**:
   ```powershell
   npm run dev
   ```
   - Access dashboard at `http://localhost:3000`
   - Proxies `/admin`, `/gpu`, `/try-on-vton` to FastAPI backend on port 8000.

3. **Production build**:
   ```powershell
   npm run build
   ```
   - Builds to `dashboard/dist/`, which FastAPI automatically serves at `/dashboard`.

---

## 4. Running the Test Suite

Run all automated unit, integration, and security tests:

```powershell
pytest tests -v
```

All 28 backend tests will execute:
- Health and OpenAPI schema validation
- SSRF prevention & IP filtering
- Customer 2-try / 24-hour quota enforcement
- Concurrent request race-condition protection
- Lium GPU manager lifecycle & 10-minute idle shutdown
- Admin authentication & JWT security
- Shopify zero-credential contract & variant switching
- Live Supabase integration
