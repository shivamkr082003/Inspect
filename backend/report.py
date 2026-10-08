import io
import os
import re
import logging
import openpyxl
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as XLImage
from openpyxl.drawing.spreadsheet_drawing import TwoCellAnchor, AnchorMarker
from openpyxl.worksheet.pagebreak import Break, RowBreak
from PIL import Image as PILImage

logger = logging.getLogger(__name__)

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "template_clean.xlsx")

# Blocks relative to each "INSPECTION DIGITALS" header row H (1-indexed rows).
# (image_top, image_bottom, (left_category, right_category))
BLOCKS = [
    (1, 16, ("packed_cartons", "selected_cartons")),
    (19, 34, ("product_packaging", "product_packaging")),
    (37, 52, ("sample_vs_production", "product_weight")),
    (55, 70, ("measurement", "labels")),
    (72, 87, ("bulk_images", "bulk_images")),
    (89, 91, ("defects", "defects")),
]
# left photo spans columns A..B (1..2); right photo spans D..H (4..8)
LEFT_COLS = (1, 2)
RIGHT_COLS = (4, 8)

NV = "Not visible"


def severity_tally(defects):
    t = {"critical": 0, "major": 0, "minor": 0}
    for d in defects or []:
        s = (d.get("severity") or "minor").lower()
        t[s if s in t else "minor"] += 1
    return t


def barcode_check(product):
    et = product.get("extracted_text") or {}
    bc = (et.get("barcode") or "").strip()
    sku = (product.get("sku") or et.get("sku") or "").strip()
    norm = lambda s: "".join(ch for ch in s.upper() if ch.isalnum())
    if not bc or not sku:
        return {"status": "not_available", "note": "No barcode and/or SKU legible to cross-check."}
    b, s = norm(bc), norm(sku)
    if b == s or (len(s) >= 4 and (s in b or b in s)):
        return {"status": "match", "note": f"Barcode and SKU are consistent ({bc})."}
    return {"status": "mismatch", "note": f"Barcode '{bc}' does not match SKU '{sku}'."}


def _find_headers(ws):
    rows = []
    for r in range(1, ws.max_row + 1):
        v = ws.cell(r, 1).value
        if v and str(v).strip() == "INSPECTION DIGITALS":
            rows.append(r)
    return rows


def _build_slots(ws):
    slots = []
    for H in _find_headers(ws):
        for top, bottom, (catL, catR) in BLOCKS:
            slots.append({"category": catL, "c0": LEFT_COLS[0], "c1": LEFT_COLS[1],
                          "r0": H + top, "r1": H + bottom})
            slots.append({"category": catR, "c0": RIGHT_COLS[0], "c1": RIGHT_COLS[1],
                          "r0": H + top, "r1": H + bottom})
    return slots


def _col_px(ws, c):
    w = ws.column_dimensions[get_column_letter(c)].width or 8.43
    return int(round(w * 7 + 5))


def _row_px(ws, r):
    h = ws.row_dimensions[r].height or 15.0
    return int(round(h * 4 / 3))


def _box_px(ws, slot):
    w = sum(_col_px(ws, c) for c in range(slot["c0"], slot["c1"] + 1))
    h = sum(_row_px(ws, r) for r in range(slot["r0"], slot["r1"] + 1))
    return max(w, 40), max(h, 40)


