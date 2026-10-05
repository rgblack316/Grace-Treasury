import { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { money, fmtDate } from "@/lib/format";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import TransactionDialog from "@/components/TransactionDialog";
import ImportDialog from "@/components/ImportDialog";
import { Search, Pencil, Trash2, Plus, X, Upload, Paperclip, Scale } from "lucide-react";

const ALL = "__all__";

export default function Transactions() {
  const { can } = useAuth();
  const canManage = can("transactions.manage");
  const [params, setParams] = useSearchParams();
  const [txns, setTxns] = useState([]);
  const [lists, setLists] = useState({ accounts: [], funds: [], categories: [], payees: [] });
  const [reconcile, setReconcile] = useState(null);
  const [filters, setFilters] = useState({
    account_id: params.get("account") || "",
    type: "",
    fund_id: "",
    category_id: "",
    start: "",
    end: "",
    search: "",
  });
  const [dialogOpen, setDialogOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [deleteId, setDeleteId] = useState(null);

  const load = () => {
    const q = {};
    Object.entries(filters).forEach(([k, v]) => {
      if (v) q[k] = v;
    });
    api.get("/transactions", { params: q }).then((r) => setTxns(r.data));
    if (filters.account_id) {
      api.get(`/accounts/${filters.account_id}/reconcile`).then((r) => setReconcile(r.data)).catch(() => setReconcile(null));
    } else {
      setReconcile(null);
    }
  };

  useEffect(() => {
    Promise.all([
      api.get("/accounts"),
      api.get("/funds"),
      api.get("/categories"),
      api.get("/payees"),
    ]).then(([a, f, c, p]) =>
      setLists({ accounts: a.data, funds: f.data, categories: c.data, payees: p.data })
    );
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [filters]);

  const maps = useMemo(() => ({
    acc: Object.fromEntries(lists.accounts.map((a) => [a.id, a])),
    fund: Object.fromEntries(lists.funds.map((f) => [f.id, f.name])),
    cat: Object.fromEntries(lists.categories.map((c) => [c.id, c.name])),
    payee: Object.fromEntries(lists.payees.map((p) => [p.id, p.name])),
  }), [lists]);

  const setF = (k, v) => {
    setFilters((f) => ({ ...f, [k]: v === ALL ? "" : v }));
    if (k === "account_id") setParams(v && v !== ALL ? { account: v } : {});
  };

  const clearFilters = () => {
    setFilters({ account_id: "", type: "", fund_id: "", category_id: "", start: "", end: "", search: "" });
    setParams({});
  };

  const toggleCleared = async (t, checked) => {
    setTxns((list) => list.map((x) => (x.id === t.id ? { ...x, cleared: checked } : x)));
    try {
      await api.patch(`/transactions/${t.id}/cleared`, { cleared: checked });
      if (filters.account_id) api.get(`/accounts/${filters.account_id}/reconcile`).then((r) => setReconcile(r.data));
    } catch {
      setTxns((list) => list.map((x) => (x.id === t.id ? { ...x, cleared: !checked } : x)));
      toast.error("Could not update");
    }
  };

  const doDelete = async () => {
    await api.delete(`/transactions/${deleteId}`);
    toast.success("Transaction deleted");
    setDeleteId(null);
    load();
  };

  const typeBadge = (t) => {
    const map = {
      income: "bg-[#F0FDF4] text-[#15803D] border-[#BBF7D0]",
      expense: "bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]",
      transfer: "bg-[#EFF6FF] text-[#1D4ED8] border-[#BFDBFE]",
    };
    return <Badge variant="outline" className={`capitalize ${map[t]}`}>{t}</Badge>;
  };

  const signed = (t) => {
    if (t.type === "income") return <span className="text-[#15803D]">+{money(t.amount)}</span>;
    if (t.type === "expense") return <span className="text-[#B91C1C]">−{money(t.amount)}</span>;
    return <span className="text-[#1D4ED8]">{money(t.amount)}</span>;
  };

  const hasFilters = Object.values(filters).some(Boolean);

  return (
    <div className="space-y-6" data-testid="transactions-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="font-serif text-3xl font-bold text-slate-900">Transactions</h1>
          <p className="text-muted-foreground mt-1">Browse, search, reconcile, and manage every entry.</p>
        </div>
        <div className="flex gap-2">
          {canManage && (
            <Button variant="outline" onClick={() => setImportOpen(true)} data-testid="btn-open-import">
              <Upload className="h-4 w-4 mr-1.5" /> Import
            </Button>
          )}
          {canManage && (
            <Button onClick={() => { setEditing(null); setDialogOpen(true); }} className="bg-[#D97706] hover:bg-[#B45309]" data-testid="btn-add-transaction">
              <Plus className="h-4 w-4 mr-1.5" /> New Entry
            </Button>
          )}
        </div>
      </div>

      {reconcile && (
        <Card className="p-4 bg-[#1E293B] text-white border-0" data-testid="reconcile-bar">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-slate-400 font-semibold mb-3">
            <Scale className="h-4 w-4" /> Reconciliation — {maps.acc[filters.account_id]?.name} {maps.acc[filters.account_id]?.mask}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div><div className="text-xs text-slate-400">Cleared Balance</div><div className="font-mono text-lg font-bold" data-testid="reconcile-cleared">{money(reconcile.cleared_balance)}</div></div>
            <div><div className="text-xs text-slate-400">Current Balance</div><div className="font-mono text-lg font-bold">{money(reconcile.current_balance)}</div></div>
            <div><div className="text-xs text-slate-400">Uncleared Items</div><div className="font-mono text-lg font-bold">{reconcile.uncleared_count}</div></div>
            <div><div className="text-xs text-slate-400">Uncleared Total</div><div className="font-mono text-lg font-bold">{money(reconcile.uncleared_total)}</div></div>
          </div>
          <p className="text-xs text-slate-400 mt-3">Tick each item that appears on your bank statement. When the cleared balance matches your statement's ending balance, the account is reconciled.</p>
        </Card>
      )}

      <Card className="p-4">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="relative lg:col-span-2">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input placeholder="Search memo or check #…" value={filters.search} onChange={(e) => setF("search", e.target.value)} className="pl-9" data-testid="transactions-search-input" />
          </div>
          <Select value={filters.account_id || ALL} onValueChange={(v) => setF("account_id", v)}>
            <SelectTrigger data-testid="filter-account"><SelectValue placeholder="All accounts" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All accounts</SelectItem>
              {lists.accounts.map((a) => <SelectItem key={a.id} value={a.id}>{a.name} {a.mask}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={filters.type || ALL} onValueChange={(v) => setF("type", v)}>
            <SelectTrigger data-testid="filter-type"><SelectValue placeholder="All types" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All types</SelectItem>
              <SelectItem value="income">Income</SelectItem>
              <SelectItem value="expense">Expense</SelectItem>
              <SelectItem value="transfer">Transfer</SelectItem>
            </SelectContent>
          </Select>
          <Select value={filters.fund_id || ALL} onValueChange={(v) => setF("fund_id", v)}>
            <SelectTrigger data-testid="filter-fund"><SelectValue placeholder="All funds" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All funds</SelectItem>
              {lists.funds.map((f) => <SelectItem key={f.id} value={f.id}>{f.name}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={filters.category_id || ALL} onValueChange={(v) => setF("category_id", v)}>
            <SelectTrigger data-testid="filter-category"><SelectValue placeholder="All categories" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All categories</SelectItem>
              {lists.categories.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
            </SelectContent>
          </Select>
          <div className="flex items-center gap-2">
            <Input type="date" value={filters.start} onChange={(e) => setF("start", e.target.value)} data-testid="filter-start" />
            <span className="text-muted-foreground text-sm">to</span>
            <Input type="date" value={filters.end} onChange={(e) => setF("end", e.target.value)} data-testid="filter-end" />
          </div>
        </div>
        {hasFilters && (
          <Button variant="ghost" size="sm" onClick={clearFilters} className="mt-3 text-muted-foreground" data-testid="btn-clear-filters">
            <X className="h-4 w-4 mr-1" /> Clear filters
          </Button>
        )}
      </Card>

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-12 text-center" title="Cleared">✓</TableHead>
              <TableHead>Date</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Account</TableHead>
              <TableHead>Payee / Details</TableHead>
              <TableHead>Check #</TableHead>
              <TableHead>Category</TableHead>
              <TableHead className="text-right">Amount</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {txns.length === 0 && (
              <TableRow><TableCell colSpan={9} className="text-center py-10 text-muted-foreground">No transactions found.</TableCell></TableRow>
            )}
            {txns.map((t) => (
              <TableRow key={t.id} data-testid={`txn-row-${t.id}`} className={t.cleared ? "bg-[#F0FDF4]/40" : ""}>
                <TableCell className="text-center">
                  <Checkbox checked={!!t.cleared} disabled={!canManage} onCheckedChange={(c) => toggleCleared(t, !!c)} data-testid={`cleared-${t.id}`} />
                </TableCell>
                <TableCell className="font-mono text-sm whitespace-nowrap">{fmtDate(t.date)}</TableCell>
                <TableCell>{typeBadge(t.type)}</TableCell>
                <TableCell className="text-sm whitespace-nowrap">{maps.acc[t.account_id]?.mask}{t.type === "transfer" && t.to_account_id ? ` → ${maps.acc[t.to_account_id]?.mask}` : ""}</TableCell>
                <TableCell className="text-sm max-w-[220px] truncate">
                  <span className="inline-flex items-center gap-1.5">
                    {t.attachment_count > 0 && <Paperclip className="h-3.5 w-3.5 text-[#B45309] shrink-0" title={`${t.attachment_count} receipt(s)`} />}
                    {maps.payee[t.payee_id] || t.memo || "—"}
                  </span>
                </TableCell>
                <TableCell className="font-mono text-sm">{t.check_number || "—"}</TableCell>
                <TableCell className="text-sm">{maps.cat[t.category_id] || "—"}</TableCell>
                <TableCell className="text-right font-mono font-medium whitespace-nowrap">{signed(t)}</TableCell>
                <TableCell className="text-right whitespace-nowrap">
                  {canManage ? (
                    <>
                      <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => { setEditing(t); setDialogOpen(true); }} data-testid={`btn-edit-${t.id}`}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={() => setDeleteId(t.id)} data-testid={`btn-delete-${t.id}`}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </>
                  ) : (
                    <span className="text-xs text-muted-foreground">—</span>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {txns.length > 0 && (
          <div className="px-4 py-3 text-sm text-muted-foreground border-t border-[#EEEDE7]">{txns.length} transaction{txns.length !== 1 ? "s" : ""}</div>
        )}
      </Card>

      <TransactionDialog open={dialogOpen} onOpenChange={setDialogOpen} editing={editing} onSaved={load} />
      <ImportDialog open={importOpen} onOpenChange={setImportOpen} onImported={load} />

      <AlertDialog open={!!deleteId} onOpenChange={(o) => !o && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this transaction?</AlertDialogTitle>
            <AlertDialogDescription>This cannot be undone and will adjust your account balances. Any attached receipts will be removed.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={doDelete} className="bg-destructive hover:bg-destructive/90" data-testid="btn-confirm-delete">Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
