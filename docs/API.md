# TryVtri FASHN VTON 1.5 — API Specification

The TryVtri virtual try-on backend provides REST APIs for the Shopify storefront widget, the React Admin Dashboard, and GPU lifecycle management.

---

## Storefront Endpoints

### 1. `POST /try-on-vton`
Executes virtual try-on using FASHN VTON 1.5.

- **Content-Type**: `multipart/form-data`
- **Authentication**: None required (public storefront endpoint with CORS `*`)

#### Parameters
| Field | Type | Required | Description |
|---|---|---|---|
| `person_image` | File | Yes | Customer full-body photo (JPG/PNG/WebP, max 8 MB) |
| `garment_url` | String | Conditional | Public URL to garment image (Shopify CDN) |
| `garment_image` | File | Conditional | Direct upload of garment image |
| `category` | String | No | Garment category: `tops`, `bottoms`, `one-pieces` (default: `tops`) |
| `shopify_customer_id` | String | No | Shopify customer ID if visitor is logged in |
| `email` | String | No | Customer email |
| `session_id` | String | No | Client session identifier |
| `product_id` | String | No | Shopify product ID |
| `variant_id` | String | No | Selected variant ID |
| `product_title` | String | No | Product title |

#### Response (`200 OK`)
```json
{
  "success": true,
  "request_id": "b18f0a...",
  "output_url": "data:image/png;base64,...",
  "result_image": "data:image/png;base64,...",
  "category": "tops",
  "duration_ms": 3450,
  "quota": {
    "customer_id": "uuid-...",
    "limit": 2,
    "window_hours": 24,
    "used": 1,
    "remaining": 1,
    "eligible": true,
    "reset_at": null
  }
}
```

#### Quota Limit Exceeded (`429 Too Many Requests`)
```json
{
  "error": "quota_exceeded",
  "message": "You have used your free demo limit of 2 try-ons. Next try available after 2026-11-04T12:00:00Z.",
  "details": {
    "customer_id": "uuid-...",
    "used": 2,
    "remaining": 0,
    "limit": 2,
    "reset_at": "2026-11-04T12:00:00Z",
    "window_hours": 24
  }
}
```

---

### 2. `GET /tryvtry-vton/products`
Retrieves and validates product and variant context provided by the storefront.

- **Parameters**: `garment_url`, `product_id`, `variant_id`, `product_title`, `category`
- **Zero Shopify Credentials**: Does **not** require Shopify Admin API tokens or store passwords.

---

### 3. `GET /tryvtri-vton/check-usage`
Checks customer remaining try-on quota before prompting for photo upload.

- **Parameters**: `email`, `shopify_customer_id`, `session_id`
- **Response**: `count`, `remaining`, `limit`, `eligible`, `reset_at`, `window_hours`.

---

## GPU Monitoring Endpoints

### 4. `GET /gpu/status`
Returns live state of the on-demand GPU.

```json
{
  "status": "running",
  "gpu_model": "RTX 5080",
  "pod_id": "pod-18239",
  "price_per_hour": 0.36,
  "active_requests": 1,
  "queued_requests": 0,
  "started_at": "2026-11-03T12:00:00Z",
  "total_runtime_seconds": 1240,
  "total_estimated_cost_usd": 0.1240
}
```

---

## Admin Endpoints

Protected by Bearer JWT token in the `Authorization` header.

### 5. `POST /admin/login`
- **Body**: `{"username": "admin", "password": "..."}`
- **Response**: `{"access_token": "...", "token_type": "bearer", "expires_in_minutes": 720}`

### 6. `GET /admin/dashboard`
Returns aggregated metrics from Supabase:
- Total registered customers
- Customers who used the demo
- Total successful and failed try-ons
- Free tries consumed
- Quota exhausted vs eligible counts

### 7. `GET /admin/customers`
Paginated customer list with remaining tries and rolling reset timestamps.

### 8. `GET /admin/usage`
Daily usage breakdown and product-wise virtual try-on statistics.

### 9. `POST /admin/gpu/start` & `POST /admin/gpu/stop`
Manual controls for administrator to start or stop the GPU pod.
