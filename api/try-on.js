/**
 * TryVtri Virtual Try-On — Vercel serverless proxy for fal.ai.
 *
 * Keeps the FAL_KEY server-side (never exposed to the browser).
 * Endpoint: POST /api/try-on
 * Body (JSON):
 *   {
 *     image_base64: "data:image/jpeg;base64,...",  // customer photo
 *     garment_url: "https://cdn.shopify.com/...",  // Shopify garment image
 *     prompt?: string,
 *     guidance_scale?: number,       // default 2.5
 *     num_inference_steps?: number,  // default 40
 *     acceleration?: string,         // default "regular"
 *     enable_safety_checker?: bool,  // default true
 *     output_format?: string,        // default "png"
 *     num_images?: number,           // default 1
 *     lora_scale?: number,           // default 1
 *     image_size?: { width, height } // optional
 *     seed?: number,                 // optional
 *     sync_mode?: bool               // default false
 *   }
 * Returns: { images: [{url, content_type, file_name, width, height}], seed, prompt }
 */

import { fal } from "@fal-ai/client";

const FAL_MODEL = "fal-ai/flux-2-lora-gallery/virtual-tryon";

// Read API key from server environment (Vercel project setting: FAL_KEY)
if (process.env.FAL_KEY) {
  fal.config({ credentials: process.env.FAL_KEY });
}

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json",
  };
}

export default async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") {
    res.status(204).end();
    return;
  }

  if (req.method !== "POST") {
    res.status(405).json({ error: "Method not allowed. Use POST." });
    return;
  }

  try {
    const {
      image_base64,
      garment_url,
      prompt,
      guidance_scale = 2.5,
      num_inference_steps = 40,
      acceleration = "regular",
      enable_safety_checker = true,
      output_format = "png",
      num_images = 1,
      lora_scale = 1,
      image_size,
      seed,
      sync_mode = false,
    } = req.body || {};

    if (!image_base64) {
      res.status(400).json({ error: "image_base64 is required" });
      return;
    }
    if (!garment_url) {
      res.status(400).json({ error: "garment_url is required" });
      return;
    }

    // Convert base64 data URI to a File for fal storage upload
    const match = String(image_base64).match(/^data:([^;]+);base64,(.*)$/);
    if (!match) {
      res.status(400).json({ error: "image_base64 must be a data URI" });
      return;
    }
    const mime = match[1];
    const buffer = Buffer.from(match[2], "base64");
    const ext = mime.split("/").pop() || "jpg";
    const personFile = new File([buffer], `person.${ext}`, { type: mime });

    // Upload customer photo to fal storage (returns a public URL)
    const personUrl = await fal.storage.upload(personFile);

    const finalPrompt =
      prompt ||
      "A person wearing the garment, virtual try-on, photorealistic, high detail";

    const result = await fal.subscribe(FAL_MODEL, {
      input: {
        image_urls: [personUrl, garment_url],
        prompt: finalPrompt,
        guidance_scale,
        num_inference_steps,
        acceleration,
        enable_safety_checker,
        output_format,
        num_images,
        lora_scale,
        sync_mode,
        ...(image_size ? { image_size } : {}),
        ...(seed !== undefined ? { seed } : {}),
      },
      logs: true,
    });

    res.status(200).json({
      images: (result.data && result.data.images) || result.images || [],
      seed: result.data?.seed ?? result.seed,
      prompt: result.data?.prompt ?? result.prompt,
    });
  } catch (err) {
    console.error("try-on error:", err);
    res.status(500).json({
      error: err.message || "Virtual try-on failed",
    });
  }
}
