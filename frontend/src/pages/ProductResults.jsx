import React, { useState } from "react";
import { Badge } from "../components/ui/badge";
import { Dialog, DialogContent, DialogTitle } from "../components/ui/dialog";
import {
  Boxes,
  Hash,
  AlertTriangle,
  Ruler,
  Scale,
  Tag,
  ScanBarcode,
  TriangleAlert,
  EyeOff,
  Images,
  Gauge,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { buildAuthedUrl } from "../lib/api";

const CATEGORY_LABEL = {
  packed_cartons: "Packed cartons",
  selected_cartons: "Selected cartons",
  product_packaging: "Product packaging",
  sample_vs_production: "Sample vs production",
  product_weight: "Product weight",
  measurement: "Measurement",
  labels: "Labels",
  bulk_images: "Bulk images",
  defects: "Defects",
};

const SEV_COLOR = {
  critical: "bg-red-500/15 text-red-400 border-red-500/30",
  major: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  minor: "bg-sky-500/15 text-sky-400 border-sky-500/30",
};

const CONF_COLOR = {
  high: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  medium: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  low: "bg-red-500/15 text-red-400 border-red-500/30",
  manual: "bg-blue-500/15 text-blue-300 border-blue-500/30",
};

function ConfidenceBadge({ label, value }) {
  if (!value) return null;
  const cls = CONF_COLOR[String(value).toLowerCase()] || "bg-slate-700 text-slate-300 border-white/10";
  const testId = label ? `confidence-${label}` : "confidence-value";
  return (
    <Badge className={`${cls} text-[10px] font-mono-data`} data-testid={testId}>
      <Gauge className="h-3 w-3 mr-1" />
      {label ? `${label}: ${value}` : value}
    </Badge>
  );
}

function DefectCrop({ url, bbox }) {
  // CSS-crop the source photo to the normalized bbox for a pinned close-up
  if (!bbox || (bbox.w <= 0 && bbox.h <= 0)) {
    return <img src={url} alt="defect" className="h-full w-full object-cover" />;
  }
  const zoom = Math.min(1 / Math.max(bbox.w || 1, 0.08), 1 / Math.max(bbox.h || 1, 0.08), 6);
  const posX = (bbox.w >= 0.98 ? 0.5 : (bbox.x + bbox.w / 2)) * 100;
  const posY = (bbox.h >= 0.98 ? 0.5 : (bbox.y + bbox.h / 2)) * 100;
  return (
    <div
      className="h-full w-full"
      style={{
        backgroundImage: `url(${url})`,
        backgroundRepeat: "no-repeat",
        backgroundSize: `${zoom * 100}% ${zoom * 100}%`,
        backgroundPosition: `${posX}% ${posY}%`,
      }}
    />
  );
}

function BarcodeBadge({ check }) {
  if (!check || !check.status) return null;
  if (check.status === "match") {
    return (
      <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30 text-[10px]" data-testid="barcode-check" title={check.note}>
        <CheckCircle2 className="h-3 w-3 mr-1" /> barcode ✓
      </Badge>
    );
  }
  if (check.status === "mismatch") {
    return (
      <Badge className="bg-red-500/15 text-red-400 border-red-500/30 text-[10px]" data-testid="barcode-check" title={check.note}>
        <XCircle className="h-3 w-3 mr-1" /> barcode ✗ mismatch
      </Badge>
    );
  }
  return (
    <Badge className="bg-slate-700 text-slate-300 border-white/10 text-[10px]" data-testid="barcode-check" title={check.note}>
      <ScanBarcode className="h-3 w-3 mr-1" /> barcode n/a
    </Badge>
  );
}

function Stat({ icon: Icon, label, value, accent }) {
  return (
    <div className="rounded-xl border border-white/10 bg-slate-900/40 p-4">
      <div className="flex items-center gap-2 text-slate-400 text-xs uppercase tracking-wide">
        <Icon className="h-3.5 w-3.5" /> {label}
      </div>
      <div className={`mt-1.5 font-mono-data text-2xl font-semibold ${accent || "text-slate-100"}`}>
        {value}
      </div>
    </div>
  );
}

export default function ProductResults({ product, inspection }) {
  const [lightbox, setLightbox] = useState(null);
  const et = product.extracted_text || {};
  const conf = product.confidence || {};

  const photoIdByIndex = (idx) => {
    const p = (inspection.photos || [])[idx - 1];
    return p ? p.id : null;
  };
  const photoUrlByIndex = (idx) => {
    const pid = photoIdByIndex(idx);
    return pid ? buildAuthedUrl(`/inspections/${inspection.id}/photos/${pid}`) : null;
  };

  const extractedRows = [
    ["SKU", product.sku || et.sku],
    ["Model", et.model],
    ["Barcode", et.barcode],
    ["Quantities", et.quantities],
    ["Markings", et.markings],
  ].filter(([, v]) => v);

  return (
    <div className="space-y-6" data-testid={`product-results-${product.sheet_name}`}>
      {/* header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <h3 className="font-display text-xl font-semibold">{product.sheet_name}</h3>
            {product.sku_readable ? (
              <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30 font-mono-data">
                SKU {product.sku}
              </Badge>
            ) : (
              <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/30">
                <EyeOff className="h-3 w-3 mr-1" /> SKU not readable
              </Badge>
            )}
            {product.grouping_uncertain && (
              <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/30">
                <TriangleAlert className="h-3 w-3 mr-1" /> Grouping uncertain
              </Badge>
            )}
          </div>
          {product.description && (
            <p className="text-sm text-slate-400 mt-1 max-w-2xl">{product.description}</p>
          )}
          {/* confidence badges */}
          <div className="flex flex-wrap gap-2 mt-3">
            <ConfidenceBadge label="overall" value={conf.overall} />
            <ConfidenceBadge label="sku" value={conf.sku} />
            <ConfidenceBadge label="units" value={conf.visible_unit_count} />
            <ConfidenceBadge label="grouping" value={conf.grouping} />
            <BarcodeBadge check={product.barcode_check} />
          </div>
        </div>
      </div>

      {/* stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat icon={Boxes} label="Distinct designs" value={product.distinct_design_count ?? 1} />
        <Stat
          icon={Hash}
          label="Visible units"
          value={product.visible_unit_count ?? 0}
          accent="text-cyan-400"
        />
        <Stat icon={Images} label="Photos" value={product.photo_count ?? 0} />
        <Stat
          icon={AlertTriangle}
          label="Defects found"
          value={(product.defects || []).length}
          accent={(product.defects || []).length ? "text-red-400" : "text-emerald-400"}
        />
      </div>

      <p className="text-xs text-amber-400/90 flex items-center gap-1.5">
        <TriangleAlert className="h-3.5 w-3.5" />
        Visible unit count reflects only what is visible in photos — it does not represent the total
        quantity inside closed cartons.
      </p>

      {/* extracted text */}
      {(extractedRows.length > 0 || (et.labels || []).length > 0) && (
        <div className="rounded-xl border border-white/10 bg-slate-900/40 p-5">
          <div className="flex items-center gap-2 text-sm font-medium text-slate-200 mb-3">
            <ScanBarcode className="h-4 w-4 text-blue-400" /> Extracted text (OCR)
          </div>
          <div className="grid sm:grid-cols-2 gap-x-8 gap-y-2">
            {extractedRows.map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4 text-sm border-b border-white/5 py-1">
                <span className="text-slate-400">{k}</span>
                <span className="font-mono-data text-slate-100 text-right break-all">{v}</span>
              </div>
            ))}
          </div>
          {(et.labels || []).length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {et.labels.map((l, i) => (
                <span key={i} className="text-xs font-mono-data bg-slate-800 border border-white/10 rounded px-2 py-1 text-slate-300">
                  <Tag className="h-3 w-3 inline mr-1" />
                  {l}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* measurements & weights */}
      {((product.measurements || []).length > 0 || (product.weights || []).length > 0) && (
        <div className="grid sm:grid-cols-2 gap-3">
          {(product.measurements || []).length > 0 && (
            <div className="rounded-xl border border-white/10 bg-slate-900/40 p-5">
              <div className="flex items-center gap-2 text-sm font-medium mb-2">
                <Ruler className="h-4 w-4 text-blue-400" /> Measurements
              </div>
              {product.measurements.map((m, i) => (
                <div key={i} className="font-mono-data text-sm text-slate-200 flex items-center gap-2">
                  {m.value} {m.unit}
                  {m.confidence && <ConfidenceBadge label="" value={m.confidence} />}
                </div>
              ))}
            </div>
          )}
          {(product.weights || []).length > 0 && (
            <div className="rounded-xl border border-white/10 bg-slate-900/40 p-5">
              <div className="flex items-center gap-2 text-sm font-medium mb-2">
                <Scale className="h-4 w-4 text-blue-400" /> Weights
              </div>
              {product.weights.map((w, i) => (
                <div key={i} className="font-mono-data text-sm text-slate-200 flex items-center gap-2">
                  {w.value} {w.unit}
                  {w.confidence && <ConfidenceBadge label="" value={w.confidence} />}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* defects — Defect Spotlight with cropped close-ups */}
      <div className="rounded-xl border border-white/10 bg-slate-900/40 p-5">
        <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
          <div className="flex items-center gap-2 text-sm font-medium text-slate-200">
            <AlertTriangle className="h-4 w-4 text-red-400" /> Defects
          </div>
          {/* severity rollup vs AQL */}
          {(() => {
            const t = product.severity_tally || { critical: 0, major: 0, minor: 0 };
            return (
              <div className="flex items-center gap-1.5 text-[11px] font-mono-data" data-testid="severity-rollup">
                <span className="text-slate-500">vs AQL:</span>
                <Badge className="bg-red-500/15 text-red-400 border-red-500/30">Crit {t.critical}/0</Badge>
                <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/30">Maj {t.major}/2.5</Badge>
                <Badge className="bg-sky-500/15 text-sky-400 border-sky-500/30">Min {t.minor}/4</Badge>
              </div>
            );
          })()}
        </div>
        {product.barcode_check?.status === "mismatch" && (
          <p className="text-xs text-red-400 mb-3 flex items-center gap-1.5">
            <XCircle className="h-3.5 w-3.5" /> {product.barcode_check.note}
          </p>
        )}
        {(product.defects || []).length === 0 ? (
          <p className="text-sm text-slate-400">
            No visible defects identified in supplied photos.{" "}
            <span className="text-amber-400">This is not a pass/fail determination.</span>
          </p>
        ) : (
          <div className="space-y-3">
            {product.defects.map((d, i) => {
              const url = photoUrlByIndex(d.photo);
              return (
                <div key={i} className="flex items-start gap-3 border-b border-white/5 pb-3" data-testid={`defect-row-${i}`}>
                  {url && (
                    <button
                      onClick={() => setLightbox({ url, cat: "defects", name: `Defect on photo ${d.photo}`, bbox: d.bbox })}
                      className="relative h-16 w-16 shrink-0 rounded-lg overflow-hidden border border-red-500/40 bg-slate-900"
                      data-testid={`defect-spotlight-${i}`}
                      title="Defect close-up"
                    >
                      <DefectCrop url={url} bbox={d.bbox} />
                    </button>
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge className={`${SEV_COLOR[(d.severity || "minor").toLowerCase()]} capitalize`}>
                        {d.severity || "minor"}
                      </Badge>
                      {d.confidence && <ConfidenceBadge label="" value={d.confidence} />}
                    </div>
                    <p className="text-sm text-slate-100 mt-1">{d.description}</p>
                    {d.location && <p className="text-xs text-slate-500">Location: {d.location}</p>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* unresolved */}
      {(product.unresolved || []).length > 0 && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-5">
          <div className="flex items-center gap-2 text-sm font-medium text-amber-400 mb-2">
            <EyeOff className="h-4 w-4" /> Deliberately unresolved — cannot be proven from photos
          </div>
          <ul className="space-y-1.5">
            {product.unresolved.map((u, i) => (
              <li key={i} className="text-sm text-amber-200/80 flex gap-2">
                <span className="text-amber-500 mt-1">•</span>
                {u}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* photo gallery with traceability */}
      <div>
        <div className="flex items-center gap-2 text-sm font-medium text-slate-200 mb-3">
          <Images className="h-4 w-4 text-blue-400" /> Traceable photos ({(product.photos || []).length})
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {(product.photos || []).map((ph, i) => {
            const url = photoUrlByIndex(ph.photo);
            if (!url) return null;
            return (
              <button
                key={i}
                onClick={() => setLightbox({ url, cat: ph.category, name: ph.filename })}
                className="group relative rounded-lg overflow-hidden border border-white/10 bg-slate-900 aspect-square"
                data-testid={`product-photo-${ph.photo}`}
              >
                <img src={url} alt={ph.filename} className="h-full w-full object-cover transition group-hover:scale-105" />
                <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 to-transparent p-2">
                  <span className="text-[10px] font-medium text-white block truncate">
                    {CATEGORY_LABEL[ph.category] || ph.category}
                  </span>
                  <span className="text-[9px] text-slate-300 font-mono-data block truncate">{ph.filename}</span>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <Dialog open={!!lightbox} onOpenChange={(o) => !o && setLightbox(null)}>
        <DialogContent className="max-w-3xl bg-[#0b0f17] border-white/10">
          {lightbox && (
            <div className="space-y-3">
              <DialogTitle className="sr-only">{lightbox.name || "Photo preview"}</DialogTitle>
              <img src={lightbox.url} alt={lightbox.name} className="w-full max-h-[70vh] object-contain rounded-lg" />
              <div className="flex items-center justify-between text-sm">
                <Badge className="bg-blue-500/15 text-blue-300 border-blue-500/30">
                  {CATEGORY_LABEL[lightbox.cat] || lightbox.cat}
                </Badge>
                <span className="font-mono-data text-slate-400">{lightbox.name}</span>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
