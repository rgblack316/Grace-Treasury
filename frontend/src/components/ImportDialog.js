import { useRef, useState } from "react";
import api, { formatApiErrorDetail } from "@/lib/api";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Download, Upload, Loader2, CheckCircle2, AlertTriangle, FileSpreadsheet } from "lucide-react";

export default function ImportDialog({ open, onOpenChange, onImported }) {
  const [file, setFile] = useState(null);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState(null);
  const inputRef = useRef();

  const reset = () => { setFile(null); setResult(null); };

  const downloadTemplate = async () => {
    try {
      const res = await api.get("/import/template", { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "text/csv" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = "transaction-import-template.csv";
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      toast.error("Could not download template");
    }
  };

  const doImport = async () => {
    if (!file) return toast.error("Choose a CSV file first");
    setImporting(true);
    setResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/import/transactions", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setResult(data);
      if (data.created > 0) {
        toast.success(`Imported ${data.created} transaction${data.created !== 1 ? "s" : ""}`);
        onImported && onImported();
      } else {
        toast.error("No transactions were imported — check the errors below");
      }
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setImporting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) reset(); }}>
      <DialogContent className="sm:max-w-lg" data-testid="import-dialog">
        <DialogHeader>
          <DialogTitle className="font-serif text-xl">Import Transactions</DialogTitle>
          <DialogDescription>Carry over past months from a CSV file using the template format.</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="bg-[#FAF8F3] rounded-lg p-4 text-sm text-slate-600 space-y-2">
            <p className="font-medium text-slate-800">How it works</p>
            <ol className="list-decimal list-inside space-y-1">
              <li>Download the template and fill in your rows.</li>
              <li>Use account labels like <span className="font-mono">*1234</span> or the account name.</li>
              <li>New payees, categories, and funds are created automatically.</li>
            </ol>
            <Button variant="outline" size="sm" onClick={downloadTemplate} className="mt-1" data-testid="btn-download-template">
              <Download className="h-4 w-4 mr-2" /> Download Template
            </Button>
          </div>

          <label
            className="flex flex-col items-center justify-center gap-2 border-2 border-dashed border-[#E5E0D8] rounded-xl py-8 cursor-pointer hover:bg-[#FAF8F3] transition-colors"
            data-testid="import-dropzone"
          >
            <FileSpreadsheet className="h-8 w-8 text-[#B45309]" />
            <span className="text-sm font-medium text-slate-800">{file ? file.name : "Choose a CSV file"}</span>
            <span className="text-xs text-muted-foreground">Only .csv files</span>
            <input ref={inputRef} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => { setFile(e.target.files?.[0] || null); setResult(null); }} data-testid="import-file-input" />
          </label>

          {result && (
            <div className="rounded-lg border border-[#E5E0D8] divide-y divide-[#EEEDE7]" data-testid="import-result">
              <div className="flex items-center gap-2 p-3 text-sm">
                <CheckCircle2 className="h-5 w-5 text-[#15803D]" />
                <span><b>{result.created}</b> transaction{result.created !== 1 ? "s" : ""} imported</span>
              </div>
              {(result.created_payees > 0 || result.created_categories > 0 || result.created_funds > 0) && (
                <div className="p-3 text-xs text-muted-foreground">
                  Auto-created: {result.created_payees} payee(s), {result.created_categories} category(ies), {result.created_funds} fund(s)
                </div>
              )}
              {result.errors?.length > 0 && (
                <div className="p-3 text-sm">
                  <div className="flex items-center gap-2 text-[#B45309] font-medium mb-1.5">
                    <AlertTriangle className="h-4 w-4" /> {result.errors.length} row(s) skipped
                  </div>
                  <ul className="space-y-1 max-h-40 overflow-y-auto">
                    {result.errors.map((e, i) => (
                      <li key={i} className="text-xs text-slate-600">Row {e.row}: {e.reason}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
          <Button onClick={doImport} disabled={importing || !file} className="bg-[#1E293B] hover:bg-[#0F172A]" data-testid="btn-run-import">
            {importing ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Upload className="h-4 w-4 mr-2" />}
            Import
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
