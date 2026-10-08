import React, { useEffect, useRef, useState, useCallback } from "react";
import { useAuth } from "../context/AuthContext";
import api, { buildAuthedUrl } from "../lib/api";
import ProductResults from "./ProductResults";
import RegroupDialog from "./RegroupDialog";
import CompareDialog from "./CompareDialog";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Progress } from "../components/ui/progress";
import { Checkbox } from "../components/ui/checkbox";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { ScrollArea } from "../components/ui/scroll-area";
import {
  ScanLine,
  Upload,
  LogOut,
  Loader2,
  Download,
  FileSpreadsheet,
  FileText,
  FileStack,
  Split,
  Columns2,
  Images,
  History,
  CheckCircle2,
  XCircle,
  Trash2,
  Sparkles,
  Clock,
  TriangleAlert,
} from "lucide-react";
import { toast } from "sonner";

const STAGES = [
  { key: "queued", label: "Uploading photos", range: [0, 14] },
  { key: "analyzing", label: "AI visual grouping & OCR", range: [15, 69] },
  { key: "generating", label: "Compiling Excel template", range: [70, 99] },
  { key: "done", label: "Report ready", range: [100, 100] },
];

function stageIndex(status) {
  if (status === "done") return 3;
  if (status === "generating") return 2;
  if (status === "analyzing") return 1;
  return 0;
}

