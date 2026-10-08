import React, { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { Badge } from "../components/ui/badge";
import { Columns2, AlertTriangle, Hash, Boxes, EyeOff } from "lucide-react";
import { buildAuthedUrl } from "../lib/api";

const SEV_COLOR = {
  critical: "bg-red-500/15 text-red-400 border-red-500/30",
  major: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  minor: "bg-sky-500/15 text-sky-400 border-sky-500/30",
};

function ProductColumn({ product, inspection }) {
  if (!product) {
    return <div className="text-sm text-slate-500 p-4">Select a product</div>;
  }
  const photoUrl = (idx) => {
    const p = (inspection.photos || [])[idx - 1];
    return p ? buildAuthedUrl(`/inspections/${inspection.id}/photos/${p.id}`) : null;
  };
  const t = product.severity_tally || { critical: 0, major: 0, minor: 0 };
  const et = product.extracted_text || {};
  return (
    <div className="space-y-4" data-testid={`compare-col-${product.sheet_name}`}>
      <div className="flex items-center gap-2 flex-wrap">
        <h4 className="font-display text-lg font-semibold">{product.sheet_name}</h4>
        {product.sku_readable ? (
          <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30 font-mono-data">
            {product.sku}
          </Badge>
        ) : (
          <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/30">
            <EyeOff className="h-3 w-3 mr-1" /> no SKU
          </Badge>
        )}
      </div>
      {product.description && <p className="text-sm text-slate-400">{product.description}</p>}

      <div className="grid grid-cols-3 gap-2">
        <div className="rounded-lg border border-white/10 bg-slate-900/40 p-2 text-center">
          <Boxes className="h-3.5 w-3.5 mx-auto text-slate-400" />
          <div className="font-mono-data text-lg">{product.distinct_design_count ?? 1}</div>
          <div className="text-[10px] text-slate-500">designs</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-slate-900/40 p-2 text-center">
          <Hash className="h-3.5 w-3.5 mx-auto text-cyan-400" />
          <div className="font-mono-data text-lg text-cyan-400">{product.visible_unit_count ?? 0}</div>
          <div className="text-[10px] text-slate-500">visible</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-slate-900/40 p-2 text-center">
          <AlertTriangle className="h-3.5 w-3.5 mx-auto text-red-400" />
          <div className="font-mono-data text-lg">{(product.defects || []).length}</div>
          <div className="text-[10px] text-slate-500">defects</div>
        </div>
      </div>

      <div className="flex gap-2">
        <Badge className={SEV_COLOR.critical}>Crit {t.critical}</Badge>
        <Badge className={SEV_COLOR.major}>Maj {t.major}</Badge>
        <Badge className={SEV_COLOR.minor}>Min {t.minor}</Badge>
      </div>

      <div className="text-sm space-y-1">
        <div className="flex justify-between border-b border-white/5 py-1">
          <span className="text-slate-400">Barcode</span>
          <span className="font-mono-data text-slate-200">{et.barcode || "—"}</span>
        </div>
        <div className="flex justify-between border-b border-white/5 py-1">
          <span className="text-slate-400">Barcode check</span>
          <span className={product.barcode_check?.status === "mismatch" ? "text-red-400" : "text-slate-200"}>
            {product.barcode_check?.status || "n/a"}
          </span>
        </div>
      </div>

      {(product.defects || []).length > 0 && (
        <div className="space-y-1">
          {product.defects.map((d, i) => (
            <div key={i} className="text-xs text-slate-300 border-b border-white/5 py-1">
              <span className="uppercase text-slate-500">{d.severity}</span> — {d.description}
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-3 gap-1.5">
        {(product.photos || []).slice(0, 9).map((ph, i) => {
          const url = photoUrl(ph.photo);
          return url ? (
            <img key={i} src={url} alt={ph.filename} className="aspect-square object-cover rounded border border-white/10" />
          ) : null;
        })}
      </div>
    </div>
  );
}

export default function CompareDialog({ open, onClose, inspection }) {
  const products = inspection.products || [];
  const [a, setA] = useState(0);
  const [b, setB] = useState(products.length > 1 ? 1 : 0);

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-5xl bg-[#0b0f17] border-white/10" data-testid="compare-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display">
            <Columns2 className="h-5 w-5 text-blue-400" /> Side-by-side compare
          </DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-6">
          {[{ v: a, set: setA, key: "a" }, { v: b, set: setB, key: "b" }].map((sel) => (
            <div key={sel.key}>
              <select
                value={sel.v}
                onChange={(e) => sel.set(Number(e.target.value))}
                className="w-full mb-3 bg-slate-800 text-sm text-slate-200 border border-white/10 rounded-lg py-2 px-2 outline-none"
                data-testid={`compare-select-${sel.key}`}
              >
                {products.map((p, i) => (
                  <option key={i} value={i}>
                    {p.sheet_name}
                  </option>
                ))}
              </select>
              <ProductColumn product={products[sel.v]} inspection={inspection} />
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
