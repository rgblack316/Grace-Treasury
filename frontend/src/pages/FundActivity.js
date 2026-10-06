import { useEffect, useState } from "react";
import api, { formatApiErrorDetail } from "@/lib/api";
import { money, fmtDate, todayISO, fundIndent } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { PiggyBank, ArrowLeftRight, Plus, Minus, Trash2, Loader2 } from "lucide-react";

export default function FundActivity() {
  const { can } = useAuth();
  const canManage = can("transactions.manage");
  const [funds, setFunds] = useState([]);
  const [activity, setActivity] = useState([]);
  const [open, setOpen] = useState(false);
  const [deleteId, setDeleteId] = useState(null);

  const load = () => {
    api.get("/dashboard").then((r) => setFunds(r.data.funds || []));
    api.get("/fund-activity").then((r) => setActivity(r.data));
  };
  useEffect(() => { load(); }, []); // eslint-disable-line

  const doDelete = async () => {
    await api.delete(`/fund-activity/${deleteId}`);
    toast.success("Entry removed");
    setDeleteId(null);
    load();
  };

  const describe = (a) => {
    if (a.type === "move") return `Moved from ${a.from_fund_name || "—"} to ${a.to_fund_name || "—"}`;
    return `Adjusted ${a.fund_name || "—"}`;
  };

  return (
    <div className="space-y-8" data-testid="fund-activity-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="font-serif text-3xl font-bold text-slate-900">Funds</h1>
          <p className="text-muted-foreground mt-1">Move money between funds or adjust a single fund — without touching any bank account.</p>
        </div>
        {canManage && (
          <Button onClick={() => setOpen(true)} className="bg-[#D97706] hover:bg-[#B45309]" data-testid="btn-open-fund-activity">
            <ArrowLeftRight className="h-4 w-4 mr-1.5" /> Fund Activity
          </Button>
        )}
      </div>

      <div>
        <h2 className="font-serif text-xl font-semibold text-slate-900 mb-4">Fund Balances</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {funds.length === 0 && <Card className="p-5 text-sm text-muted-foreground">No funds yet. Add one in Settings → Funds.</Card>}
          {funds.map((f) => (
            <Card key={f.id} className="p-5 border-[#E5E0D8]" data-testid={`fund-balance-card-${f.id}`} style={{ marginLeft: (f.depth || 0) * 16 }}>
              <div className="flex items-center justify-between">
                <div className="h-10 w-10 rounded-lg bg-[#FEF3C7] grid place-items-center">
                  <PiggyBank className="h-5 w-5 text-[#B45309]" />
                </div>
                {f.opening_balance ? <Badge variant="secondary" className="font-mono text-xs">Opening {money(f.opening_balance)}</Badge> : null}
              </div>
              <div className="mt-4 text-sm text-muted-foreground">{f.depth ? "↳ " : ""}{f.name}</div>
              <div className="font-mono text-2xl font-bold text-slate-900 mt-1" data-testid={`fund-balance-${f.id}`}>{money(f.has_children ? f.rolled_balance : f.balance)}</div>
              {f.has_children ? <div className="text-xs text-muted-foreground mt-0.5">Own {money(f.balance)} · includes nested</div> : null}
            </Card>
          ))}
        </div>
      </div>

      <div>
        <h2 className="font-serif text-xl font-semibold text-slate-900 mb-4">Activity History</h2>
        <Card className="divide-y divide-[#EEEDE7]">
          {activity.length === 0 && <div className="p-5 text-sm text-muted-foreground">No fund moves or adjustments yet.</div>}
          {activity.map((a) => (
            <div key={a.id} className="flex items-center justify-between p-4" data-testid={`fund-activity-row-${a.id}`}>
              <div className="flex items-center gap-3 min-w-0">
                <div className="h-9 w-9 rounded-lg bg-[#F4F0E8] grid place-items-center shrink-0">
                  {a.type === "move" ? <ArrowLeftRight className="h-4 w-4 text-[#1E293B]" /> : (a.amount >= 0 ? <Plus className="h-4 w-4 text-[#15803D]" /> : <Minus className="h-4 w-4 text-[#B91C1C]" />)}
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-medium text-slate-800 truncate">{describe(a)}</div>
                  <div className="text-xs text-muted-foreground">{fmtDate(a.date)}{a.memo ? ` · ${a.memo}` : ""}</div>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className={`font-mono font-semibold ${a.type === "adjust" && a.amount < 0 ? "text-[#B91C1C]" : "text-slate-900"}`}>
                  {a.type === "adjust" && a.amount >= 0 ? "+" : ""}{money(a.amount)}
                </span>
                {canManage && (
                  <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={() => setDeleteId(a.id)} data-testid={`btn-delete-fund-activity-${a.id}`}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </div>
          ))}
        </Card>
      </div>

      <FundActivityDialog open={open} onOpenChange={setOpen} funds={funds} onSaved={load} />

      <AlertDialog open={!!deleteId} onOpenChange={(o) => !o && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove this fund entry?</AlertDialogTitle>
            <AlertDialogDescription>This will adjust the affected fund balances. It cannot be undone.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={doDelete} className="bg-destructive hover:bg-destructive/90" data-testid="confirm-delete-fund-activity">Remove</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

const MODES = [
  { id: "move", label: "Move between funds", icon: ArrowLeftRight },
  { id: "adjust", label: "Adjust a fund", icon: Plus },
];

function FundActivityDialog({ open, onOpenChange, funds, onSaved }) {
  const [mode, setMode] = useState("move");
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setMode("move");
      setForm({ date: todayISO(), amount: "", memo: "", direction: "add" });
    }
  }, [open]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    const amt = Number(form.amount);
    if (!amt || amt <= 0) return toast.error("Enter an amount greater than zero");
    let payload;
    if (mode === "move") {
      if (!form.from_fund_id || !form.to_fund_id) return toast.error("Choose both funds");
      if (form.from_fund_id === form.to_fund_id) return toast.error("Source and destination must differ");
      payload = { type: "move", date: form.date, amount: amt, from_fund_id: form.from_fund_id, to_fund_id: form.to_fund_id, memo: form.memo || "" };
    } else {
      if (!form.fund_id) return toast.error("Choose a fund");
      const signed = form.direction === "subtract" ? -amt : amt;
      payload = { type: "adjust", date: form.date, amount: signed, fund_id: form.fund_id, memo: form.memo || "" };
    }
    setSaving(true);
    try {
      await api.post("/fund-activity", payload);
      toast.success("Fund activity saved");
      onOpenChange(false);
      onSaved && onSaved();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" data-testid="fund-activity-dialog">
        <DialogHeader>
          <DialogTitle className="font-serif text-xl">Fund Activity</DialogTitle>
          <DialogDescription>Move money between funds or adjust one fund. Bank account balances are not affected.</DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-2">
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => setMode(m.id)}
              data-testid={`fund-activity-mode-${m.id}`}
              className={`flex flex-col items-center gap-1.5 py-3 rounded-lg border transition-all ${
                mode === m.id ? "border-[#1E293B] bg-[#F4F0E8] ring-1 ring-[#1E293B]" : "border-[#E5E0D8] hover:bg-[#FAF8F3]"
              }`}
            >
              <m.icon className="h-5 w-5 text-[#1E293B]" />
              <span className="text-sm font-medium">{m.label}</span>
            </button>
          ))}
        </div>

        <div className="space-y-4 mt-1">
          {mode === "move" ? (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>From Fund</Label>
                <Select value={form.from_fund_id || ""} onValueChange={(v) => set("from_fund_id", v)}>
                  <SelectTrigger data-testid="fa-from-fund"><SelectValue placeholder="Source fund" /></SelectTrigger>
                  <SelectContent>{funds.map((f) => <SelectItem key={f.id} value={f.id}>{fundIndent(f.depth)}{f.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>To Fund</Label>
                <Select value={form.to_fund_id || ""} onValueChange={(v) => set("to_fund_id", v)}>
                  <SelectTrigger data-testid="fa-to-fund"><SelectValue placeholder="Destination fund" /></SelectTrigger>
                  <SelectContent>{funds.map((f) => <SelectItem key={f.id} value={f.id}>{fundIndent(f.depth)}{f.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Fund</Label>
                <Select value={form.fund_id || ""} onValueChange={(v) => set("fund_id", v)}>
                  <SelectTrigger data-testid="fa-fund"><SelectValue placeholder="Choose fund" /></SelectTrigger>
                  <SelectContent>{funds.map((f) => <SelectItem key={f.id} value={f.id}>{fundIndent(f.depth)}{f.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Direction</Label>
                <Select value={form.direction || "add"} onValueChange={(v) => set("direction", v)}>
                  <SelectTrigger data-testid="fa-direction"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="add">Add to fund</SelectItem>
                    <SelectItem value="subtract">Subtract from fund</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Date</Label>
              <Input type="date" value={form.date || ""} onChange={(e) => set("date", e.target.value)} data-testid="fa-date" />
            </div>
            <div className="space-y-1.5">
              <Label>Amount (USD)</Label>
              <Input type="number" step="0.01" min="0" value={form.amount ?? ""} onChange={(e) => set("amount", e.target.value)} placeholder="0.00" className="font-mono" data-testid="fa-amount" />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Memo / Reason <span className="text-muted-foreground font-normal">(optional)</span></Label>
            <Textarea value={form.memo || ""} onChange={(e) => set("memo", e.target.value)} rows={2} placeholder="e.g. Reallocate surplus to Building Fund" data-testid="fa-memo" />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="fa-cancel">Cancel</Button>
          <Button onClick={submit} disabled={saving} className="bg-[#1E293B] hover:bg-[#0F172A]" data-testid="fa-save">
            {saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
