import { useEffect, useState } from "react";
import api, { formatApiErrorDetail } from "@/lib/api";
import { todayISO } from "@/lib/format";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
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
import { ArrowDownCircle, ArrowUpCircle, ArrowLeftRight, Loader2 } from "lucide-react";

const TYPES = [
  { id: "income", label: "Income", icon: ArrowDownCircle, color: "text-[#15803D]" },
  { id: "expense", label: "Expense", icon: ArrowUpCircle, color: "text-[#B91C1C]" },
  { id: "transfer", label: "Transfer", icon: ArrowLeftRight, color: "text-[#1D4ED8]" },
];

const NONE = "__none__";

export default function TransactionDialog({ open, onOpenChange, editing, onSaved }) {
  const [type, setType] = useState("income");
  const [form, setForm] = useState({});
  const [lists, setLists] = useState({ accounts: [], funds: [], categories: [], payees: [] });
  const [saving, setSaving] = useState(false);

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
    } else {
      setType("income");
      setForm({ date: todayISO(), amount: "", check_number: "", memo: "" });
    }
  }, [open, editing]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v === NONE ? "" : v }));

  const submit = async () => {
    if (!form.account_id) return toast.error("Please choose a bank account");
    if (!form.amount || Number(form.amount) <= 0) return toast.error("Enter an amount greater than zero");
    if (type === "transfer" && !form.to_account_id) return toast.error("Choose a destination account");
    if (type === "transfer" && form.to_account_id === form.account_id) return toast.error("Source and destination must differ");

    const payload = {
      type,
      date: form.date,
      account_id: form.account_id,
      to_account_id: type === "transfer" ? form.to_account_id : null,
      amount: Number(form.amount),
      payee_id: form.payee_id || null,
      check_number: form.check_number || "",
      category_id: form.category_id || null,
      fund_id: form.fund_id || null,
      memo: form.memo || "",
    };
    setSaving(true);
    try {
      if (editing) {
        await api.put(`/transactions/${editing.id}`, payload);
        toast.success("Transaction updated");
      } else {
        await api.post("/transactions", payload);
        toast.success("Transaction recorded");
      }
      onOpenChange(false);
      onSaved && onSaved();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const catsForType = lists.categories.filter((c) =>
    type === "transfer" ? false : c.type === type
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[92vh] overflow-y-auto" data-testid="transaction-dialog">
        <DialogHeader>
          <DialogTitle className="font-serif text-xl">
            {editing ? "Edit Transaction" : "Record a Transaction"}
          </DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-3 gap-2">
          {TYPES.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setType(t.id)}
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
            <div className="grid grid-cols-2 gap-3">
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
              <div className="space-y-1.5">
                <Label>Fund <span className="text-muted-foreground font-normal">(optional)</span></Label>
                <Select value={form.fund_id || ""} onValueChange={(v) => set("fund_id", v)}>
                  <SelectTrigger data-testid="select-fund"><SelectValue placeholder="Choose fund" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>None</SelectItem>
                    {lists.funds.map((f) => (
                      <SelectItem key={f.id} value={f.id}>{f.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}

          <div className="space-y-1.5">
            <Label>{type === "expense" ? "Memo / Reason" : "Memo"} <span className="text-muted-foreground font-normal">(optional)</span></Label>
            <Textarea value={form.memo || ""} onChange={(e) => set("memo", e.target.value)} rows={2} placeholder="e.g. Electric Service (Church)" data-testid="input-memo" />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="btn-cancel-transaction">Cancel</Button>
          <Button onClick={submit} disabled={saving} className="bg-[#1E293B] hover:bg-[#0F172A]" data-testid="btn-save-transaction">
            {saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            {editing ? "Save Changes" : "Record"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
