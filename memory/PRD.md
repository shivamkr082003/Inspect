# InspectAI — Buying House Automated Inspection Report Generator

## Original Problem Statement
Build a web app that automatically creates buying-house inspection reports from photos. The user only
uploads a batch of product & packaging photos and presses "Generate report" — no manual entry of product
name, SKU, quantity, category, or result. The app identifies distinct products, groups photos of the same
product, counts visible units (never claiming it equals total carton quantity), reads legible label/SKU/
barcode/measurement text, describes defects, and fills a FIXED Excel inspection-report template
("PO# 0251 frames.xlsx") — one sheet per product — preserving its exact format (merged cells, formulas,
row heights, column widths, page breaks, print settings, repeated photo sections). Photos are embedded,
sized and positioned in the existing "Inspection Digitals" slots. Values that cannot be proven from photos
are deliberately left unresolved ("Not visible"). Original photos are stored for traceability.

## User Choices
- Vision model: OpenAI GPT 5.5 (via Emergent Universal LLM key)
- Auth: simple team login (JWT, Bearer token)
- Photo storage: Emergent Object Storage

## Architecture
- Frontend: React (CRA + craco), Tailwind + shadcn/ui, dark "tactical QC" theme. Pages: Login, Dashboard
  (upload → live processing pipeline → results workbench with per-product tabs → history sidebar), ProductResults.
- Backend: FastAPI. Modules: server.py (routes + background processing), auth.py (JWT/bcrypt), storage.py
  (Emergent Object Storage with 5xx retry + stale-key reinit), vision.py (GPT-5.5 multi-image analysis →
  strict JSON), report.py (openpyxl template cloning + photo embedding).
- DB: MongoDB (users, inspections). Photos + generated .xlsx stored in Object Storage; references in Mongo.
- Template engine: template_clean.xlsx (example images/data stripped from the master "PO# 0251 frames.xlsx").
  For each product, copy_worksheet is used (preserves 315 merges, formulas, widths/heights, page scale 62);
  row page-breaks are re-applied; photos embedded via TwoCellAnchor into the 6 repeating INSPECTION DIGITALS
  sections (12 slots each); findings/traceability written into SKU cells, defects table, SPECIAL COMMENTS and
  SPECIAL REMARKS areas.

## Personas
- Lead/QC inspector at a buying house who needs audit-ready Excel reports from phone photos without data entry.

## Core Requirements (static)
- One .xlsx per batch; one sheet per distinct product/design; exact template fidelity; embedded correctly
  placed photos; no example data/photo carryover; truthful unresolved handling; photo traceability.

## Implemented (2026-06)
- JWT team auth (seeded admin inspector@indigo.com / inspect123).
- Multi-photo batch upload → Object Storage; original filename + timestamp + per-photo records retained.
- Async background pipeline with status/progress (queued → analyzing → generating → done/error).
- GPT-5.5 vision: product identification, cross-photo grouping, visible-unit counting, OCR of SKU/label/
  barcode/measurements/weights, defect detection, grouping-uncertainty flag, explicit unresolved list.
- Excel generation preserving template format; per-product sheets named by SKU or "Product N"; photos
  embedded into Inspection Digitals slots; defects reference supporting photo; comments/remarks carry
  traceability + deliberately-unresolved statements.
- Download .xlsx; original-photo serving endpoint; inspection history.
- Verified end-to-end with the template's own 17 photos (testing agent: backend 9/9, frontend flows 100%).

## Backlog / Remaining (prioritized)
- P1: Allow re-running/editing a product grouping if the inspector disagrees with AI split.
- P2: Batch LLM analysis for very large uploads (currently all photos in one request / loaded in memory).
- P2: Per-user team management UI (currently single seeded admin + register endpoint).
- P2: Thumbnail caching and lazy-loading in the photo gallery.

## Next Tasks
- Gather real inspector feedback on sheet-field placement vs. their Excel expectations and tune _fill_values mapping.
