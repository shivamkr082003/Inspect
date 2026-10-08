import os
import io
import json
import base64
import logging
import httpx
from PIL import Image

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OPENROUTER_MODEL = "openrouter/free"

VALID_CATEGORIES = [
    "packed_cartons", "selected_cartons", "product_packaging",
    "sample_vs_production", "product_weight", "measurement",
    "labels", "bulk_images", "defects",
]

SYSTEM_PROMPT = """You are a senior quality-control inspector working for a buying house (sourcing company).
You are given a batch of inspection photographs of products and their packaging, in order (photo 1, photo 2, ...).
Your job is to analyse ONLY what is visibly provable in the photos and produce a strict, truthful JSON report.

CRITICAL TRUTHFULNESS RULES:
- NEVER invent a buyer, supplier/vendor, purchase-order number, order quantity, ship date, specification, test result, or any pass/fail decision. These almost never appear in product photos. If not clearly legible in a photo, mark them unresolved.
- Only read text (SKU, model, barcode, quantities, markings, measurements, scale/weight displays) when it is actually legible. Always include units for measurements and weights.
- The visible unit count is ONLY the number of individual physical units you can actually see in the photos. It does NOT represent the total quantity inside closed cartons. Never claim otherwise.
- If two products look too similar to separate reliably, set grouping_uncertain=true and explain.
- If a value is unreadable or a required view is missing, leave it unresolved. Do not guess. Do not silently mark anything as passed.

GROUPING RULES:
- Identify each DISTINCT product/design across the whole batch.
- Group every photo of the SAME product together even when it shows different angles, cartons, labels, weight readings, measurements, packaging, or defects.
- Do NOT treat two photos of the same physical unit as two different units.

For EACH distinct product, assign every one of its photos to exactly ONE category from this list:
packed_cartons, selected_cartons, product_packaging, sample_vs_production, product_weight, measurement, labels, bulk_images, defects
(use "bulk_images" when it is a general/overview shot that fits no specific category).

Return ONLY valid JSON (no markdown, no commentary) with this exact shape:
{
  "products": [
    {
      "sku": "string or null if not legible",
      "sku_readable": true/false,
      "distinct_design_count": 1,
      "visible_unit_count": 0,
      "description": "short description of the product",
      "characteristics": "visible material/color/construction characteristics",
      "packaging": "visible packaging description or 'Not visible'",
      "extracted_text": {"sku": "", "model": "", "barcode": "", "quantities": "", "markings": "", "labels": ["..."]},
      "measurements": [{"value": "", "unit": "", "photo": 1, "confidence": "high|medium|low"}],
      "weights": [{"value": "", "unit": "", "photo": 1, "confidence": "high|medium|low"}],
      "defects": [{"description": "", "location": "", "severity": "minor|major|critical", "photo": 1, "confidence": "high|medium|low", "bbox": {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0}}],
      "grouping_uncertain": false,
      "grouping_uncertain_reason": "",
      "comparison_notes": "only if photos give sufficient evidence, else ''",
      "unresolved": ["list plain statements of what cannot be determined from photos"],
      "confidence": {"sku": "high|medium|low", "visible_unit_count": "high|medium|low", "grouping": "high|medium|low", "overall": "high|medium|low"},
      "photos": [{"photo": 1, "category": "labels", "note": "why"}]
    }
  ],
  "batch_notes": "overall notes",
  "overall_unresolved": ["buyer, PO, vendor, order qty, ship date, test results and pass/fail cannot be established from photos unless legibly shown"]
}
photo numbers are 1-based and refer to the order the images were supplied.
For every defect, ALSO return "bbox": a tight bounding box around the defect on its photo, as fractions of image width/height: x,y = top-left corner (0..1), w,h = width/height (0..1). If you cannot localize it, use {"x":0,"y":0,"w":1,"h":1}.
Give a "confidence" of high/medium/low for each defect, measurement, weight, and for the product-level sku, visible_unit_count, grouping and overall reading. Be conservative: use "low" when text is blurry or inferred."""


def _prep_image(raw: bytes) -> str | None:
    try:
        img = Image.open(io.BytesIO(raw))
        if getattr(img, "is_animated", False):
            img.seek(0)
        img = img.convert("RGB")
        img.thumbnail((1024, 1024))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        logger.error(f"image prep failed: {e}")
        return None


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in model response")
    return json.loads(text[start:end + 1])


async def analyze_photos(photos: list[dict]) -> dict:
    """photos: list of {index(1-based), bytes}. Returns parsed analysis dict."""
    api_key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set; add it to backend/.env to enable AI vision analysis")
    model = (os.environ.get("OPENROUTER_MODEL") or "").strip() or DEFAULT_OPENROUTER_MODEL

    images = []
    for p in photos:
        b64 = _prep_image(p["bytes"])
        if b64:
            images.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

    text = (f"Here are {len(images)} inspection photos in order (photo 1 to photo {len(images)}). "
            "Analyse them and return the JSON report exactly as specified.")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [{"type": "text", "text": text}, *images]},
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:3000",
        "X-Title": "InspectAI",
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=30.0)) as client:
        resp = await client.post(OPENROUTER_URL, json=payload, headers=headers)
    if not resp.is_success:
        logger.error(f"OpenRouter {resp.status_code} (model={model}): {resp.text[:2000]}")
        raise RuntimeError(f"OpenRouter request failed ({resp.status_code}, model={model}): {resp.text[:500]}")

    body = resp.json()
    if body.get("error"):  # OpenRouter can report upstream failures inside a 200 body
        logger.error(f"OpenRouter error (model={model}): {body['error']}")
        raise RuntimeError(f"OpenRouter error (model={model}): {body['error']}")
    choice = (body.get("choices") or [{}])[0]
    raw = (choice.get("message") or {}).get("content")
    if isinstance(raw, list):
        raw = "".join(part.get("text", "") for part in raw if isinstance(part, dict))
    if not raw:
        raise RuntimeError(f"OpenRouter returned no content (model={body.get('model', model)}, "
                           f"finish_reason={choice.get('finish_reason')})")
    logger.info(f"OpenRouter vision response from {body.get('model', model)} for {len(images)} photos")
    data = _parse_json(raw)

    products = data.get("products") or []
    for i, prod in enumerate(products, 1):
        for ph in prod.get("photos", []):
            cat = ph.get("category")
            if cat not in VALID_CATEGORIES:
                ph["category"] = "bulk_images"
        if not prod.get("sku_readable"):
            prod.setdefault("sku", None)
    return data
