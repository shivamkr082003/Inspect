import io
import logging
from PIL import Image as PILImage
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage,
    HRFlowable, KeepTogether,
)

logger = logging.getLogger(__name__)

CATEGORY_LABEL = {
    "packed_cartons": "Packed cartons", "selected_cartons": "Selected cartons",
    "product_packaging": "Product packaging", "sample_vs_production": "Sample vs production",
    "product_weight": "Product weight", "measurement": "Measurement", "labels": "Labels",
    "bulk_images": "Bulk images", "defects": "Defects",
}
NAVY = colors.HexColor("#0b2545")
BLUE = colors.HexColor("#2563eb")
AMBER = colors.HexColor("#b45309")
RED = colors.HexColor("#b91c1c")
GREY = colors.HexColor("#64748b")


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("H1x", parent=ss["Heading1"], textColor=NAVY, fontSize=18, spaceAfter=4))
    ss.add(ParagraphStyle("H2x", parent=ss["Heading2"], textColor=BLUE, fontSize=12, spaceBefore=10, spaceAfter=4))
    ss.add(ParagraphStyle("Small", parent=ss["Normal"], fontSize=8, textColor=GREY))
    ss.add(ParagraphStyle("Body", parent=ss["Normal"], fontSize=9, leading=12))
    ss.add(ParagraphStyle("Amber", parent=ss["Normal"], fontSize=9, leading=12, textColor=AMBER))
    return ss


def _thumb(raw: bytes, max_w: int, max_h: int):
    try:
        img = PILImage.open(io.BytesIO(raw)).convert("RGB")
        img.thumbnail((max_w * 4, max_h * 4))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        buf.seek(0)
        w, h = img.size
        ratio = min(max_w / w, max_h / h)
        return RLImage(buf, width=w * ratio, height=h * ratio)
    except Exception as e:
        logger.error(f"pdf thumb failed: {e}")
        return None


def _crop(raw: bytes, bbox: dict) -> bytes:
    img = PILImage.open(io.BytesIO(raw)).convert("RGB")
    W, H = img.size
    try:
        x, y = float(bbox.get("x", 0)), float(bbox.get("y", 0))
        w, h = float(bbox.get("w", 1)), float(bbox.get("h", 1))
    except (TypeError, ValueError):
        x, y, w, h = 0, 0, 1, 1
    pad = 0.06
    l, t = int(max(0, x - pad) * W), int(max(0, y - pad) * H)
    r, b = int(min(1, x + w + pad) * W), int(min(1, y + h + pad) * H)
    if r - l < 20 or b - t < 20:
        l, t, r, b = 0, 0, W, H
    out = io.BytesIO()
    img.crop((l, t, r, b)).save(out, format="JPEG", quality=85)
    return out.getvalue()