def _letterbox(raw: bytes, box_w: int, box_h: int) -> io.BytesIO:
    img = PILImage.open(io.BytesIO(raw))
    if getattr(img, "is_animated", False):
        img.seek(0)
    img = img.convert("RGB")
    img.thumbnail((box_w, box_h))
    canvas = PILImage.new("RGB", (box_w, box_h), (255, 255, 255))
    canvas.paste(img, ((box_w - img.width) // 2, (box_h - img.height) // 2))
    out = io.BytesIO()
    canvas.save(out, format="JPEG", quality=82)
    out.seek(0)
    return out


def _crop_defect(raw: bytes, bbox: dict) -> bytes:
    """Crop a padded close-up around a normalized bbox {x,y,w,h}."""
    img = PILImage.open(io.BytesIO(raw)).convert("RGB")
    W, H = img.size
    try:
        x = float(bbox.get("x", 0)); y = float(bbox.get("y", 0))
        w = float(bbox.get("w", 1)); h = float(bbox.get("h", 1))
    except (TypeError, ValueError):
        x, y, w, h = 0, 0, 1, 1
    pad = 0.06
    l = int(max(0.0, x - pad) * W); t = int(max(0.0, y - pad) * H)
    r = int(min(1.0, x + w + pad) * W); b = int(min(1.0, y + h + pad) * H)
    if r - l < 20 or b - t < 20:
        l, t, r, b = 0, 0, W, H
    crop = img.crop((l, t, r, b))
    out = io.BytesIO()
    crop.save(out, format="JPEG", quality=85)
    return out.getvalue()


def _place_image(ws, slot, raw: bytes):
    bw, bh = _box_px(ws, slot)
    buf = _letterbox(raw, bw, bh)
    xi = XLImage(buf)
    frm = AnchorMarker(col=slot["c0"] - 1, colOff=0, row=slot["r0"] - 1, rowOff=0)
    to = AnchorMarker(col=slot["c1"], colOff=0, row=slot["r1"], rowOff=0)
    xi.anchor = TwoCellAnchor(editAs="twoCell", _from=frm, to=to)
    ws.add_image(xi)


def _merged_anchor(ws, coord):
    for m in ws.merged_cells.ranges:
        if coord in m:
            return m.min_row, m.min_col
    cell = ws[coord]
    return cell.row, cell.column


def _set(ws, coord, value):
    r, c = _merged_anchor(ws, coord)
    ws.cell(r, c).value = value


def _sanitize_sheet_name(name, existing):
    name = re.sub(r"[\[\]:\*\?/\\]", " ", str(name)).strip()[:28] or "Product"
    base = name
    i = 1
    while name in existing:
        suffix = f" ({i})"
        name = base[:28 - len(suffix)] + suffix
        i += 1
    return name


def _fill_values(ws, prod, photo_map):
    sku = prod.get("sku") if prod.get("sku_readable") else None
    sku_disp = sku or NV
    et = prod.get("extracted_text") or {}

    # identity fields -- never invented; default to "Not visible"
    _set(ws, "B6", NV)                       # buyer name
    _set(ws, "F6", NV)                       # inspection date
    _set(ws, "B7", et.get("markings") or NV) # PO# (only if legibly on carton)
    _set(ws, "F7", NV)                       # ship date
    _set(ws, "B8", NV)                       # vendor name
    _set(ws, "B9", NV)                       # invoice no
    _set(ws, "B10", (prod.get("description") or NV)[:120])  # item
    _set(ws, "B11", NV)                      # total order qty
    _set(ws, "B12", f"Visible units in photos: {prod.get('visible_unit_count', 0)}")

    # description / available-qty row
    _set(ws, "A15", (prod.get("description") or NV)[:120])
    _set(ws, "C15", prod.get("visible_unit_count", 0))   # Available Qty (visible)
    _set(ws, "D15", prod.get("visible_unit_count", 0))   # Inspected Qty (visible)

    # Style# on first inspection-digitals section
    _set(ws, "D210", f"Style# {sku_disp}")

    # SKU on measurement & weight sub-sheets
    _set(ws, "A105", sku_disp)
    _set(ws, "A131", sku_disp)

    # Defects table (workmanship), header row 87; data from row 88
    defects = prod.get("defects") or []
    if defects:
        r = 88
        for d in defects[:14]:
            _set(ws, f"A{r}", sku_disp)
            desc = d.get("description", "")
            ph = d.get("photo")
            if ph and ph in photo_map:
                desc = f"{desc} [see {photo_map[ph]}]"
            conf = d.get("confidence")
            if conf:
                desc = f"{desc} (conf: {conf})"
            _set(ws, f"B{r}", desc)
            _set(ws, f"D{r}", d.get("location") or NV)
            sev = (d.get("severity") or "").lower()
            if sev == "critical":
                _set(ws, f"F{r}", 1)
            elif sev == "major":
                _set(ws, f"G{r}", 1)
            else:
                _set(ws, f"H{r}", 1)
            r += 1
    else:
        _set(ws, "A88", sku_disp)
        _set(ws, "B88", "No visible defects identified in supplied photos (not a pass/fail determination).")

    # Severity rollup into the AQL "Defects Found" row (B=Critical, C=Major, D=Minor)
    tally = severity_tally(defects)
    _set(ws, "B39", tally["critical"])
    _set(ws, "C39", tally["major"])
    _set(ws, "D39", tally["minor"])

    # Measurements sub-sheet (rows 105+)
    r = 105
    for m in (prod.get("measurements") or [])[:10]:
        val = f"{m.get('value', '')} {m.get('unit', '')}".strip()
        if val:
            _set(ws, f"A{r}", sku_disp)
            _set(ws, f"B{r}", "No spec from photos")
            _set(ws, f"C{r}", val)
            r += 1

    # Weight sub-sheet (rows 131+)
    r = 131
    for w in (prod.get("weights") or [])[:8]:
        val = f"{w.get('value', '')} {w.get('unit', '')}".strip()
        if val:
            _set(ws, f"A{r}", sku_disp)
            _set(ws, f"B{r}", "No standard from photos")
            _set(ws, f"C{r}", val)
            r += 1

    # Findings summary -> SPECIAL COMMENTS (A52 header) area
    summary = _build_summary(prod)
    _set(ws, "A53", summary)
    cell = ws.cell(*_merged_anchor(ws, "A53"))
    cell.alignment = openpyxl.styles.Alignment(wrap_text=True, vertical="top")

    # Traceability + unresolved -> SPECIAL REMARKS (A171 header) area
    remarks = _build_remarks(prod, photo_map)
    _set(ws, "A172", remarks)
    cell = ws.cell(*_merged_anchor(ws, "A172"))
    cell.alignment = openpyxl.styles.Alignment(wrap_text=True, vertical="top")


def _build_summary(prod):
    lines = [
        f"Distinct product designs identified: {prod.get('distinct_design_count', 1)}",
        f"Visible units counted in photos: {prod.get('visible_unit_count', 0)} "
        "(visible count only - does NOT represent total quantity inside closed cartons).",
        f"SKU: {prod.get('sku') if prod.get('sku_readable') else 'Not readable from photos'}",
    ]
    et = prod.get("extracted_text") or {}
    extracted = []
    for k in ("model", "barcode", "quantities", "markings"):
        if et.get(k):
            extracted.append(f"{k}: {et[k]}")
    if et.get("labels"):
        extracted.append("labels: " + "; ".join(et["labels"][:6]))
    if extracted:
        lines.append("Extracted text: " + " | ".join(extracted))
    if prod.get("characteristics"):
        lines.append("Characteristics: " + prod["characteristics"])
    if prod.get("packaging"):
        lines.append("Packaging: " + prod["packaging"])
    if prod.get("comparison_notes"):
        lines.append("Comparison: " + prod["comparison_notes"])
    if prod.get("grouping_uncertain"):
        lines.append("GROUPING UNCERTAIN: " + (prod.get("grouping_uncertain_reason") or "products look too similar to separate reliably."))
    conf = prod.get("confidence") or {}
    if conf:
        lines.append(
            "AI confidence - SKU: {sku}, visible units: {vu}, grouping: {g}, overall: {o}".format(
                sku=conf.get("sku", "n/a"), vu=conf.get("visible_unit_count", "n/a"),
                g=conf.get("grouping", "n/a"), o=conf.get("overall", "n/a"),
            )
        )
    bc = barcode_check(prod)
    prefix = {"match": "Barcode check OK: ", "mismatch": "BARCODE MISMATCH: ",
              "not_available": "Barcode check: "}.get(bc["status"], "")
    lines.append(prefix + bc["note"])
    tally = severity_tally(prod.get("defects"))
    lines.append("Defects by severity - critical: {c}, major: {m}, minor: {n} "
                 "(AQL limits in template: critical 0, major 2.5, minor 4; "
                 "max allowed depends on lot size - not determinable from photos).".format(
                     c=tally["critical"], m=tally["major"], n=tally["minor"]))
    return "\n".join(lines)


def _build_remarks(prod, photo_map):
    lines = ["Photo traceability (this product):"]
    cat_count = {}
    for ph in prod.get("photos", []):
        n = ph.get("photo")
        fn = photo_map.get(n, f"photo {n}")
        cat = ph.get("category", "")
        cat_count[cat] = cat_count.get(cat, 0) + 1
        lines.append(f"  - {fn} -> {cat}")
    lines.append("")
    lines.append("Deliberately UNRESOLVED (cannot be proven from photos):")
    unresolved = prod.get("unresolved") or [
        "Buyer, supplier/vendor, PO number, order quantity, ship date, test results and pass/fail decision are not visible in the photos.",
    ]
    for u in unresolved:
        lines.append(f"  - {u}")
    return "\n".join(lines)


def generate_report(products: list[dict]) -> bytes:
    """products: list of analysis dicts, each with extra key 'photo_items':
       list of {photo(1-based global), category, bytes, filename}."""
    wb = openpyxl.load_workbook(TEMPLATE_PATH)
    master = wb["Sheet1"]
    master_breaks = [b.id for b in master.row_breaks.brk]

    if not products:
        products = [{"sku": None, "sku_readable": False, "photo_items": [],
                     "description": NV, "visible_unit_count": 0, "distinct_design_count": 0,
                     "unresolved": ["No analysable products were identified in the uploaded photos."]}]

    created = []
    for i, prod in enumerate(products, 1):
        ws = wb.copy_worksheet(master)
        default_name = prod.get("sku") if prod.get("sku_readable") else f"Product {i}"
        ws.title = _sanitize_sheet_name(default_name or f"Product {i}", created)
        created.append(ws.title)

        # restore page breaks (copy_worksheet drops them)
        rb = RowBreak()
        for bid in master_breaks:
            rb.append(Break(id=bid))
        ws.row_breaks = rb

        photo_items = prod.get("photo_items", [])
        photo_map = {it["photo"]: it["filename"] for it in photo_items}
        bytes_by_idx = {it["photo"]: it["bytes"] for it in photo_items}

        # build defect close-up crops (Defect Spotlight)
        defect_crops = []
        for d in prod.get("defects", []):
            ph = d.get("photo")
            bb = d.get("bbox")
            if ph in bytes_by_idx and bb:
                try:
                    defect_crops.append(_crop_defect(bytes_by_idx[ph], bb))
                except Exception as e:
                    logger.error(f"defect crop failed: {e}")

        _fill_values(ws, prod, photo_map)
        _place_photos(ws, photo_items, defect_crops)

    del wb["Sheet1"]

    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out.getvalue()


def _place_photos(ws, photo_items, defect_crops):
    slots = _build_slots(ws)
    defect_idx = [i for i, s in enumerate(slots) if s["category"] == "defects"]
    other_idx = [i for i, s in enumerate(slots) if s["category"] != "defects"]
    used = [False] * len(slots)

    def take_from(pool, category=None):
        if category:
            for i in pool:
                if not used[i] and slots[i]["category"] == category:
                    used[i] = True
                    return slots[i]
        for i in pool:
            if not used[i]:
                used[i] = True
                return slots[i]
        return None

    # defect close-up crops go into the reserved Defects slots first
    for crop in defect_crops:
        slot = take_from(defect_idx) or take_from(other_idx)
        if slot is None:
            break
        try:
            _place_image(ws, slot, crop)
        except Exception as e:
            logger.error(f"failed to place defect crop: {e}")

    # general product photos go into all remaining (non-defect) slots
    for it in photo_items:
        cat = it.get("category")
        if cat == "defects":
            cat = "bulk_images"
        slot = take_from(other_idx, cat) or take_from(other_idx) or take_from(defect_idx)
        if slot is None:
            logger.warning("Ran out of photo slots; skipping extra photo")
            break
        try:
            _place_image(ws, slot, it["bytes"])
        except Exception as e:
            logger.error(f"failed to place image {it.get('filename')}: {e}")
