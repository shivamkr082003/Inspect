import React, { useMemo, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";
import { ScrollArea } from "../components/ui/scroll-area";
import { Plus, Trash2, Loader2, Split, Save } from "lucide-react";
import { toast } from "sonner";
import api, { buildAuthedUrl } from "../lib/api";

const PALETTE = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#a855f7", "#06b6d4", "#ec4899", "#84cc16"];

export default function RegroupDialog({ open, onClose, inspection, onRegrouped }) {
  const photos = useMemo(() => inspection.photos || [], [inspection]);
  const initial = useMemo(() => {
    const groups = (inspection.products || []).map((p, i) => ({
      key: `g${i}`,
      name: p.sheet_name || `Product ${i + 1}`,
      sku: p.sku || "",
      indices: (p.photos || []).map((ph) => ph.photo),
    }));
    return groups.length ? groups : [{ key: "g0", name: "Product 1", sku: "", indices: photos.map((_, i) => i + 1) }];
  }, [inspection, photos]);

  const [groups, setGroups] = useState(initial);
  const [saving, setSaving] = useState(false);

  const groupOfIndex = (idx) => groups.findIndex((g) => g.indices.includes(idx));

  const assign = (idx, groupKey) => {
    setGroups((prev) =>
      prev.map((g) => {
        const indices = g.indices.filter((x) => x !== idx);
        if (g.key === groupKey) indices.push(idx);
        return { ...g, indices: indices.sort((a, b) => a - b) };
      })
    );
  };

  const addGroup = () => {
    setGroups((prev) => [...prev, { key: `g${Date.now()}`, name: `Product ${prev.length + 1}`, sku: "", indices: [] }]);
  };

  const removeGroup = (key) => {
    setGroups((prev) => {
      if (prev.length === 1) return prev;
      const victim = prev.find((g) => g.key === key);
      const rest = prev.filter((g) => g.key !== key);
      // move its photos to the first remaining group
      rest[0] = { ...rest[0], indices: [...rest[0].indices, ...victim.indices].sort((a, b) => a - b) };
      return rest;
    });
  };

  const updateGroup = (key, field, value) => {
    setGroups((prev) => prev.map((g) => (g.key === key ? { ...g, [field]: value } : g)));
  };

  const submit = async () => {
    const payload = {
      groups: groups
        .filter((g) => g.indices.length > 0)
        .map((g) => ({
          name: g.name,
          sku: g.sku.trim() || null,
          sku_readable: !!g.sku.trim(),
          photo_indices: g.indices,
        })),
    };
    if (!payload.groups.length) {
      toast.error("Every group is empty");
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.post(`/inspections/${inspection.id}/regroup`, payload);
      toast.success("Regrouping — regenerating Excel & PDF");
      onRegrouped(data);
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Regroup failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-5xl bg-[#0b0f17] border-white/10" data-testid="regroup-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display">
            <Split className="h-5 w-5 text-blue-400" /> Manual regroup
          </DialogTitle>
        </DialogHeader>
        <p className="text-sm text-slate-400 -mt-2">
          Reassign photos, rename products, or create / merge groups. Each photo belongs to exactly one
          product. Regenerating rebuilds the Excel &amp; PDF with your grouping.
        </p>

        {/* group editors */}
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {groups.map((g, gi) => (
            <div key={g.key} className="rounded-lg border border-white/10 bg-slate-900/50 p-3 space-y-2">
              <div className="flex items-center gap-2">
                <span className="h-3 w-3 rounded-full shrink-0" style={{ background: PALETTE[gi % PALETTE.length] }} />
                <Input
                  value={g.name}
                  onChange={(e) => updateGroup(g.key, "name", e.target.value)}
                  className="h-8 bg-slate-800 border-white/10 text-sm"
                  placeholder="Product name"
                  data-testid={`regroup-name-${gi}`}
                />
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0"
                  onClick={() => removeGroup(g.key)}
                  data-testid={`regroup-remove-${gi}`}
                >
                  <Trash2 className="h-4 w-4 text-red-400" />
                </Button>
              </div>
              <Input
                value={g.sku}
                onChange={(e) => updateGroup(g.key, "sku", e.target.value)}
                className="h-8 bg-slate-800 border-white/10 text-sm font-mono-data"
                placeholder="SKU (optional)"
                data-testid={`regroup-sku-${gi}`}
              />
              <Badge className="bg-slate-800 text-slate-300 border-white/10 text-[10px]">
                {g.indices.length} photo(s)
              </Badge>
            </div>
          ))}
          <button
            onClick={addGroup}
            data-testid="regroup-add-group"
            className="rounded-lg border border-dashed border-white/15 bg-slate-900/30 p-3 flex items-center justify-center text-slate-400 hover:border-white/30 min-h-[96px]"
          >
            <Plus className="h-4 w-4 mr-1" /> Add product
          </button>
        </div>

        {/* photo assignment grid */}
        <ScrollArea className="h-[40vh] mt-1 pr-2">
          <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-2">
            {photos.map((p, i) => {
              const idx = i + 1;
              const gi = groupOfIndex(idx);
              const color = gi >= 0 ? PALETTE[gi % PALETTE.length] : "#334155";
              const url = buildAuthedUrl(`/inspections/${inspection.id}/photos/${p.id}`);
              return (
                <div
                  key={p.id}
                  className="rounded-lg overflow-hidden border-2"
                  style={{ borderColor: color }}
                  data-testid={`regroup-photo-${idx}`}
                >
                  <img src={url} alt={p.original_filename} className="h-20 w-full object-cover" />
                  <select
                    value={gi >= 0 ? groups[gi].key : ""}
                    onChange={(e) => assign(idx, e.target.value)}
                    className="w-full bg-slate-800 text-[11px] text-slate-200 border-0 py-1 px-1 outline-none"
                    data-testid={`regroup-select-${idx}`}
                  >
                    {groups.map((g, k) => (
                      <option key={g.key} value={g.key}>
                        {g.name}
                      </option>
                    ))}
                  </select>
                </div>
              );
            })}
          </div>
        </ScrollArea>

        <div className="flex justify-end gap-2 pt-2 border-t border-white/10">
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button
            onClick={submit}
            disabled={saving}
            className="bg-blue-500 hover:bg-blue-600 text-white"
            data-testid="regroup-regenerate-button"
          >
            {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
            Regenerate report
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