def _product_flowables(p, i, ss):
    e = []
    name = p.get("sheet_name") or (p.get("sku") if p.get("sku_readable") else f"Product {i}")
    conf = p.get("confidence") or {}
    e.append(Paragraph(f"{name}", ss["H2x"]))
    if p.get("description"):
        e.append(Paragraph(p["description"], ss["Body"]))

    tally = p.get("severity_tally") or {"critical": 0, "major": 0, "minor": 0}
    stat_rows = [[
        Paragraph("<b>Distinct designs</b><br/>%s" % (p.get("distinct_design_count", 1)), ss["Body"]),
        Paragraph("<b>Visible units</b><br/>%s" % (p.get("visible_unit_count", 0)), ss["Body"]),
        Paragraph("<b>Photos</b><br/>%s" % (p.get("photo_count", len(p.get("photos", [])))), ss["Body"]),
        Paragraph("<b>Defects</b><br/>C %s / M %s / m %s" % (
            tally.get("critical", 0), tally.get("major", 0), tally.get("minor", 0)), ss["Body"]),
        Paragraph("<b>Confidence</b><br/>%s" % (conf.get("overall", "n/a")), ss["Body"]),
    ]]
    st = Table(stat_rows, colWidths=[35 * mm] * 5)
    st.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    e.append(st)
    e.append(Spacer(1, 6))

    et = p.get("extracted_text") or {}
    rows = [["SKU", p.get("sku") or et.get("sku") or "Not readable"],
            ["Model", et.get("model") or "-"], ["Barcode", et.get("barcode") or "-"],
            ["Quantities", et.get("quantities") or "-"], ["Markings", et.get("markings") or "-"]]
    tt = Table([[Paragraph("<b>%s</b>" % k, ss["Body"]), Paragraph(str(v), ss["Body"])] for k, v in rows],
               colWidths=[30 * mm, 150 * mm])
    tt.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#eef2f7")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    e.append(tt)

    bc = p.get("barcode_check") or {}
    if bc:
        style = {"match": ss["Body"], "mismatch": ss["Amber"], "not_available": ss["Small"]}.get(
            bc.get("status"), ss["Small"])
        tag = {"match": "Barcode ✓", "mismatch": "Barcode ✗ MISMATCH", "not_available": "Barcode —"}.get(
            bc.get("status"), "Barcode")
        e.append(Paragraph(f"<b>{tag}:</b> {bc.get('note', '')}", style))

    mw = []
    for m in p.get("measurements", []):
        mw.append(f"Measurement: {m.get('value','')} {m.get('unit','')} (conf: {m.get('confidence','n/a')})")
    for w in p.get("weights", []):
        mw.append(f"Weight: {w.get('value','')} {w.get('unit','')} (conf: {w.get('confidence','n/a')})")
    if mw:
        e.append(Spacer(1, 4))
        e.append(Paragraph("<br/>".join(mw), ss["Body"]))

    e.append(Paragraph("Defects", ss["H2x"]))
    defects = p.get("defects", [])
    if not defects:
        e.append(Paragraph("No visible defects identified in supplied photos. "
                           "This is not a pass/fail determination.", ss["Amber"]))
    else:
        bytes_by_idx = {it["photo"]: it["bytes"] for it in p.get("photo_items", [])}
        for d in defects:
            crop_img = None
            ph = d.get("photo")
            if ph in bytes_by_idx and d.get("bbox"):
                try:
                    crop_img = _thumb(_crop(bytes_by_idx[ph], d["bbox"]), 32, 26)
                except Exception:
                    crop_img = None
            txt = Paragraph(
                f"<b>{(d.get('severity') or 'minor').upper()}</b> — {d.get('description','')}"
                f"<br/><font size=8 color='#64748b'>Location: {d.get('location') or 'Not visible'} · "
                f"confidence: {d.get('confidence','n/a')}</font>", ss["Body"])
            row = [[crop_img or Paragraph("-", ss["Small"]), txt]]
            dt = Table(row, colWidths=[36 * mm, 144 * mm])
            dt.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
            e.append(dt)

    unresolved = p.get("unresolved") or []
    if unresolved:
        e.append(Paragraph("Deliberately unresolved — cannot be proven from photos", ss["H2x"]))
        for u in unresolved:
            e.append(Paragraph("• " + u, ss["Amber"]))

    photos = p.get("photos", [])
    pbytes = {it["photo"]: it["bytes"] for it in p.get("photo_items", [])}
    cells, row = [], []
    for ph in photos:
        img = _thumb(pbytes.get(ph.get("photo"), b""), 40, 32) if ph.get("photo") in pbytes else None
        if img:
            cap = Paragraph(f"<font size=7>{CATEGORY_LABEL.get(ph.get('category'), ph.get('category',''))}<br/>"
                            f"{ph.get('filename','')}</font>", ss["Small"])
            row.append([img, cap])
            if len(row) == 4:
                cells.append(row); row = []
    if row:
        while len(row) < 4:
            row.append([Paragraph("", ss["Small"])])
        cells.append(row)
    if cells:
        e.append(Paragraph("Traceable photos", ss["H2x"]))
        flat = []
        for r in cells:
            inner = [Table([[c[0]], [c[1]]] if len(c) == 2 else [[c[0]]], colWidths=[42 * mm]) for c in r]
            flat.append(inner)
        gt = Table(flat, colWidths=[45 * mm] * 4)
        gt.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
        e.append(gt)

    e.append(HRFlowable(width="100%", color=colors.HexColor("#e2e8f0"), spaceBefore=8, spaceAfter=8))
    return e


