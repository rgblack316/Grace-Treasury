import { useEffect, useState } from "react";
import api, { formatApiErrorDetail } from "@/lib/api";
import { todayISO, money, orderFunds, fundIndent } from "@/lib/format";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ArrowDownCircle, ArrowUpCircle, ArrowLeftRight, Loader2, Paperclip, FileText, ImageIcon, Trash2, Eye, Upload, Split, Plus } from "lucide-react";

const TYPES = [
  { id: "income", label: "Income", icon: ArrowDownCircle, color: "text-[#15803D]" },
  { id: "expense", label: "Expense", icon: ArrowUpCircle, color: "text-[#B91C1C]" },
  { id: "transfer", label: "Transfer", icon: ArrowLeftRight, color: "text-[#1D4ED8]" },
];

const NONE = "__none__";
const ACCEPT = "image/jpeg,image/png,image/heic,image/heif,image/webp,application/pdf";

export default function TransactionDialog({ open, onOpenChange, editing, onSaved }) {
  const [type, setType] = useState("income");
  const [form, setForm] = useState({});
  const [lists, setLists] = useState({ accounts: [], funds: [], categories: [], payees: [] });
  const [saving, setSaving] = useState(false);
  const [pending, setPending] = useState([]); // File[] to upload on save
  const [existing, setExisting] = useState([]); // uploaded attachments
  const [uploading, setUploading] = useState(false);
  const [splitMode, setSplitMode] = useState(false);
  const [splits, setSplits] = useState([]); // [{fund_id, amount}]

  useEffect(() => {
    if (!open) return;
    Promise.all([
      api.get("/accounts"),
      api.get("/funds"),
      api.get("/categories"),
      api.get("/payees"),
    ]).then(([a, f, c, p]) =>
      setLists({ accounts: a.data, funds: f.data, categories: c.data, payees: p.data })
    );
  }, [open]);

  useEffect(() => {
    if (!open) return;
    setPending([]);
    setExisting([]);
    if (editing) {
      setType(editing.type);
      setForm({
        date: editing.date,
        account_id: editing.account_id,
        to_account_id: editing.to_account_id || "",
        amount: editing.amount,
        payee_id: editing.payee_id || "",
        check_number: editing.check_number || "",
        category_id: editing.category_id || "",
        fund_id: editing.fund_id || "",
        memo: editing.memo || "",
      });
      if (editing.fund_splits && editing.fund_splits.length) {
        setSplitMode(true);
        setSplits(editing.fund_splits.map((s) => ({ fund_id: s.fund_id, amount: s.amount })));
      } else {
        setSplitMode(false);
        setSplits([]);
      }
      api.get(`/transactions/${editing.id}/attachments`).then((r) => setExisting(r.data)).catch(() => {});
    } else {
      setType("income");
      setForm({ date: todayISO(), amount: "", check_number: "", memo: "" });
      setSplitMode(false);
      setSplits([]);
    }
  }, [open, editing]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v === NONE ? "" : v }));

  const addFiles = (fileList) => {
    const files = Array.from(fileList || []);
    const valid = files.filter((f) => ACCEPT.split(",").includes(f.type));
    if (valid.length !== files.length) toast.error("Only photos and PDF files are allowed");
    setPending((p) => [...p, ...valid]);
  };

  const uploadTo = async (txnId) => {
    for (const file of pending) {
      const fd = new FormData();
      fd.append("file", file);
      await api.post(`/transactions/${txnId}/attachments`, fd, { headers: { "Content-Type": "multipart/form-data" } });
    }
  };

  const viewExisting = async (f) => {
    try {
      const res = await api.get(`/attachments/${f.id}/download`, { responseType: "blob" });
      const url = window.URL.createObjectURL(res.data);
      window.open(url, "_blank");
      setTimeout(() => window.URL.revokeObjectURL(url), 60000);
    } catch {
      toast.error("Could not open the receipt. Please try again.");
    }
  };

  const deleteExisting = async (f) => {
    try {
      await api.delete(`/attachments/${f.id}`);
      setExisting((e) => e.filter((x) => x.id !== f.id));
      toast.success("Receipt removed");
    } catch {
      toast.error("Could not remove the receipt. Please try again.");
    }
  };

  // Split helpers
  const enableSplit = () => {
    const amt = Number(form.amount) || 0;
    const base = [];
    if (form.fund_id) base.push({ fund_id: form.fund_id, amount: amt || "" });
    else base.push({ fund_id: "", amount: amt || "" });
    base.push({ fund_id: "", amount: "" });
    setSplits(base);
    setSplitMode(true);
  };
  const disableSplit = () => { setSplitMode(false); setSplits([]); };
  const setSplit = (i, k, v) => setSplits((s) => s.map((row, idx) => (idx === i ? { ...row, [k]: v } : row)));
  const addSplitRow = () => setSplits((s) => [...s, { fund_id: "", amount: "" }]);
  const removeSplitRow = (i) => setSplits((s) => s.filter((_, idx) => idx !== i));
  const splitTotal = splits.reduce((acc, s) => acc + (Number(s.amount) || 0), 0);
  const remaining = (Number(form.amount) || 0) - splitTotal;

  const submit = async () => {
    if (!form.account_id) return toast.error("Please choose a bank account");
    if (!form.amount || Number(form.amount) <= 0) return toast.error("Enter an amount greater than zero");
    if (type === "transfer" && !form.to_account_id) return toast.error("Choose a destination account");
    if (type === "transfer" && form.to_account_id === form.account_id) return toast.error("Source and destination must differ");

    let fundSplits = null;
    if (type !== "transfer" && splitMode) {
      const cleaned = splits
        .filter((s) => s.fund_id && Number(s.amount) > 0)
        .map((s) => ({ fund_id: s.fund_id, amount: Number(s.amount) }));
      if (cleaned.length === 0) return toast.error("Add at least one fund with an amount");
      const total = cleaned.reduce((a, s) => a + s.amount, 0);
      if (Math.abs(total - Number(form.amount)) > 0.01) {
        return toast.error(`Fund splits must add up to ${money(form.amount)} (currently ${money(total)})`);
      }
      const ids = cleaned.map((s) => s.fund_id);
      if (new Set(ids).size !== ids.length) return toast.error("Each fund can only appear once in the split");
      fundSplits = cleaned;
    }

    const payload = {
      type,
      date: form.date,
      account_id: form.account_id,
      to_account_id: type === "transfer" ? form.to_account_id : null,
      amount: Number(form.amount),
      payee_id: form.payee_id || null,
      check_number: form.check_number || "",
      category_id: form.category_id || null,
      fund_id: type !== "transfer" && !splitMode ? (form.fund_id || null) : null,
      fund_splits: fundSplits,
      memo: form.memo || "",
      cleared: editing ? !!editing.cleared : false,
    };
    setSaving(true);
    try {
      let txnId;
      if (editing) {
        await api.put(`/transactions/${editing.id}`, payload);
        txnId = editing.id;
      } else {
        const { data } = await api.post("/transactions", payload);
        txnId = data.id;
      }
      if (pending.length) {
        setUploading(true);
        await uploadTo(txnId);
      }
      toast.success(editing ? "Transaction updated" : "Transaction recorded");
      onOpenChange(false);
      onSaved && onSaved();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    } finally {
      setSaving(false);
      setUploading(false);
    }
  };

  const catsForType = lists.categories.filter((c) => (type === "transfer" ? false : c.type === type));
  const fileIcon = (ct) => (ct === "application/pdf" ? FileText : ImageIcon);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[92vh] overflow-y-auto" data-testid="transaction-dialog">
        <DialogHeader>
          <DialogTitle className="font-serif text-xl">
            {editing ? "Edit Transaction" : "Record a Transaction"}
          </DialogTitle>
          <DialogDescription>Record income, an expense, or a transfer between accounts.</DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-3 gap-2">
          {TYPES.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => { setType(t.id); if (t.id === "transfer") disableSplit(); }}
              data-testid={`modal-transaction-type-${t.id}`}
              className={`flex flex-col items-center gap-1.5 py-3 rounded-lg border transition-all ${
                type === t.id ? "border-[#1E293B] bg-[#F4F0E8] ring-1 ring-[#1E293B]" : "border-[#E5E0D8] hover:bg-[#FAF8F3]"
              }`}
            >
              <t.icon className={`h-5 w-5 ${t.color}`} />
              <span className="text-sm font-medium">{t.label}</span>
            </button>
          ))}
        </div>

        <div className="space-y-4 mt-1">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Date</Label>
              <Input type="date" value={form.date || ""} onChange={(e) => set("date", e.target.value)} data-testid="input-transaction-date" />
            </div>
            <div className="space-y-1.5">
              <Label>Amount (USD)</Label>
              <Input type="number" step="0.01" min="0" value={form.amount ?? ""} onChange={(e) => set("amount", e.target.value)} placeholder="0.00" className="font-mono" data-testid="input-transaction-amount" />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>{type === "transfer" ? "From Account" : "Bank Account"}</Label>
            <Select value={form.account_id || ""} onValueChange={(v) => set("account_id", v)}>
              <SelectTrigger data-testid="select-bank-account"><SelectValue placeholder="Choose account" /></SelectTrigger>
              <SelectContent>
                {lists.accounts.map((a) => (
                  <SelectItem key={a.id} value={a.id}>{a.name} {a.mask}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {type === "transfer" && (
            <div className="space-y-1.5">
              <Label>To Account</Label>
              <Select value={form.to_account_id || ""} onValueChange={(v) => set("to_account_id", v)}>
                <SelectTrigger data-testid="select-to-account"><SelectValue placeholder="Choose destination" /></SelectTrigger>
                <SelectContent>
                  {lists.accounts.map((a) => (
                    <SelectItem key={a.id} value={a.id}>{a.name} {a.mask}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {type === "expense" && (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Check #</Label>
                <Input value={form.check_number || ""} onChange={(e) => set("check_number", e.target.value)} placeholder="e.g. 4046" className="font-mono" data-testid="input-check-number" />
              </div>
              <div className="space-y-1.5">
                <Label>Payee</Label>
                <Select value={form.payee_id || ""} onValueChange={(v) => set("payee_id", v)}>
                  <SelectTrigger data-testid="select-payee"><SelectValue placeholder="Choose payee" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>None</SelectItem>
                    {lists.payees.map((p) => (
                      <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}

          {type !== "transfer" && (
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label>Category <span className="text-muted-foreground font-normal">(optional)</span></Label>
                <Select value={form.category_id || ""} onValueChange={(v) => set("category_id", v)}>
                  <SelectTrigger data-testid="select-category"><SelectValue placeholder="Choose category" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>None</SelectItem>
                    {catsForType.map((c) => (
                      <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Fund — single or split */}
              {!splitMode ? (
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <Label>Fund <span className="text-muted-foreground font-normal">(optional)</span></Label>
                    <button type="button" onClick={enableSplit} className="text-xs font-medium text-[#B45309] hover:underline inline-flex items-center gap-1" data-testid="btn-enable-split">
                      <Split className="h-3.5 w-3.5" /> Split across funds
                    </button>
                  </div>
                  <Select value={form.fund_id || ""} onValueChange={(v) => set("fund_id", v)}>
                    <SelectTrigger data-testid="select-fund"><SelectValue placeholder="Choose fund" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value={NONE}>None</SelectItem>
                      {orderFunds(lists.funds).map((f) => (
                        <SelectItem key={f.id} value={f.id}>{fundIndent(f.depth)}{f.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ) : (
                <div className="space-y-2 rounded-lg border border-[#E5E0D8] p-3 bg-[#FAF8F3]" data-testid="fund-split-section">
                  <div className="flex items-center justify-between">
                    <Label className="flex items-center gap-1.5"><Split className="h-4 w-4" /> Split across funds</Label>
                    <button type="button" onClick={disableSplit} className="text-xs font-medium text-muted-foreground hover:underline" data-testid="btn-disable-split">Use a single fund</button>
                  </div>
                  {splits.map((s, i) => (
                    <div key={i} className="flex items-center gap-2" data-testid={`split-row-${i}`}>
                      <Select value={s.fund_id || ""} onValueChange={(v) => setSplit(i, "fund_id", v)}>
                        <SelectTrigger className="flex-1" data-testid={`split-fund-${i}`}><SelectValue placeholder="Choose fund" /></SelectTrigger>
                        <SelectContent>
                          {orderFunds(lists.funds).map((f) => (
                            <SelectItem key={f.id} value={f.id}>{fundIndent(f.depth)}{f.name}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Input type="number" step="0.01" min="0" value={s.amount ?? ""} onChange={(e) => setSplit(i, "amount", e.target.value)} placeholder="0.00" className="w-28 font-mono" data-testid={`split-amount-${i}`} />
                      <Button type="button" variant="ghost" size="icon" className="h-8 w-8 text-destructive shrink-0" onClick={() => removeSplitRow(i)} data-testid={`split-remove-${i}`}><Trash2 className="h-4 w-4" /></Button>
                    </div>
                  ))}
                  <div className="flex items-center justify-between pt-1">
                    <button type="button" onClick={addSplitRow} className="text-xs font-medium text-[#B45309] hover:underline inline-flex items-center gap-1" data-testid="btn-add-split-row">
                      <Plus className="h-3.5 w-3.5" /> Add fund
                    </button>
                    <span className={`text-xs font-mono ${Math.abs(remaining) < 0.01 ? "text-[#15803D]" : "text-[#B91C1C]"}`} data-testid="split-remaining">
                      {Math.abs(remaining) < 0.01 ? "Fully allocated" : `${money(remaining)} unallocated`}
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="space-y-1.5">
            <Label>{type === "expense" ? "Memo / Reason" : "Memo"} <span className="text-muted-foreground font-normal">(optional)</span></Label>
            <Textarea value={form.memo || ""} onChange={(e) => set("memo", e.target.value)} rows={2} placeholder="e.g. Electric Service (Church)" data-testid="input-memo" />
          </div>

          {/* Receipts */}
          <div className="space-y-2 pt-1 border-t border-[#EEEDE7]">
            <Label className="flex items-center gap-1.5 pt-2"><Paperclip className="h-4 w-4" /> Receipts <span className="text-muted-foreground font-normal">(photos or PDF)</span></Label>
            {existing.map((f) => {
              const Icon = fileIcon(f.content_type);
              return (
                <div key={f.id} className="flex items-center justify-between bg-[#FAF8F3] rounded-lg px-3 py-2 text-sm" data-testid={`attachment-${f.id}`}>
                  <span className="flex items-center gap-2 min-w-0"><Icon className="h-4 w-4 shrink-0 text-[#B45309]" /><span className="truncate">{f.original_filename}</span></span>
                  <span className="flex items-center gap-1 shrink-0">
                    <Button type="button" variant="ghost" size="icon" className="h-7 w-7" onClick={() => viewExisting(f)} data-testid={`btn-view-attachment-${f.id}`}><Eye className="h-4 w-4" /></Button>
                    <Button type="button" variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => deleteExisting(f)} data-testid={`btn-delete-attachment-${f.id}`}><Trash2 className="h-4 w-4" /></Button>
                  </span>
                </div>
              );
            })}
            {pending.map((f, i) => (
              <div key={i} className="flex items-center justify-between bg-[#F0FDF4] rounded-lg px-3 py-2 text-sm">
                <span className="flex items-center gap-2 min-w-0"><Upload className="h-4 w-4 shrink-0 text-[#15803D]" /><span className="truncate">{f.name}</span><span className="text-xs text-muted-foreground">(pending)</span></span>
                <Button type="button" variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => setPending((p) => p.filter((_, idx) => idx !== i))}><Trash2 className="h-4 w-4" /></Button>
              </div>
            ))}
            <label className="flex items-center justify-center gap-2 border border-dashed border-[#E5E0D8] rounded-lg py-3 text-sm text-muted-foreground cursor-pointer hover:bg-[#FAF8F3]" data-testid="attachment-dropzone">
              <Paperclip className="h-4 w-4" /> Add a receipt
              <input type="file" accept={ACCEPT} multiple className="hidden" onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} data-testid="attachment-input" />
            </label>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="btn-cancel-transaction">Cancel</Button>
          <Button onClick={submit} disabled={saving} className="bg-[#1E293B] hover:bg-[#0F172A]" data-testid="btn-save-transaction">
            {(saving || uploading) && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            {uploading ? "Uploading…" : editing ? "Save Changes" : "Record"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
