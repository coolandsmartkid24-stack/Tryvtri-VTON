# TryVtri Shopify Storefront Integration Guide

## Zero API Credentials Requirement

TryVtri requires **NO** Shopify Admin API access tokens, private app keys, store passwords, manually configured domains, or Shopify store authentication.

### How Product Image Retrieval Works

The integration operates entirely on the Shopify storefront via Liquid and a lightweight client-side JavaScript widget:

1. **Automatic Product Context**:
   When a visitor opens a product page, the Liquid card block (`tryvtri-card.liquid`) automatically extracts:
   - `product.id`
   - `product.title`
   - `product.featured_image` (Shopify CDN URL)
   - `product.selected_or_first_available_variant`
   - Variant-specific images for all variants via embedded JSON metadata.

2. **Automatic Variant Switching**:
   - The widget automatically listens for storefront variant change events (`variant:change`, `theme:variant:change`, and DOM form changes).
   - When a customer selects a size, color, or style, the garment image URL updates immediately.
   - If the selected variant does not have an individual image, it automatically falls back to the product's featured image.

3. **Try-On Request Flow**:
   - Customer uploads their photo.
   - Widget sends the customer's photo and the current variant's public Shopify CDN image URL to `POST /try-on-vton`.
   - The FastAPI backend validates the CDN image URL with strict SSRF protection and downloads it directly from Shopify's CDN.
   - The result is generated via FASHN VTON 1.5 and returned directly to the storefront popup.

---

## Installation Methods

### Method A: Shopify Theme App Extension (Recommended)

1. Copy `shopify/blocks/tryvtri-card.liquid` into your theme extension's `blocks/` directory.
2. Copy `shopify/assets/tryvtri.css` and `shopify/assets/tryvtri.js` into `assets/`.
3. In the Shopify Theme Editor:
   - Open any **Product Page** template.
   - Click **Add block** under the Product Information section.
   - Select **Try-On Card**.
   - Configure the FastAPI Backend URL (e.g., `https://api.yourdomain.com`).
   - Save your theme.

### Method B: Custom Liquid Block (No App Required)

1. Upload `tryvtri.css` and `tryvtri.js` to your theme's Assets folder.
2. In the theme editor on the Product page, add a **Custom Liquid** block.
3. Paste the contents of `shopify/blocks/tryvtri-card.liquid` (excluding the `{% schema %}` section at the bottom).
4. Set the backend URL in the block or via `window.TryVtriConfig = { api: 'https://api.yourdomain.com' };`.

---

## Supported Garment Categories

FASHN VTON 1.5 natively supports three garment categories:
- **`tops`**: Upper body garments (t-shirts, shirts, blouses, hoodies, sweaters, jackets).
- **`bottoms`**: Lower body garments (pants, trousers, jeans, skirts, shorts).
- **`one-pieces`**: Full body garments (dresses, jumpsuits, gowns, overalls).

> [!WARNING]
> Accessories, sunglasses, shoes, jewelry, and hats are **not** supported by FASHN VTON 1.5. Products in these categories should not display the virtual try-on card.

---

## Free Demo Limits

- Each visitor receives **exactly two free try-ons per rolling 24-hour period**.
- The limit is enforced atomically on the backend via Supabase customer row locks.
- Failed generations (due to upload issues or timeouts) **never** consume quota.
- When quota is reached, a friendly message displays the exact hours until another try becomes available.