def _rollup_table(rollup, ss):
    data = [["", "Critical", "Major", "Minor"],
            ["Defects found", rollup.get("critical", 0), rollup.get("major", 0), rollup.get("minor", 0)],
            ["AQL limit", "0", "2.5", "4"]]
    t = Table(data, colWidths=[40 * mm, 30 * mm, 30 * mm, 30 * mm])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b2545")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("TEXTCOLOR", (1, 1), (1, 1), RED), ("TEXTCOLOR", (2, 1), (2, 1), AMBER),
        ("FONTSIZE", (0, 0), (-1, -1), 9), ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ]))
    return t


def generate_pdf(products: list[dict], meta: dict) -> bytes:
    ss = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=16 * mm, bottomMargin=14 * mm,
                            leftMargin=14 * mm, rightMargin=14 * mm,
                            title=f"Inspection Report {meta.get('id', '')[:8]}")
    e = []
    e.append(Paragraph("INDIGO SOURCING — Inspection Report (summary)", ss["H1x"]))
    e.append(Paragraph(
        f"Batch #{meta.get('id', '')[:8]} &nbsp;·&nbsp; {meta.get('photo_count', 0)} photos "
        f"&nbsp;·&nbsp; {len(products)} product sheet(s)", ss["Small"]))
    e.append(Paragraph(
        "This PDF is a shareable summary generated alongside the formatted Excel workbook. "
        "Visible unit counts reflect only what is visible in photos and do NOT represent total "
        "quantities inside closed cartons.", ss["Amber"]))
    rollup = meta.get("severity_rollup")
    if rollup:
        e.append(Spacer(1, 4))
        e.append(Paragraph("Batch defect rollup vs AQL", ss["H2x"]))
        e.append(_rollup_table(rollup, ss))
        e.append(Paragraph("Max allowed defects depend on lot size and are not determinable from photos.",
                           ss["Small"]))
    e.append(HRFlowable(width="100%", color=colors.HexColor("#e2e8f0"), spaceBefore=6, spaceAfter=6))

    for i, p in enumerate(products, 1):
        e.extend(_product_flowables(p, i, ss))

    doc.build(e)
    buf.seek(0)
    return buf.getvalue()


def generate_review_pack(sections: list[dict]) -> bytes:
    """sections: list of {meta:{id,created_at,photo_count,severity_rollup}, products:[...]}"""
    ss = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=16 * mm, bottomMargin=14 * mm,
                            leftMargin=14 * mm, rightMargin=14 * mm, title="Supplier Review Pack")
    e = []
    e.append(Paragraph("INDIGO SOURCING — Supplier Review Pack", ss["H1x"]))
    e.append(Paragraph(f"{len(sections)} inspection(s) combined for review.", ss["Small"]))
    tot = {"critical": 0, "major": 0, "minor": 0}
    for s in sections:
        r = s["meta"].get("severity_rollup") or {}
        for k in tot:
            tot[k] += r.get(k, 0)
    e.append(Spacer(1, 4))
    e.append(Paragraph("Combined defect rollup vs AQL", ss["H2x"]))
    e.append(_rollup_table(tot, ss))
    e.append(HRFlowable(width="100%", color=colors.HexColor("#e2e8f0"), spaceBefore=6, spaceAfter=6))

    for s in sections:
        m = s["meta"]
        e.append(Paragraph(f"Inspection #{m.get('id','')[:8]} — {m.get('created_at','')[:10]} "
                           f"· {m.get('photo_count',0)} photos · {len(s['products'])} product(s)", ss["H1x"]))
        for i, p in enumerate(s["products"], 1):
            e.extend(_product_flowables(p, i, ss))

    doc.build(e)
    buf.seek(0)
    return buf.getvalue()