export default function Dashboard() {
  const { user, logout } = useAuth();
  const [files, setFiles] = useState([]);
  const [previews, setPreviews] = useState([]);
  const [dragging, setDragging] = useState(false);
  const [active, setActive] = useState(null); // active inspection doc
  const [history, setHistory] = useState([]);
  const [view, setView] = useState("upload"); // upload | processing | results
  const [selected, setSelected] = useState(new Set());
  const [packing, setPacking] = useState(false);
  const inputRef = useRef();
  const pollRef = useRef();

  const loadHistory = useCallback(() => {
    api.get("/inspections").then((r) => setHistory(r.data)).catch(() => {});
  }, []);

  const toggleSelect = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const downloadReviewPack = async () => {
    const ids = Array.from(selected);
    if (!ids.length) return;
    setPacking(true);
    try {
      const res = await api.post("/inspections/review-pack", { ids }, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = "supplier_review_pack.pdf";
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Review pack downloaded");
    } catch (e) {
      toast.error("Review pack failed");
    } finally {
      setPacking(false);
    }
  };

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  // polling active inspection
  useEffect(() => {
    if (!active || active.status === "done" || active.status === "error") {
      clearInterval(pollRef.current);
      return;
    }
    pollRef.current = setInterval(async () => {
      try {
        const { data } = await api.get(`/inspections/${active.id}`);
        setActive(data);
        if (data.status === "done") {
          setView("results");
          loadHistory();
          toast.success(`Report ready — ${data.product_count} product(s)`);
        } else if (data.status === "error") {
          toast.error("Processing failed");
          loadHistory();
        }
      } catch (e) {
        /* ignore */
      }
    }, 2500);
    return () => clearInterval(pollRef.current);
  }, [active, loadHistory]);

  const addFiles = (list) => {
    const imgs = Array.from(list).filter((f) => f.type.startsWith("image/"));
    if (!imgs.length) return;
    setFiles((prev) => [...prev, ...imgs]);
    setPreviews((prev) => [
      ...prev,
      ...imgs.map((f) => ({ name: f.name, url: URL.createObjectURL(f) })),
    ]);
  };

  const removeFile = (idx) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
    setPreviews((prev) => prev.filter((_, i) => i !== idx));
  };

  const clearAll = () => {
    setFiles([]);
    setPreviews([]);
  };

  const generate = async () => {
    if (!files.length) return;
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    try {
      const { data } = await api.post("/inspections", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success("Upload complete — analysing photos");
      const { data: full } = await api.get(`/inspections/${data.id}`);
      setActive(full);
      setView("processing");
      clearAll();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Upload failed");
    }
  };

  const openInspection = async (id) => {
    const { data } = await api.get(`/inspections/${id}`);
    setActive(data);
    setView(data.status === "done" ? "results" : data.status === "error" ? "results" : "processing");
  };

  const newInspection = () => {
    setActive(null);
    setView("upload");
  };

  return (
    <div className="min-h-screen bg-[#0b0f17] text-slate-200">
      {/* header */}
      <header className="sticky top-0 z-50 glass border-b border-white/10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-blue-500 flex items-center justify-center">
              <ScanLine className="h-5 w-5 text-white" />
            </div>
            <div>
              <div className="font-display font-bold leading-tight">InspectAI</div>
              <div className="text-[11px] text-slate-400 -mt-0.5">Buying house QC console</div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={newInspection}
              data-testid="new-inspection-button"
              className="text-slate-300 hover:text-white"
            >
              <Upload className="h-4 w-4 mr-1.5" /> New inspection
            </Button>
            <div className="hidden sm:flex items-center gap-2 text-sm text-slate-400 border-l border-white/10 pl-3">
              <span className="font-mono-data text-xs">{user?.email}</span>
            </div>
            <Button variant="ghost" size="icon" onClick={logout} data-testid="logout-button">
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-8">
        {/* main column */}
        <main className="min-w-0">
          {view === "upload" && (
            <UploadView
              previews={previews}
              dragging={dragging}
              setDragging={setDragging}
              addFiles={addFiles}
              removeFile={removeFile}
              clearAll={clearAll}
              generate={generate}
              inputRef={inputRef}
              count={files.length}
            />
          )}

          {view === "processing" && active && <ProcessingView insp={active} />}

          {view === "results" && active && (
            <ResultsView
              insp={active}
              onNew={newInspection}
              onRegrouped={(data) => {
                setActive(data);
                if (data.status && data.status !== "done") setView("processing");
                loadHistory();
              }}
            />
          )}
        </main>

        {/* history sidebar */}
        <aside className="lg:sticky lg:top-24 h-fit">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-300">
              <History className="h-4 w-4" /> Inspection history
            </div>
          </div>

          {selected.size > 0 && (
            <Button
              onClick={downloadReviewPack}
              disabled={packing}
              data-testid="review-pack-button"
              className="w-full mb-3 h-9 bg-blue-500 hover:bg-blue-600 text-white text-sm"
            >
              {packing ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <FileStack className="h-4 w-4 mr-2" />}
              Review pack PDF ({selected.size})
            </Button>
          )}

          <ScrollArea className="h-[66vh] pr-2">
            <div className="space-y-2">
              {history.length === 0 && (
                <p className="text-xs text-slate-500">No inspections yet.</p>
              )}
              {history.map((h) => (
                <div
                  key={h.id}
                  className={`w-full rounded-xl border p-3 transition ${
                    active?.id === h.id
                      ? "border-blue-500/50 bg-blue-500/10"
                      : "border-white/10 bg-slate-900/40 hover:border-white/20"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    {h.status === "done" && (
                      <span onClick={(e) => e.stopPropagation()}>
                        <Checkbox
                          checked={selected.has(h.id)}
                          onCheckedChange={() => toggleSelect(h.id)}
                          data-testid={`history-select-${h.id}`}
                          className="border-white/30"
                        />
                      </span>
                    )}
                    <button
                      onClick={() => openInspection(h.id)}
                      data-testid={`history-item-${h.id}`}
                      className="flex-1 text-left"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono-data text-slate-400">#{h.id.slice(0, 8)}</span>
                        <StatusPill status={h.status} />
                      </div>
                      <div className="mt-1.5 flex items-center gap-3 text-xs text-slate-400">
                        <span className="flex items-center gap-1">
                          <Images className="h-3 w-3" /> {h.photo_count}
                        </span>
                        {h.product_count != null && (
                          <span className="flex items-center gap-1">
                            <FileSpreadsheet className="h-3 w-3" /> {h.product_count}
                          </span>
                        )}
                        <span className="flex items-center gap-1 ml-auto">
                          <Clock className="h-3 w-3" />
                          {new Date(h.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        </aside>
      </div>
    </div>
  );
}

function StatusPill({ status }) {
  const map = {
    done: ["bg-emerald-500/15 text-emerald-400 border-emerald-500/30", CheckCircle2, "Ready"],
    error: ["bg-red-500/15 text-red-400 border-red-500/30", XCircle, "Error"],
    queued: ["bg-cyan-500/15 text-cyan-400 border-cyan-500/30", Loader2, "Queued"],
    analyzing: ["bg-cyan-500/15 text-cyan-400 border-cyan-500/30", Loader2, "Analysing"],
    generating: ["bg-cyan-500/15 text-cyan-400 border-cyan-500/30", Loader2, "Building"],
  };
  const [cls, Icon, label] = map[status] || map.queued;
  const spin = ["queued", "analyzing", "generating"].includes(status);
  return (
    <Badge className={`${cls} text-[10px] px-1.5`}>
      <Icon className={`h-3 w-3 mr-1 ${spin ? "animate-spin" : ""}`} />
      {label}
    </Badge>
  );
}

function UploadView({ previews, dragging, setDragging, addFiles, removeFile, clearAll, generate, inputRef, count }) {
  return (
    <div className="animate-rise">
      <h1 className="font-display text-3xl sm:text-4xl font-bold tracking-tight">
        Generate an inspection report
      </h1>
      <p className="text-slate-400 mt-2 max-w-2xl">
        Drop a full batch of product &amp; packaging photos. No forms to fill — the AI identifies each
        design, groups photos, reads labels, flags defects, and compiles the Excel report.
      </p>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          addFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        data-testid="photo-upload-dropzone"
        className={`mt-7 cursor-pointer rounded-2xl border-2 border-dashed p-10 text-center transition ${
          dragging ? "border-blue-500 bg-blue-500/10" : "border-white/15 bg-slate-900/40 hover:border-white/30"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          data-testid="photo-file-input"
          onChange={(e) => addFiles(e.target.files)}
        />
        <div className="mx-auto h-14 w-14 rounded-2xl bg-blue-500/15 flex items-center justify-center">
          <Upload className="h-7 w-7 text-blue-400" />
        </div>
        <p className="mt-4 font-medium text-slate-200">Drag &amp; drop photos, or click to browse</p>
        <p className="text-sm text-slate-500 mt-1">JPEG / PNG / WEBP · many photos at once</p>
      </div>

      {previews.length > 0 && (
        <div className="mt-6">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm text-slate-300">
              <span className="font-mono-data text-blue-400">{count}</span> photo(s) selected
            </span>
            <Button variant="ghost" size="sm" onClick={clearAll} data-testid="clear-photos-button">
              <Trash2 className="h-4 w-4 mr-1" /> Clear
            </Button>
          </div>
          <div className="grid grid-cols-3 sm:grid-cols-5 lg:grid-cols-6 gap-2">
            {previews.map((p, i) => (
              <div key={i} className="relative group rounded-lg overflow-hidden border border-white/10 aspect-square">
                <img src={p.url} alt={p.name} className="h-full w-full object-cover" />
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    removeFile(i);
                  }}
                  className="absolute top-1 right-1 h-5 w-5 rounded-full bg-black/70 text-white opacity-0 group-hover:opacity-100 flex items-center justify-center"
                  data-testid={`remove-photo-${i}`}
                >
                  <XCircle className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
          <Button
            onClick={generate}
            disabled={!count}
            data-testid="generate-report-button"
            className="mt-6 h-12 px-6 bg-blue-500 hover:bg-blue-600 text-white font-medium glow-primary"
          >
            <Sparkles className="h-4 w-4 mr-2" /> Generate report
          </Button>
        </div>
      )}
    </div>
  );
}

function ProcessingView({ insp }) {
  const idx = stageIndex(insp.status);
  const progress = insp.progress ?? 0;
  if (insp.status === "error") {
    return (
      <div className="animate-rise rounded-2xl border border-red-500/30 bg-red-500/5 p-8">
        <XCircle className="h-10 w-10 text-red-400" />
        <h2 className="font-display text-2xl font-semibold mt-3">Processing failed</h2>
        <p className="text-sm text-red-300/80 mt-2">{insp.error || "An unexpected error occurred."}</p>
      </div>
    );
  }
  return (
    <div className="animate-rise" data-testid="processing-view">
      <h1 className="font-display text-3xl font-bold tracking-tight">Analysing inspection batch</h1>
      <p className="text-slate-400 mt-2">
        <span className="font-mono-data text-cyan-400">{insp.photo_count}</span> photos ·{" "}
        <span className="font-mono-data">#{insp.id.slice(0, 8)}</span>
      </p>

      <div className="mt-8 rounded-2xl border border-white/10 bg-slate-900/40 p-6">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-slate-300">{STAGES[idx].label}</span>
          <span className="font-mono-data text-cyan-400">{progress}%</span>
        </div>
        <Progress value={progress} className="h-2 bg-slate-800" />

        <div className="mt-8 space-y-4">
          {STAGES.map((s, i) => {
            const stStatus = i < idx ? "done" : i === idx ? "active" : "pending";
            return (
              <div key={s.key} className="flex items-center gap-3">
                <div
                  className={`h-8 w-8 rounded-full flex items-center justify-center shrink-0 ${
                    stStatus === "done"
                      ? "bg-emerald-500/20 text-emerald-400"
                      : stStatus === "active"
                      ? "bg-cyan-500/20 text-cyan-400 pulse-ring"
                      : "bg-slate-800 text-slate-600"
                  }`}
                >
                  {stStatus === "done" ? (
                    <CheckCircle2 className="h-4 w-4" />
                  ) : stStatus === "active" ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <span className="text-xs font-mono-data">{i + 1}</span>
                  )}
                </div>
                <span className={stStatus === "pending" ? "text-slate-600" : "text-slate-200"}>
                  {s.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function ResultsView({ insp, onNew, onRegrouped }) {
  const [regroupOpen, setRegroupOpen] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);
  if (insp.status === "error") {
    return (
      <div className="rounded-2xl border border-red-500/30 bg-red-500/5 p-8">
        <XCircle className="h-10 w-10 text-red-400" />
        <h2 className="font-display text-2xl font-semibold mt-3">Processing failed</h2>
        <p className="text-sm text-red-300/80 mt-2">{insp.error}</p>
        <Button onClick={onNew} className="mt-4 bg-blue-500 hover:bg-blue-600">
          Start new inspection
        </Button>
      </div>
    );
  }
  const products = insp.products || [];
  const downloadUrl = buildAuthedUrl(`/inspections/${insp.id}/download`);
  const pdfUrl = buildAuthedUrl(`/inspections/${insp.id}/download/pdf`);
  return (
    <div className="animate-rise">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-bold tracking-tight">Inspection report</h1>
          <p className="text-slate-400 mt-2">
            <span className="font-mono-data">#{insp.id.slice(0, 8)}</span> · {insp.photo_count} photos ·{" "}
            <span className="text-emerald-400">{products.length} product sheet(s)</span>
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {products.length > 1 && (
            <Button
              variant="outline"
              onClick={() => setCompareOpen(true)}
              data-testid="compare-button"
              className="h-11 border-white/15 bg-slate-900/40 hover:bg-slate-800 text-slate-200"
            >
              <Columns2 className="h-4 w-4 mr-2" /> Compare
            </Button>
          )}
          <Button
            variant="outline"
            onClick={() => setRegroupOpen(true)}
            data-testid="regroup-button"
            className="h-11 border-white/15 bg-slate-900/40 hover:bg-slate-800 text-slate-200"
          >
            <Split className="h-4 w-4 mr-2" /> Regroup
          </Button>
          <a href={pdfUrl} data-testid="download-pdf-button">
            <Button variant="outline" className="h-11 border-white/15 bg-slate-900/40 hover:bg-slate-800 text-slate-200">
              <FileText className="h-4 w-4 mr-2" /> PDF
            </Button>
          </a>
          <a href={downloadUrl} data-testid="download-excel-button">
            <Button className="h-11 bg-emerald-500 hover:bg-emerald-600 text-white font-medium">
              <Download className="h-4 w-4 mr-2" /> Download .xlsx
            </Button>
          </a>
        </div>
      </div>

      {insp.severity_rollup && (
        <div className="mt-5 rounded-xl border border-white/10 bg-slate-900/40 p-4" data-testid="batch-rollup">
          <div className="flex items-center gap-2 text-sm font-medium text-slate-200 mb-3">
            <TriangleAlert className="h-4 w-4 text-amber-400" /> Batch defect rollup vs AQL
          </div>
          <div className="grid grid-cols-3 gap-3">
            {[
              ["Critical", insp.severity_rollup.critical, "0", "text-red-400", "border-red-500/30"],
              ["Major", insp.severity_rollup.major, "2.5", "text-amber-400", "border-amber-500/30"],
              ["Minor", insp.severity_rollup.minor, "4", "text-sky-400", "border-sky-500/30"],
            ].map(([label, found, aql, color, border]) => (
              <div key={label} className={`rounded-lg border ${border} bg-slate-900/40 p-3 text-center`}>
                <div className="text-xs text-slate-400 uppercase tracking-wide">{label}</div>
                <div className={`font-mono-data text-2xl font-semibold ${color}`}>{found ?? 0}</div>
                <div className="text-[11px] text-slate-500 font-mono-data">AQL {aql}</div>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-slate-500 mt-2">
            Max allowed defects depend on lot size and are not determinable from photos.
          </p>
        </div>
      )}

      {(insp.overall_unresolved || []).length > 0 && (
        <div className="mt-5 rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 text-sm text-amber-200/80 flex gap-2">
          <TriangleAlert className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
          <div>{insp.overall_unresolved.join(" ")}</div>
        </div>
      )}

      {products.length === 0 ? (
        <p className="mt-8 text-slate-400">No products were identified in this batch.</p>
      ) : (
        <Tabs defaultValue="0" className="mt-7">
          <TabsList className="bg-slate-900/60 border border-white/10 flex-wrap h-auto">
            {products.map((p, i) => (
              <TabsTrigger
                key={i}
                value={String(i)}
                data-testid={`product-tab-${i}`}
                className="data-[state=active]:bg-blue-500 data-[state=active]:text-white font-mono-data text-xs"
              >
                {p.sheet_name}
              </TabsTrigger>
            ))}
          </TabsList>
          {products.map((p, i) => (
            <TabsContent key={i} value={String(i)} className="mt-6">
              <ProductResults product={p} inspection={insp} />
            </TabsContent>
          ))}
        </Tabs>
      )}

      <RegroupDialog
        open={regroupOpen}
        onClose={() => setRegroupOpen(false)}
        inspection={insp}
        onRegrouped={onRegrouped}
      />
      <CompareDialog open={compareOpen} onClose={() => setCompareOpen(false)} inspection={insp} />
    </div>
  );
}
