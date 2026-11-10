/**
 * TryVtri Virtual Try-On — Vercel serverless proxy for fal.ai.
 *
 * Endpoint: POST /api/try-on
 * Body (JSON):
 *   {
 *     image_base64: "data:image/jpeg;base64,...",
 *     garment_url: "https://cdn.shopify.com/...",
 *     prompt?: string,
 *     guidance_scale?: number,
 *     num_inference_steps?: number,
 *     acceleration?: string,
 *     enable_safety_checker?: bool,
 *     output_format?: string,
 *     num_images?: number,
 *     lora_scale?: number,
 *     image_size?: { width, height },
 *     seed?: number,
 *     sync_mode?: bool
 *   }
 * Returns: { images: [{url, content_type, file_name, width, height}], seed, prompt }
 */

const FAL_MODEL = "fal-ai/flux-2-lora-gallery/virtual-tryon";
const FAL_API_BASE = "https://api.fal.ai/v1";

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Content-Type": "application/json",
  };
}

export default async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization");

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

    const apiKey = process.env.FAL_KEY;
    if (!apiKey) {
      res.status(500).json({ error: "FAL_KEY not configured on server" });
      return;
    }

    // Convert base64 data URI to a buffer for upload
    const match = String(image_base64).match(/^data:([^;]+);base64,(.*)$/);
    if (!match) {
      res.status(400).json({ error: "image_base64 must be a data URI" });
      return;
    }
    const mime = match[1];
    const buffer = Buffer.from(match[2], "base64");

    // Step 1: Upload person image to fal storage
    const uploadResp = await fetch(`${FAL_API_BASE}/storage/upload`, {
      method: "POST",
      headers: {
        Authorization: `Key ${apiKey}`,
        "Content-Type": mime,
      },
      body: buffer,
    });

    if (!uploadResp.ok) {
      const errText = await uploadResp.text();
      throw new Error(`Fal storage upload failed: ${uploadResp.status} ${errText}`);
    }

    const uploadData = await uploadResp.json();
    const personUrl = uploadData.url;

    // Step 2: Submit the try-on request
    const finalPrompt =
      prompt ||
      "A person wearing the garment, virtual try-on, photorealistic, high detail";

    const input = {
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
    };

    const runResp = await fetch(
      `${FAL_API_BASE}/${FAL_MODEL}/run`,
      {
        method: "POST",
        headers: {
          Authorization: `Key ${apiKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(input),
      }
    );

    if (!runResp.ok) {
      const errText = await runResp.text();
      throw new Error(`Fal run failed: ${runResp.status} ${errText}`);
    }

    const result = await runResp.json();

    res.status(200).json({
      images: result.images || [],
      seed: result.seed,
      prompt: result.prompt,
    });
  } catch (err) {
    console.error("try-on error:", err);
    res.status(500).json({
      error: err.message || "Virtual try-on failed",
    });
  }
}
