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
const FAL_API_BASE = "https://fal.run";

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Content-Type": "application/json",
  };
}

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
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

    if (!image_base64 || !garment_url) {
      res.status(400).json({ error: "image_base64 and garment_url are required" });
      return;
    }

    const apiKey = process.env.FAL_KEY;
    if (!apiKey) {
      res.status(500).json({ error: "FAL_KEY not configured on server" });
      return;
    }

    const finalPrompt =
      prompt ||
      "A person wearing the garment, virtual try-on, photorealistic, high detail";

    const input = {
      image_urls: [image_base64, garment_url],
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

    // Step 1: Submit request via queue API
    const submitResp = await fetch(
      `https://queue.fal.run/${FAL_MODEL}/submit`,
      {
        method: "POST",
        headers: {
          Authorization: `Key ${apiKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ input }),
      }
    );

    if (!submitResp.ok) {
      const errText = await submitResp.text();
      throw new Error(`Fal submit failed: ${submitResp.status} ${errText}`);
    }

    const submitData = await submitResp.json();
    const requestId = submitData.request_id;

    if (!requestId) {
      throw new Error("No request_id returned from fal.ai submit");
    }

    // Step 2: Poll for result
    let result;
    for (let i = 0; i < 120; i++) {
      const statusResp = await fetch(
        `https://queue.fal.run/${FAL_MODEL}/status/${requestId}`,
        {
          headers: {
            Authorization: `Key ${apiKey}`,
          },
        }
      );

      if (!statusResp.ok) {
        throw new Error(`Fal status check failed: ${statusResp.status}`);
      }

      const statusData = await statusResp.json();

      if (statusData.status === "completed" || statusData.status === "COMPLETED") {
        const resultResp = await fetch(
          `https://queue.fal.run/${FAL_MODEL}/result/${requestId}`,
          {
            headers: {
              Authorization: `Key ${apiKey}`,
            },
          }
        );

        if (!resultResp.ok) {
          throw new Error(`Fal result fetch failed: ${resultResp.status}`);
        }

        result = await resultResp.json();
        break;
      }

      if (statusData.status === "failed" || statusData.status === "FAILED") {
        throw new Error(`Fal inference failed: ${JSON.stringify(statusData)}`);
      }

      await sleep(1000);
    }

    if (!result) {
      throw new Error("Fal inference timed out");
    }

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
