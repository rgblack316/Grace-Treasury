import { useEffect, useState } from "react";
import api, { formatApiErrorDetail } from "@/lib/api";
import { money } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
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
import { Plus, Pencil, Trash2, Save, Download, Upload, ShieldCheck, Loader2, AlertTriangle, Mail, Send, Lock, Unlock, RefreshCw, LogOut, History } from "lucide-react";

const PW_HINT = "At least 12 characters with uppercase, lowercase, a number, and a symbol.";
const strongPw = (p) => p.length >= 12 && /[A-Z]/.test(p) && /[a-z]/.test(p) && /\d/.test(p) && /[^A-Za-z0-9]/.test(p);

export default function Settings() {
  const { user, can } = useAuth();
  const canSettings = can("settings.manage");
  const canUsers = can("users.manage");
  const canData = can("data.manage");
  const isAdmin = user?.role === "admin";

  const available = [];
  if (canSettings) available.push("accounts", "funds", "categories", "payees", "church");
  if (canUsers) available.push("roles", "users");
  if (canData) available.push("backup");
  if (isAdmin) available.push("security");
  const first = available[0] || "none";

  return (
    <div className="space-y-6" data-testid="settings-page">
      <div>
        <h1 className="font-serif text-3xl font-bold text-slate-900">Settings</h1>
        <p className="text-muted-foreground mt-1">Manage accounts, funds, categories, payees, users, and backups.</p>
      </div>

      {available.length === 0 ? (
        <Card className="p-6 text-muted-foreground">You don't have access to any settings.</Card>
      ) : (
        <Tabs defaultValue={first}>
          <TabsList className="flex flex-wrap h-auto">
            {canSettings && <TabsTrigger value="accounts" data-testid="settings-tab-accounts">Bank Accounts</TabsTrigger>}
            {canSettings && <TabsTrigger value="funds" data-testid="settings-tab-funds">Funds</TabsTrigger>}
            {canSettings && <TabsTrigger value="categories" data-testid="settings-tab-categories">Categories</TabsTrigger>}
            {canSettings && <TabsTrigger value="payees" data-testid="settings-tab-payees">Payees</TabsTrigger>}
            {canSettings && <TabsTrigger value="church" data-testid="settings-tab-church">Church Info</TabsTrigger>}
            {canUsers && <TabsTrigger value="roles" data-testid="settings-tab-roles">Roles</TabsTrigger>}
            {canUsers && <TabsTrigger value="users" data-testid="settings-tab-users">Users</TabsTrigger>}
            {canData && <TabsTrigger value="backup" data-testid="settings-tab-backup">Backup & Restore</TabsTrigger>}
            {isAdmin && <TabsTrigger value="security" data-testid="settings-tab-security">Security</TabsTrigger>}
          </TabsList>

          {canSettings && <TabsContent value="accounts"><AccountsTab /></TabsContent>}
          {canSettings && <TabsContent value="funds"><FundsTab /></TabsContent>}
          {canSettings && <TabsContent value="categories"><CategoriesTab /></TabsContent>}
          {canSettings && <TabsContent value="payees"><PayeesTab /></TabsContent>}
          {canSettings && <TabsContent value="church"><ChurchTab /></TabsContent>}
          {canUsers && <TabsContent value="roles"><RolesTab /></TabsContent>}
          {canUsers && <TabsContent value="users"><UsersTab me={user} /></TabsContent>}
          {canData && <TabsContent value="backup"><BackupTab /></TabsContent>}
          {isAdmin && <TabsContent value="security"><SecurityTab /><DataCheckCard /><AuditLog /></TabsContent>}
        </Tabs>
      )}
    </div>
  );
}

const ACTIVE_FIELD = { key: "active", label: "Active", type: "switch", hint: "Inactive items are hidden when recording new entries but stay in history and reports." };

function useCrud(path) {
  const [items, setItems] = useState([]);
  const load = () => api.get(`/${path}`).then((r) => setItems(r.data));
  useEffect(() => { load(); }, []); // eslint-disable-line
  return { items, load };
}

function CrudDialog({ open, onOpenChange, title, fields, initial, onSubmit }) {
  const [form, setForm] = useState({});
  useEffect(() => { if (open) setForm(initial || {}); }, [open, initial]);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="crud-dialog">
        <DialogHeader><DialogTitle className="font-serif">{title}</DialogTitle>
          <DialogDescription>Fill in the details below.</DialogDescription></DialogHeader>
        <div className="space-y-4">
          {fields.map((f) => (
            <div key={f.key} className="space-y-1.5">
              {f.type !== "switch" && <Label>{f.label}</Label>}
              {f.type === "switch" ? (
                <label className="flex items-start gap-2 cursor-pointer">
                  <Switch checked={form[f.key] !== false} onCheckedChange={(v) => set(f.key, v)} className="mt-0.5" data-testid={`crud-${f.key}`} />
                  <span className="text-sm">{f.label}{f.hint && <span className="block text-xs text-muted-foreground">{f.hint}</span>}</span>
                </label>
              ) : f.type === "select" ? (
                <Select value={form[f.key] || ""} onValueChange={(v) => set(f.key, v)}>
                  <SelectTrigger data-testid={`crud-${f.key}`}><SelectValue placeholder={f.placeholder} /></SelectTrigger>
                  <SelectContent>
                    {f.options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              ) : (
                <Input type={f.type || "text"} value={form[f.key] ?? ""} onChange={(e) => set(f.key, e.target.value)} placeholder={f.placeholder} data-testid={`crud-${f.key}`} />
              )}
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={() => onSubmit(form)} className="bg-[#1E293B] hover:bg-[#0F172A]" data-testid="crud-save"><Save className="h-4 w-4 mr-2" />Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ManagerCard({ title, description, items, columns, fields, path, buildPayload, label }) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [deleteId, setDeleteId] = useState(null);
  const [list, setList] = useState(items);
  useEffect(() => setList(items), [items]);
  const load = () => api.get(`/${path}`).then((r) => setList(r.data));
  const submit = async (form) => {
    try {
      const payload = buildPayload(form);
      if (editing) await api.put(`/${path}/${editing.id}`, payload);
      else await api.post(`/${path}`, payload);
      toast.success(`${label} saved`);
      setOpen(false); setEditing(null); load();
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
  };
  const doDelete = async () => {
    const item = list.find((x) => x.id === deleteId);
    setDeleteId(null);
    try {
      await api.delete(`/${path}/${item.id}`);
      toast.success(`${label} deleted`);
      load();
    } catch (e) {
      const msg = formatApiErrorDetail(e.response?.data?.detail);
      if (e.response?.status === 409 && item && item.active !== false) {
        toast.error(msg, {
          duration: 10000,
          action: { label: "Mark inactive", onClick: async () => {
            try { await api.put(`/${path}/${item.id}`, buildPayload({ ...item, active: false })); toast.success(`${label} marked inactive`); load(); }
            catch (err) { toast.error(formatApiErrorDetail(err.response?.data?.detail)); }
          } },
        });
      } else toast.error(msg);
    }
  };
  return (
    <Card className="p-5 mt-4">
      <div className="flex items-center justify-between mb-4">
        <div><h3 className="font-serif text-lg font-semibold text-slate-900">{title}</h3><p className="text-sm text-muted-foreground">{description}</p></div>
        <Button size="sm" onClick={() => { setEditing(null); setOpen(true); }} className="bg-[#D97706] hover:bg-[#B45309]" data-testid={`btn-add-${path}`}><Plus className="h-4 w-4 mr-1.5" />Add</Button>
      </div>
      <div className="divide-y divide-[#EEEDE7] border-t border-[#EEEDE7]">
        {list.length === 0 && <div className="py-6 text-sm text-muted-foreground text-center">Nothing yet.</div>}
        {list.map((it) => (
          <div key={it.id} className="flex items-center justify-between py-3" data-testid={`${path}-row-${it.id}`}>
            <div className={`min-w-0 flex items-center gap-2 ${it.active === false ? "opacity-60" : ""}`}>{columns(it)}{it.active === false && <Badge variant="outline" className="shrink-0 text-muted-foreground" data-testid={`inactive-${it.id}`}>Inactive</Badge>}</div>
            <div className="flex items-center gap-1 shrink-0">
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => { setEditing(it); setOpen(true); }} data-testid={`btn-edit-${path}-${it.id}`}><Pencil className="h-4 w-4" /></Button>
              <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={() => setDeleteId(it.id)} data-testid={`btn-delete-${path}-${it.id}`}><Trash2 className="h-4 w-4" /></Button>
            </div>
          </div>
        ))}
      </div>
      <CrudDialog open={open} onOpenChange={setOpen} title={`${editing ? "Edit" : "Add"} ${label}`} fields={fields} initial={editing} onSubmit={submit} />
      <AlertDialog open={!!deleteId} onOpenChange={(o) => !o && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>Delete {label.toLowerCase()}?</AlertDialogTitle><AlertDialogDescription>This can't be undone. Items already used by transactions can't be deleted; mark them inactive instead.</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={doDelete} className="bg-destructive hover:bg-destructive/90" data-testid="confirm-delete">Delete</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}

function AccountsTab() {
  const { items } = useCrud("accounts");
  return (
    <ManagerCard title="Bank Accounts" description="Track checking and savings accounts. Opening balance seeds the running balance."
      items={items} path="accounts" label="Account"
      columns={(a) => (
        <div><div className="font-medium text-slate-800">{a.name} <Badge variant="secondary" className="font-mono ml-1">{a.mask}</Badge></div>
          <div className="text-xs text-muted-foreground">Opening {money(a.opening_balance)} as of {a.opening_date || "—"}</div></div>
      )}
      fields={[
        { key: "name", label: "Account Name", placeholder: "General Operating Checking" },
        { key: "mask", label: "Masked Number", placeholder: "*1234" },
        { key: "opening_balance", label: "Opening Balance", type: "number", placeholder: "0.00" },
        { key: "opening_date", label: "Opening Date", type: "date" },
        ACTIVE_FIELD,
      ]}
      buildPayload={(f) => ({ name: f.name, mask: f.mask || "", opening_balance: Number(f.opening_balance || 0), opening_date: f.opening_date || "", active: f.active !== false })}
    />
  );
}

function FundsTab() {
  const { items } = useCrud("funds");
  const parentName = Object.fromEntries(items.map((f) => [f.id, f.name]));
  const parentOptions = [{ value: "none", label: "None (top level)" }, ...items.map((f) => ({ value: f.id, label: f.name }))];
  return (
    <ManagerCard title="Church Funds" description="Track money by purpose, independent of which account holds it. Set a starting balance, and optionally nest a fund inside another."
      items={items} path="funds" label="Fund"
      columns={(f) => <div><div className="font-medium text-slate-800">{f.name}{f.parent_id && parentName[f.parent_id] ? <span className="text-xs font-normal text-muted-foreground"> · under {parentName[f.parent_id]}</span> : null}</div><div className="text-xs text-muted-foreground">{f.description || "—"}{(f.opening_balance ? ` · Opening ${money(f.opening_balance)}${f.opening_date ? ` as of ${f.opening_date}` : ""}` : "")}</div></div>}
      fields={[
        { key: "name", label: "Fund Name", placeholder: "Building Fund" },
        { key: "description", label: "Description", placeholder: "Optional" },
        { key: "parent_id", label: "Nested under (optional)", type: "select", placeholder: "Top level fund", options: parentOptions },
        { key: "opening_balance", label: "Opening Balance", type: "number", placeholder: "0.00" },
        { key: "opening_date", label: "Opening Date", type: "date" },
        ACTIVE_FIELD,
      ]}
      buildPayload={(f) => ({ name: f.name, description: f.description || "", parent_id: f.parent_id && f.parent_id !== "none" ? f.parent_id : null, opening_balance: Number(f.opening_balance || 0), opening_date: f.opening_date || "", active: f.active !== false })}
    />
  );
}

function CategoriesTab() {
  const { items } = useCrud("categories");
  return (
    <ManagerCard title="Categories" description="Group income and expenses for the summary report. Optional on each transaction."
      items={items} path="categories" label="Category"
      columns={(c) => <div className="flex items-center gap-2"><span className="font-medium text-slate-800">{c.name}</span><Badge variant="outline" className={`capitalize ${c.type === "income" ? "text-[#15803D] border-[#BBF7D0]" : "text-[#B91C1C] border-[#FECACA]"}`}>{c.type}</Badge></div>}
      fields={[{ key: "name", label: "Category Name", placeholder: "Utilities" }, { key: "type", label: "Type", type: "select", placeholder: "Choose type", options: [{ value: "income", label: "Income" }, { value: "expense", label: "Expense" }] }, ACTIVE_FIELD]}
      buildPayload={(f) => ({ name: f.name, type: f.type || "expense", active: f.active !== false })}
    />
  );
}

function PayeesTab() {
  const { items } = useCrud("payees");
  return (
    <ManagerCard title="Payees & Vendors" description="A quick-pick list for recording expenses consistently."
      items={items} path="payees" label="Payee"
      columns={(p) => <div className="font-medium text-slate-800">{p.name}</div>}
      fields={[{ key: "name", label: "Payee / Vendor Name", placeholder: "Frontier Communications" }, ACTIVE_FIELD]}
      buildPayload={(f) => ({ name: f.name, active: f.active !== false })}
    />
  );
}

function ChurchTab() {
  const [form, setForm] = useState(null);
  useEffect(() => { api.get("/settings/church").then((r) => setForm(r.data)); }, []);
  if (!form) return null;
  const save = async () => {
    await api.put("/settings/church", { church_name: form.church_name, treasurer_name: form.treasurer_name || "", meeting_day: form.meeting_day || "" });
    toast.success("Church info saved");
  };
  return (
    <Card className="p-5 mt-4 max-w-lg space-y-4">
      <h3 className="font-serif text-lg font-semibold text-slate-900">Church Information</h3>
      <div className="space-y-1.5"><Label>Church Name</Label><Input value={form.church_name || ""} onChange={(e) => setForm({ ...form, church_name: e.target.value })} data-testid="church-name-input" /></div>
      <div className="space-y-1.5"><Label>Treasurer Name <span className="text-muted-foreground font-normal">(appears on report)</span></Label><Input value={form.treasurer_name || ""} onChange={(e) => setForm({ ...form, treasurer_name: e.target.value })} placeholder="e.g. Jane Smith" data-testid="treasurer-name-input" /></div>
      <div className="space-y-1.5"><Label>Business Meeting Day <span className="text-muted-foreground font-normal">(optional)</span></Label><Input value={form.meeting_day || ""} onChange={(e) => setForm({ ...form, meeting_day: e.target.value })} placeholder="e.g. Last Wednesday" data-testid="meeting-day-input" /></div>
      <Button onClick={save} className="bg-[#1E293B] hover:bg-[#0F172A]" data-testid="btn-save-church"><Save className="h-4 w-4 mr-2" />Save</Button>
    </Card>
  );
}

function RolesTab() {
  const [roles, setRoles] = useState([]);
  const [perms, setPerms] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [deleteId, setDeleteId] = useState(null);
  const [form, setForm] = useState({ name: "", permissions: [] });
  const load = () => api.get("/roles").then((r) => setRoles(r.data));
  useEffect(() => { load(); api.get("/permissions").then((r) => setPerms(r.data)); }, []);

  const openNew = () => { setEditing(null); setForm({ name: "", permissions: [] }); setOpen(true); };
  const openEdit = (r) => { setEditing(r); setForm({ name: r.name, permissions: [...r.permissions] }); setOpen(true); };
  const togglePerm = (k) => setForm((f) => ({ ...f, permissions: f.permissions.includes(k) ? f.permissions.filter((x) => x !== k) : [...f.permissions, k] }));

  const save = async () => {
    if (!form.name.trim()) return toast.error("Give the role a name");
    try {
      if (editing) await api.put(`/roles/${editing.id}`, form);
      else await api.post("/roles", form);
      toast.success("Role saved"); setOpen(false); load();
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
  };
  const doDelete = async () => {
    try { await api.delete(`/roles/${deleteId}`); toast.success("Role deleted"); setDeleteId(null); load(); }
    catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); setDeleteId(null); }
  };

  return (
    <Card className="p-5 mt-4">
      <div className="flex items-center justify-between mb-4">
        <div><h3 className="font-serif text-lg font-semibold text-slate-900">Roles</h3><p className="text-sm text-muted-foreground">Create roles that limit what a user can do. Assign them on the Users tab.</p></div>
        <Button size="sm" onClick={openNew} className="bg-[#D97706] hover:bg-[#B45309]" data-testid="btn-add-role"><Plus className="h-4 w-4 mr-1.5" />Add Role</Button>
      </div>
      <div className="divide-y divide-[#EEEDE7] border-t border-[#EEEDE7]">
        {roles.map((r) => (
          <div key={r.id} className="flex items-start justify-between py-3" data-testid={`role-row-${r.id}`}>
            <div className="min-w-0">
              <div className="font-medium text-slate-800 flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-[#B45309]" /> {r.name}
                {r.is_system && <Badge variant="secondary">Built-in</Badge>}
                <span className="text-xs text-muted-foreground font-normal">· {r.user_count} user(s)</span>
              </div>
              <div className="flex flex-wrap gap-1 mt-1.5">
                {r.permissions.map((p) => (perms.find((x) => x.key === p)) && <Badge key={p} variant="outline" className="text-xs">{p}</Badge>)}
                {r.permissions.length === 0 && <span className="text-xs text-muted-foreground">No permissions</span>}
              </div>
            </div>
            {!r.is_system && (
              <div className="flex items-center gap-1 shrink-0">
                <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEdit(r)} data-testid={`btn-edit-role-${r.id}`}><Pencil className="h-4 w-4" /></Button>
                <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={() => setDeleteId(r.id)} data-testid={`btn-delete-role-${r.id}`}><Trash2 className="h-4 w-4" /></Button>
              </div>
            )}
          </div>
        ))}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid="role-dialog">
          <DialogHeader><DialogTitle className="font-serif">{editing ? "Edit Role" : "Add Role"}</DialogTitle>
            <DialogDescription>Choose exactly what this role is allowed to do.</DialogDescription></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5"><Label>Role Name</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Assistant Treasurer" data-testid="role-name-input" /></div>
            <div className="space-y-2">
              <Label>Permissions</Label>
              {perms.map((p) => (
                <label key={p.key} className="flex items-start gap-2.5 cursor-pointer rounded-lg border border-[#E5E0D8] p-2.5 hover:bg-[#FAF8F3]">
                  <Checkbox checked={form.permissions.includes(p.key)} onCheckedChange={() => togglePerm(p.key)} data-testid={`perm-${p.key}`} />
                  <span className="text-sm"><span className="font-medium text-slate-800">{p.key}</span><br /><span className="text-muted-foreground text-xs">{p.label}</span></span>
                </label>
              ))}
            </div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button><Button onClick={save} className="bg-[#1E293B] hover:bg-[#0F172A]" data-testid="btn-save-role">Save Role</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleteId} onOpenChange={(o) => !o && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>Delete this role?</AlertDialogTitle><AlertDialogDescription>Roles assigned to users cannot be deleted until reassigned.</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={doDelete} className="bg-destructive hover:bg-destructive/90" data-testid="confirm-delete-role">Delete</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}

const AUDIT_LABELS = {
  "setup.admin_created": "Administrator account created",
  "user.create": "Added user",
  "user.rename": "Renamed user",
  "user.role_change": "Changed role",
  "user.password_reset": "Reset password",
  "user.sign_out": "Signed user out",
  "user.delete": "Removed user",
  "self.password_change": "Changed own password",
  "self.sign_out_everywhere": "Signed out other devices",
  "role.create": "Created role",
  "role.update": "Edited role",
  "role.delete": "Deleted role",
  "login.unlock": "Unlocked sign-in",
  "data.check": "Ran a data check",
  "settings.account_notices": "Account emails setting",
  "backup.passphrase_set": "Set backup passphrase",
  "backup.passphrase_changed": "Changed backup passphrase",
  "backup.run": "Ran a backup",
  "backup.download": "Downloaded a backup",
  "backup.delete": "Deleted a backup",
  "backup.email": "Emailed a backup",
  "data.export": "Downloaded a backup",
  "data.restore": "Restored from backup",
};

function DataCheckCard() {
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const run = async () => {
    setRunning(true);
    try { const { data } = await api.get("/security/data-check"); setResult(data); }
    catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
    finally { setRunning(false); }
  };
  const c = result?.checked;
  return (
    <Card className="p-5 mt-4" data-testid="data-check-card">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
        <div>
          <h3 className="font-serif text-lg font-semibold text-slate-900 flex items-center gap-2"><ShieldCheck className="h-5 w-5 text-[#B45309]" />Data Check</h3>
          <p className="text-sm text-muted-foreground max-w-2xl">Looks for records that break the app's rules — for example from older versions, imports or direct database edits. It only reads; nothing is changed.</p>
        </div>
        <Button onClick={run} disabled={running} variant="outline" data-testid="btn-run-data-check">
          {running ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <ShieldCheck className="h-4 w-4 mr-2" />}Run Data Check
        </Button>
      </div>
      {result && (
        result.issue_count === 0 ? (
          <div className="flex items-center gap-2 rounded-lg bg-[#F0FDF4] text-[#15803D] px-3 py-2 text-sm" data-testid="data-check-clean">
            <ShieldCheck className="h-4 w-4" /> No problems found in {c.transactions} transactions, {c.fund_activity} fund moves, {c.accounts} accounts and {c.funds} funds.
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-start gap-2 rounded-lg bg-[#FFFBEB] text-[#B45309] px-3 py-2 text-sm">
              <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" /> {result.issue_count} problem{result.issue_count === 1 ? "" : "s"} found. These need a decision on how to correct each one; nothing has been changed.
            </div>
            <div className="overflow-x-auto border-t border-[#EEEDE7]">
              <table className="w-full text-sm" data-testid="data-check-issues">
                <thead><tr className="text-left text-slate-500 border-b border-[#EEEDE7]">
                  <th className="py-2 pr-3 font-medium">Record</th><th className="py-2 pr-3 font-medium">Date</th><th className="py-2 pr-3 font-medium">Account</th>
                  <th className="py-2 pr-3 font-medium text-right">Amount</th><th className="py-2 pr-3 font-medium">Memo / Name</th><th className="py-2 font-medium">Problem</th>
                </tr></thead>
                <tbody>
                  {result.issues.map((i, n) => (
                    <tr key={`${i.id}-${n}`} className="border-b border-[#F4F0E8] align-top">
                      <td className="py-2 pr-3 capitalize whitespace-nowrap">{i.kind}</td>
                      <td className="py-2 pr-3 font-mono whitespace-nowrap">{i.date || "—"}</td>
                      <td className="py-2 pr-3 whitespace-nowrap">{i.account || "—"}</td>
                      <td className="py-2 pr-3 text-right font-mono whitespace-nowrap">{i.amount ?? "—"}</td>
                      <td className="py-2 pr-3 text-slate-600">{i.memo || "—"}</td>
                      <td className="py-2 text-[#B91C1C]">{i.problem}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )
      )}
    </Card>
  );
}

function AuditLog() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const load = () => {
    setLoading(true);
    api.get("/security/audit?limit=200").then((r) => setRows(r.data)).catch(() => {}).finally(() => setLoading(false));
  };
  useEffect(load, []);
  const when = (iso) => new Date(iso).toLocaleString([], { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
  return (
    <Card className="p-5 mt-4">
      <div className="flex items-center justify-between gap-3 mb-4">
        <div>
          <h3 className="font-serif text-lg font-semibold text-slate-900 flex items-center gap-2"><History className="h-5 w-5 text-[#B45309]" />Activity Log</h3>
          <p className="text-sm text-muted-foreground">Who added, changed, reset, signed out or removed users and roles, and when.</p>
        </div>
        <Button variant="outline" size="icon" onClick={load} title="Refresh" data-testid="audit-refresh"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /></Button>
      </div>
      <div className="overflow-x-auto border-t border-[#EEEDE7]">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 border-b border-[#EEEDE7]">
              <th className="py-2 pr-3 font-medium">When</th>
              <th className="py-2 pr-3 font-medium">Who</th>
              <th className="py-2 pr-3 font-medium">Action</th>
              <th className="py-2 pr-3 font-medium">Affected</th>
              <th className="py-2 font-medium">Details</th>
            </tr>
          </thead>
          <tbody>
            {!loading && rows.length === 0 && <tr><td colSpan={5} className="py-6 text-center text-muted-foreground">No activity recorded yet.</td></tr>}
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-[#F4F0E8] align-top" data-testid={`audit-row-${r.id}`}>
                <td className="py-2 pr-3 whitespace-nowrap">{when(r.at)}</td>
                <td className="py-2 pr-3 break-all">{r.actor_email || "—"}</td>
                <td className="py-2 pr-3 whitespace-nowrap font-medium">{AUDIT_LABELS[r.action] || r.action}</td>
                <td className="py-2 pr-3 break-all">{r.target_email || "—"}</td>
                <td className="py-2 text-slate-600">{r.details || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function SecurityTab() {
  const [days, setDays] = useState("7");
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const load = () => {
    setLoading(true);
    api.get(`/security/login-attempts?days=${days}`)
      .then((r) => setGroups(r.data.groups))
      .catch((e) => toast.error(formatApiErrorDetail(e.response?.data?.detail)))
      .finally(() => setLoading(false));
  };
  useEffect(load, [days]); // eslint-disable-line react-hooks/exhaustive-deps

  const unlock = async (body, label) => {
    try {
      await api.post("/security/login-attempts/clear", body);
      toast.success(`Unlocked ${label}`);
      load();
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
  };
  const when = (iso) => new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  const time = (iso) => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const lockedCount = groups.filter((g) => g.locked_until).length;

  return (
    <Card className="p-5 mt-4">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h3 className="font-serif text-lg font-semibold text-slate-900">Failed Sign-ins</h3>
          <p className="text-sm text-muted-foreground">
            After 5 wrong passwords from the same computer, that email is locked from there for 15 minutes.
            20 failures from one IP address locks that address. Unlock someone here if they're stuck.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={days} onValueChange={setDays}>
            <SelectTrigger className="w-36" data-testid="security-days"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="1">Last 24 hours</SelectItem>
              <SelectItem value="7">Last 7 days</SelectItem>
              <SelectItem value="30">Last 30 days</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" size="icon" onClick={load} title="Refresh" data-testid="security-refresh"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /></Button>
        </div>
      </div>
      {lockedCount > 0 && (
        <div className="mb-3 flex items-center gap-2 rounded-lg bg-[#FEF2F2] text-[#B91C1C] px-3 py-2 text-sm">
          <Lock className="h-4 w-4" /> {lockedCount} sign-in{lockedCount === 1 ? " is" : "s are"} locked right now.
        </div>
      )}
      <div className="overflow-x-auto border-t border-[#EEEDE7]">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 border-b border-[#EEEDE7]">
              <th className="py-2 font-medium">Email tried</th>
              <th className="py-2 font-medium">IP address</th>
              <th className="py-2 pr-3 font-medium text-right">Failures</th>
              <th className="py-2 pl-2 font-medium">Last attempt</th>
              <th className="py-2 font-medium">Status</th>
              <th className="py-2"></th>
            </tr>
          </thead>
          <tbody>
            {!loading && groups.length === 0 && (
              <tr><td colSpan={6} className="py-6 text-center text-muted-foreground">No failed sign-ins in this period.</td></tr>
            )}
            {groups.map((g) => (
              <tr key={`${g.email}|${g.ip}`} className="border-b border-[#F4F0E8]" data-testid={`security-row-${g.email}-${g.ip}`}>
                <td className="py-2 pr-3 break-all">{g.email}</td>
                <td className="py-2 pr-3 font-mono text-xs whitespace-nowrap" title={g.user_agent}>{g.ip}</td>
                <td className="py-2 pr-3 text-right font-mono">{g.failures}</td>
                <td className="py-2 pl-2 pr-3 whitespace-nowrap">{when(g.last_attempt)}</td>
                <td className="py-2 pr-3 whitespace-nowrap">
                  {g.locked_until
                    ? <Badge variant="outline" className="bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]">Locked until {time(g.locked_until)}</Badge>
                    : <span className="text-muted-foreground">—</span>}
                </td>
                <td className="py-2 text-right whitespace-nowrap">
                  {g.locked_until && (
                    <>
                      <Button variant="ghost" size="sm" onClick={() => unlock({ email: g.email, ip: g.ip }, g.email)} data-testid={`btn-unlock-${g.email}-${g.ip}`}><Unlock className="h-4 w-4 mr-1" />Unlock</Button>
                      <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={() => unlock({ ip: g.ip }, g.ip)} title="Clear all failures from this IP address">Unlock IP</Button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function UsersTab({ me }) {
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [deleteId, setDeleteId] = useState(null);
  const [form, setForm] = useState({ name: "", email: "", password: "", role_id: "" });
  const load = () => api.get("/auth/users").then((r) => setUsers(r.data));
  useEffect(() => { load(); api.get("/roles").then((r) => setRoles(r.data)); }, []);

  const openNew = () => { setEditing(null); setForm({ name: "", email: "", password: "", role_id: "" }); setOpen(true); };
  const openEdit = (u) => { setEditing(u); setForm({ name: u.name, email: u.email, password: "", role_id: u.role_id || "" }); setOpen(true); };

  const save = async () => {
    if (form.password && !strongPw(form.password)) return toast.error(PW_HINT);
    try {
      if (editing) {
        const body = { name: form.name, role_id: form.role_id || null };
        if (form.password) body.password = form.password;
        await api.put(`/auth/users/${editing.id}`, body);
        toast.success("User updated");
      } else {
        if (!strongPw(form.password)) return toast.error(PW_HINT);
        await api.post("/auth/users", { name: form.name, email: form.email, password: form.password, role_id: form.role_id || null });
        toast.success("User added");
      }
      setOpen(false); load();
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
  };
  const doDelete = async () => {
    try { await api.delete(`/auth/users/${deleteId}`); toast.success("User removed"); load(); }
    catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
    setDeleteId(null);
  };
  const signOutUser = async (u) => {
    try { await api.post(`/auth/users/${u.id}/sign-out`); toast.success(`${u.name} has been signed out everywhere`); }
    catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
  };
  const editingSelf = editing && editing.id === me.id;

  return (
    <Card className="p-5 mt-4">
      <div className="flex items-center justify-between mb-4">
        <div><h3 className="font-serif text-lg font-semibold text-slate-900">Users</h3><p className="text-sm text-muted-foreground">People who can log in, each with a role that limits what they can do.</p></div>
        <Button size="sm" onClick={openNew} className="bg-[#D97706] hover:bg-[#B45309]" data-testid="btn-add-user"><Plus className="h-4 w-4 mr-1.5" />Add User</Button>
      </div>
      <div className="divide-y divide-[#EEEDE7] border-t border-[#EEEDE7]">
        {users.map((u) => (
          <div key={u.id} className="flex items-center justify-between py-3" data-testid={`user-row-${u.id}`}>
            <div>
              <div className="font-medium text-slate-800">{u.name} {u.id === me.id && <span className="text-xs text-muted-foreground">(you)</span>}</div>
              <div className="text-xs text-muted-foreground">{u.email}</div>
            </div>
            <div className="flex items-center gap-3">
              {u.must_change_password && <Badge variant="outline" className="bg-[#FFFBEB] text-[#B45309] border-[#FDE68A]" title="Signed in with a temporary password; must choose a new one">Temporary password</Badge>}
              <Badge variant="outline" className={u.role === "admin" ? "text-[#B45309] border-[#FEF3C7]" : ""}>{u.role_name || "—"}</Badge>
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEdit(u)} data-testid={`btn-edit-user-${u.id}`}><Pencil className="h-4 w-4" /></Button>
              {u.id !== me.id && <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => signOutUser(u)} title="Sign out of all devices" data-testid={`btn-signout-user-${u.id}`}><LogOut className="h-4 w-4" /></Button>}
              {u.id !== me.id && <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={() => setDeleteId(u.id)} data-testid={`btn-delete-user-${u.id}`}><Trash2 className="h-4 w-4" /></Button>}
            </div>
          </div>
        ))}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid="user-dialog">
          <DialogHeader><DialogTitle className="font-serif">{editing ? "Edit User" : "Add User"}</DialogTitle>
            <DialogDescription>{editing ? (editingSelf ? "Update your name or role. Change your own password from your account menu." : "Update this user's name or role, or give them a temporary password.") : "Create a login with a temporary password. They'll choose their own the first time they sign in."}</DialogDescription></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5"><Label>Name</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="user-name-input" /></div>
            <div className="space-y-1.5"><Label>Email</Label><Input type="email" value={form.email} disabled={!!editing} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="user-email-input" /></div>
            {!editingSelf && (
              <div className="space-y-1.5">
                <Label>{editing ? "Reset password (leave blank to keep)" : "Temporary password"}</Label>
                <Input type="password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder={editing ? "••••••••" : ""} data-testid="user-password-input" />
                <p className="text-xs text-muted-foreground">{PW_HINT} {editing ? "Resetting signs them out everywhere, and they must choose a new password at next sign-in." : "They must change it at first sign-in."}</p>
              </div>
            )}
            <div className="space-y-1.5"><Label>Role</Label>
              <Select value={form.role_id} onValueChange={(v) => setForm({ ...form, role_id: v })}>
                <SelectTrigger data-testid="user-role-select"><SelectValue placeholder="Choose a role" /></SelectTrigger>
                <SelectContent>{roles.map((r) => <SelectItem key={r.id} value={r.id}>{r.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button><Button onClick={save} className="bg-[#1E293B] hover:bg-[#0F172A]" data-testid="btn-save-user">{editing ? "Save Changes" : "Add User"}</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleteId} onOpenChange={(o) => !o && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>Remove this user?</AlertDialogTitle><AlertDialogDescription>They will no longer be able to log in.</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={doDelete} className="bg-destructive hover:bg-destructive/90" data-testid="confirm-delete-user">Remove</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}

function EmailBackupCard() {
  const [cfg, setCfg] = useState(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => { api.get("/settings/email").then((r) => setCfg(r.data)).catch(() => {}); }, []);
  if (!cfg) return null;
  const set = (k, v) => setCfg({ ...cfg, [k]: v });

  const save = async () => {
    setSaving(true);
    try {
      const body = {
        enabled: cfg.enabled, smtp_host: cfg.smtp_host || "", smtp_port: Number(cfg.smtp_port || 587),
        smtp_username: cfg.smtp_username || "", use_tls: cfg.use_tls, from_address: cfg.from_address || "", to_address: cfg.to_address || "",
        notify_users: cfg.notify_users !== false,
      };
      if (cfg.smtp_password) body.smtp_password = cfg.smtp_password;
      await api.put("/settings/email", body);
      const { data } = await api.get("/settings/email");
      setCfg(data);
      toast.success("Email settings saved");
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  const sendTest = async () => {
    setTesting(true);
    try { await api.post("/email/test"); toast.success("Test email sent — check the inbox"); }
    catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
    finally { setTesting(false); }
  };

  return (
    <Card className="p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div><h3 className="font-serif text-lg font-semibold text-slate-900 flex items-center gap-2"><Mail className="h-5 w-5 text-[#B45309]" />Email Backups</h3>
          <p className="text-sm text-muted-foreground">Automatically email each nightly backup to the treasurer for off-site safekeeping, using your own email (SMTP) account. Only encrypted backups are emailed.</p></div>
        <label className="flex items-center gap-2 cursor-pointer">
          <span className="text-sm text-muted-foreground">Enabled</span>
          <Switch checked={!!cfg.enabled} onCheckedChange={(v) => set("enabled", v)} data-testid="email-enabled-switch" />
        </label>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5"><Label>SMTP Host</Label><Input value={cfg.smtp_host || ""} onChange={(e) => set("smtp_host", e.target.value)} placeholder="smtp.gmail.com" data-testid="email-host-input" /></div>
        <div className="space-y-1.5"><Label>Port</Label><Input type="number" value={cfg.smtp_port || 587} onChange={(e) => set("smtp_port", e.target.value)} placeholder="587" data-testid="email-port-input" /></div>
        <div className="space-y-1.5"><Label>Username</Label><Input value={cfg.smtp_username || ""} onChange={(e) => set("smtp_username", e.target.value)} placeholder="you@gmail.com" data-testid="email-username-input" /></div>
        <div className="space-y-1.5"><Label>Password {cfg.has_password && <span className="text-xs text-muted-foreground">(saved — leave blank to keep)</span>}</Label><Input type="password" value={cfg.smtp_password || ""} onChange={(e) => set("smtp_password", e.target.value)} placeholder={cfg.has_password ? "••••••••" : "app password"} data-testid="email-password-input" /></div>
        <div className="space-y-1.5"><Label>From Address</Label><Input value={cfg.from_address || ""} onChange={(e) => set("from_address", e.target.value)} placeholder="treasury@yourchurch.org" data-testid="email-from-input" /></div>
        <div className="space-y-1.5"><Label>Send To (treasurer)</Label><Input value={cfg.to_address || ""} onChange={(e) => set("to_address", e.target.value)} placeholder="treasurer@yourchurch.org" data-testid="email-to-input" /></div>
      </div>
      <label className="flex items-center gap-2 cursor-pointer w-fit">
        <Switch checked={cfg.use_tls !== false} onCheckedChange={(v) => set("use_tls", v)} data-testid="email-tls-switch" />
        <span className="text-sm">Use STARTTLS (recommended for port 587; use port 465 for SSL)</span>
      </label>
      <label className="flex items-start gap-2 cursor-pointer w-fit">
        <Switch checked={cfg.notify_users !== false} onCheckedChange={(v) => set("notify_users", v)} className="mt-0.5" data-testid="email-notify-users-switch" />
        <span className="text-sm">
          Email users when their account changes
          <span className="block text-xs text-muted-foreground">New account, password reset, role change, or password changed. Uses these SMTP settings; passwords are never included.</span>
        </span>
      </label>
      <div className="flex flex-wrap gap-3">
        <Button onClick={save} disabled={saving} className="bg-[#1E293B] hover:bg-[#0F172A]" data-testid="btn-save-email-cfg">
          {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}Save Email Settings
        </Button>
        <Button onClick={sendTest} disabled={testing} variant="outline" data-testid="btn-send-test-email">
          {testing ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Send className="h-4 w-4 mr-2" />}Send Test Email
        </Button>
      </div>
    </Card>
  );
}

function BackupEncryptionCard({ status, onChange }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ pass: "", confirm: "", saved: false });
  const [saving, setSaving] = useState(false);
  const enabled = !!status?.enabled;

  const save = async () => {
    if (form.pass.length < 12) return toast.error("Use at least 12 characters — a few unrelated words works well");
    if (form.pass !== form.confirm) return toast.error("The passphrases don't match");
    if (!form.saved) return toast.error("Please confirm you've written the passphrase down somewhere safe");
    setSaving(true);
    try {
      const { data } = await api.put("/settings/backup-encryption", { passphrase: form.pass });
      onChange(data);
      setOpen(false); setForm({ pass: "", confirm: "", saved: false });
      toast.success(enabled ? "Backup passphrase changed" : "Backups will now be encrypted");
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  return (
    <Card className={`p-5 space-y-3 ${enabled ? "" : "border-[#FCA5A5]"}`} data-testid="backup-encryption-card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-serif text-lg font-semibold text-slate-900 flex items-center gap-2"><Lock className="h-5 w-5 text-[#B45309]" />Backup Encryption</h3>
          <p className="text-sm text-muted-foreground max-w-2xl">
            Encrypts every backup — nightly, downloaded and emailed — with a passphrase only you know. Restoring an encrypted backup asks for it.
          </p>
        </div>
        {enabled
          ? <Badge variant="outline" className="bg-[#F0FDF4] text-[#15803D] border-[#BBF7D0]" data-testid="backup-encryption-on"><Lock className="h-3.5 w-3.5 mr-1" />On{status.set_at ? ` · set ${new Date(status.set_at).toLocaleDateString()}` : ""}</Badge>
          : <Badge variant="outline" className="bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]" data-testid="backup-encryption-off">Off</Badge>}
      </div>
      {!enabled && (
        <div className="flex items-start gap-2 text-sm text-[#B91C1C] bg-[#FEF2F2] rounded-lg p-3">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
          <span>Backups are <b>not encrypted</b> and contain all financial data and password hashes. Emailing backups is paused until you set a passphrase.</span>
        </div>
      )}
      {!open ? (
        <Button onClick={() => setOpen(true)} className="bg-[#1E293B] hover:bg-[#0F172A]" data-testid="btn-set-passphrase">
          <Lock className="h-4 w-4 mr-2" />{enabled ? "Change Passphrase" : "Set Backup Passphrase"}
        </Button>
      ) : (
        <div className="space-y-3 rounded-lg border border-[#E5E0D8] bg-[#FAF8F3] p-4 max-w-xl">
          <div className="flex items-start gap-2 text-xs text-[#B45309]">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span><b>If this passphrase is lost, encrypted backups cannot be opened by anyone.</b> Write it down and keep it somewhere safe away from this server (for example, with the church's important papers).{enabled && " Backups made before a change still need the passphrase that was in use when they were made."}</span>
          </div>
          <div className="space-y-1.5"><Label>Passphrase</Label><Input type="password" autoComplete="new-password" value={form.pass} onChange={(e) => setForm({ ...form, pass: e.target.value })} placeholder="e.g. four unrelated words" data-testid="passphrase-input" /></div>
          <div className="space-y-1.5"><Label>Confirm passphrase</Label><Input type="password" autoComplete="new-password" value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} data-testid="passphrase-confirm-input" /></div>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <Checkbox checked={form.saved} onCheckedChange={(v) => setForm({ ...form, saved: !!v })} data-testid="passphrase-saved-check" />
            I've written this passphrase down somewhere safe
          </label>
          <div className="flex gap-2">
            <Button onClick={save} disabled={saving} className="bg-[#1E293B] hover:bg-[#0F172A]" data-testid="btn-save-passphrase">
              {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}Save Passphrase
            </Button>
            <Button variant="outline" onClick={() => { setOpen(false); setForm({ pass: "", confirm: "", saved: false }); }}>Cancel</Button>
          </div>
        </div>
      )}
    </Card>
  );
}

const filenameFrom = (res, fallback) => {
  const m = /filename=([^;]+)/i.exec(res.headers?.["content-disposition"] || "");
  return m ? m[1].trim().replace(/"/g, "") : fallback;
};

function BackupTab() {
  const [exporting, setExporting] = useState(false);
  const [file, setFile] = useState(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [importing, setImporting] = useState(false);
  const [cfg, setCfg] = useState(null);
  const [savingCfg, setSavingCfg] = useState(false);
  const [backups, setBackups] = useState([]);
  const [running, setRunning] = useState(false);
  const [restoreName, setRestoreName] = useState(null);
  const [encStatus, setEncStatus] = useState(null);
  const [filePass, setFilePass] = useState("");
  const [restorePass, setRestorePass] = useState("");
  const restoreEncrypted = !!restoreName && restoreName.endsWith("-enc.json");

  const loadBackups = () => api.get("/backups").then((r) => setBackups(r.data)).catch(() => {});
  useEffect(() => {
    api.get("/settings/backup").then((r) => setCfg(r.data)).catch(() => {});
    api.get("/settings/backup-encryption").then((r) => setEncStatus(r.data)).catch(() => {});
    loadBackups();
  }, []);

  const doExport = async () => {
    setExporting(true);
    try {
      const res = await api.get("/data/export", { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/json" }));
      const a = document.createElement("a");
      a.href = url; a.download = filenameFrom(res, `church-treasury-backup-${new Date().toISOString().slice(0, 10)}.json`); a.click();
      window.URL.revokeObjectURL(url);
      toast.success("Backup downloaded");
    } catch { toast.error("Could not export backup"); }
    finally { setExporting(false); }
  };

  const doImport = async () => {
    if (!file) return;
    setImporting(true); setConfirmOpen(false);
    try {
      const fd = new FormData(); fd.append("file", file);
      if (filePass) fd.append("passphrase", filePass);
      await api.post("/data/import", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Backup restored. Please sign in again.");
      setTimeout(() => { localStorage.removeItem("ct_token"); window.location.href = "/login"; }, 1500);
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
    finally { setImporting(false); }
  };

  const saveCfg = async () => {
    setSavingCfg(true);
    try {
      const { data } = await api.put("/settings/backup", { enabled: cfg.enabled, time: cfg.time, retention: Number(cfg.retention) });
      setCfg({ ...cfg, ...data });
      toast.success("Backup schedule saved");
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
    finally { setSavingCfg(false); }
  };

  const runNow = async () => {
    setRunning(true);
    try {
      const { data } = await api.post("/backups/run");
      if (data.encrypted) toast.success("Encrypted backup created"); else toast.warning("Backup created, but it is NOT encrypted — set a backup passphrase");
      loadBackups();
    }
    catch { toast.error("Could not create backup"); }
    finally { setRunning(false); }
  };

  const downloadServer = async (name) => {
    try {
      const res = await api.get(`/backups/${name}/download`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/json" }));
      const a = document.createElement("a"); a.href = url; a.download = name; a.click();
      window.URL.revokeObjectURL(url);
    } catch { toast.error("Could not download"); }
  };

  const deleteServer = async (name) => {
    try { await api.delete(`/backups/${name}`); toast.success("Backup deleted"); loadBackups(); }
    catch { toast.error("Could not delete"); }
  };

  const doRestoreServer = async () => {
    const name = restoreName; const passphrase = restorePass;
    setRestoreName(null); setRestorePass("");
    try {
      await api.post(`/backups/${name}/restore`, passphrase ? { passphrase } : {});
      toast.success("Restored. Please sign in again.");
      setTimeout(() => { localStorage.removeItem("ct_token"); window.location.href = "/login"; }, 1500);
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
  };

  const fmtSize = (b) => (b > 1024 * 1024 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);

  return (
    <div className="mt-4 space-y-5">
      {encStatus && <BackupEncryptionCard status={encStatus} onChange={setEncStatus} />}
      <div className="grid gap-5 md:grid-cols-2">
        <Card className="p-5 space-y-3">
          <h3 className="font-serif text-lg font-semibold text-slate-900">Export (Backup)</h3>
          <p className="text-sm text-muted-foreground">Download a complete backup of all accounts, transactions, users, roles, and settings{encStatus?.enabled ? ", encrypted with your backup passphrase" : ""}. The email (SMTP) password is never included.</p>
          <Button onClick={doExport} disabled={exporting} className="bg-[#1E293B] hover:bg-[#0F172A]" data-testid="btn-export-data">
            {exporting ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Download className="h-4 w-4 mr-2" />}Download Backup
          </Button>
        </Card>

        <Card className="p-5 space-y-3">
          <h3 className="font-serif text-lg font-semibold text-slate-900">Restore (Import)</h3>
          <p className="text-sm text-muted-foreground">Restore from a backup file. This <b>replaces all current data</b> and signs you out.</p>
          <div className="flex items-start gap-2 text-xs text-[#B45309] bg-[#FEF3C7]/50 rounded-lg p-2.5">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" /> Restoring overwrites everything. Export a backup first if unsure.
          </div>
          <label className="flex items-center justify-center gap-2 border-2 border-dashed border-[#E5E0D8] rounded-lg py-4 cursor-pointer hover:bg-[#FAF8F3] text-sm" data-testid="import-data-dropzone">
            <Upload className="h-4 w-4" /> {file ? file.name : "Choose a backup file (.json)"}
            <input type="file" accept=".json,application/json" className="hidden" onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid="import-data-input" />
          </label>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Backup passphrase (only if the file is encrypted)</Label>
            <Input type="password" autoComplete="off" value={filePass} onChange={(e) => setFilePass(e.target.value)} data-testid="import-passphrase-input" />
          </div>
          <Button onClick={() => setConfirmOpen(true)} disabled={!file || importing} variant="destructive" data-testid="btn-restore-data">
            {importing ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Upload className="h-4 w-4 mr-2" />}Restore from File
          </Button>
        </Card>
      </div>

      {cfg && (
        <Card className="p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div><h3 className="font-serif text-lg font-semibold text-slate-900">Automatic Nightly Backups</h3>
              <p className="text-sm text-muted-foreground">Saved to <span className="font-mono text-xs">{cfg.backup_dir}</span> on the server.</p></div>
            <label className="flex items-center gap-2 cursor-pointer">
              <span className="text-sm text-muted-foreground">Enabled</span>
              <Switch checked={!!cfg.enabled} onCheckedChange={(v) => setCfg({ ...cfg, enabled: v })} data-testid="backup-enabled-switch" />
            </label>
          </div>
          <div className="flex flex-wrap items-end gap-4">
            <div className="space-y-1.5"><Label>Run daily at</Label><Input type="time" value={cfg.time} onChange={(e) => setCfg({ ...cfg, time: e.target.value })} className="w-36" data-testid="backup-time-input" /></div>
            <div className="space-y-1.5"><Label>Keep last (files)</Label><Input type="number" min="1" value={cfg.retention} onChange={(e) => setCfg({ ...cfg, retention: e.target.value })} className="w-28" data-testid="backup-retention-input" /></div>
            <Button onClick={saveCfg} disabled={savingCfg} className="bg-[#1E293B] hover:bg-[#0F172A]" data-testid="btn-save-backup-cfg">
              {savingCfg ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}Save Schedule
            </Button>
            <Button onClick={runNow} disabled={running} variant="outline" data-testid="btn-run-backup-now">
              {running ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Download className="h-4 w-4 mr-2" />}Back Up Now
            </Button>
          </div>
        </Card>
      )}

      <EmailBackupCard />

      <Card className="p-5">
        <h3 className="font-serif text-lg font-semibold text-slate-900 mb-3">Saved Backups on Server</h3>
        <div className="divide-y divide-[#EEEDE7] border-t border-[#EEEDE7]">
          {backups.length === 0 && <div className="py-6 text-sm text-muted-foreground text-center">No server backups yet. Use "Back Up Now" or wait for the nightly run.</div>}
          {backups.map((b) => (
            <div key={b.name} className="flex items-center justify-between py-3 gap-3" data-testid={`backup-row-${b.name}`}>
              <div className="min-w-0">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-mono text-sm text-slate-800 truncate">{b.name}</span>
                  {b.encrypted
                    ? <Badge variant="outline" className="shrink-0 bg-[#F0FDF4] text-[#15803D] border-[#BBF7D0]"><Lock className="h-3 w-3 mr-1" />Encrypted</Badge>
                    : <Badge variant="outline" className="shrink-0 bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]">Not encrypted</Badge>}
                </div>
                <div className="text-xs text-muted-foreground">{new Date(b.created_at).toLocaleString()} · {fmtSize(b.size)}</div>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <Button variant="ghost" size="sm" onClick={() => downloadServer(b.name)} data-testid={`btn-download-backup-${b.name}`}><Download className="h-4 w-4 mr-1" />Download</Button>
                <Button variant="ghost" size="sm" onClick={() => setRestoreName(b.name)} data-testid={`btn-restore-backup-${b.name}`}><Upload className="h-4 w-4 mr-1" />Restore</Button>
                <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={() => deleteServer(b.name)} data-testid={`btn-delete-backup-${b.name}`}><Trash2 className="h-4 w-4" /></Button>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>Replace all data?</AlertDialogTitle>
            <AlertDialogDescription>This permanently overwrites every account, transaction, user, and setting with the uploaded backup. You will be signed out afterward.</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={doImport} className="bg-destructive hover:bg-destructive/90" data-testid="confirm-restore">Yes, restore</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={!!restoreName} onOpenChange={(o) => { if (!o) { setRestoreName(null); setRestorePass(""); } }}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>Restore this backup?</AlertDialogTitle>
            <AlertDialogDescription>This replaces all current data with <span className="font-mono text-xs">{restoreName}</span> and signs everyone out.</AlertDialogDescription></AlertDialogHeader>
          {restoreEncrypted && (
            <div className="space-y-1.5">
              <Label>Backup passphrase</Label>
              <Input type="password" autoComplete="off" value={restorePass} onChange={(e) => setRestorePass(e.target.value)} placeholder="The passphrase in use when this backup was made" data-testid="restore-passphrase-input" />
            </div>
          )}
          <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={doRestoreServer} className="bg-destructive hover:bg-destructive/90" data-testid="confirm-restore-server">Yes, restore</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
