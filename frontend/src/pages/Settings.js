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
import { Plus, Pencil, Trash2, Save, Download, Upload, ShieldCheck, Loader2, AlertTriangle, Mail, Send } from "lucide-react";

const PW_HINT = "At least 12 characters with uppercase, lowercase, a number, and a symbol.";
const strongPw = (p) => p.length >= 12 && /[A-Z]/.test(p) && /[a-z]/.test(p) && /\d/.test(p) && /[^A-Za-z0-9]/.test(p);

export default function Settings() {
  const { user, can } = useAuth();
  const canSettings = can("settings.manage");
  const canUsers = can("users.manage");
  const canData = can("data.manage");

  const available = [];
  if (canSettings) available.push("accounts", "funds", "categories", "payees", "coa", "church");
  if (canUsers) available.push("roles", "users");
  if (canData) available.push("backup");
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
            {canSettings && <TabsTrigger value="coa" data-testid="settings-tab-coa">Chart of Accounts</TabsTrigger>}
            {canSettings && <TabsTrigger value="church" data-testid="settings-tab-church">Church Info</TabsTrigger>}
            {canUsers && <TabsTrigger value="roles" data-testid="settings-tab-roles">Roles</TabsTrigger>}
            {canUsers && <TabsTrigger value="users" data-testid="settings-tab-users">Users</TabsTrigger>}
            {canData && <TabsTrigger value="backup" data-testid="settings-tab-backup">Backup & Restore</TabsTrigger>}
          </TabsList>

          {canSettings && <TabsContent value="accounts"><AccountsTab /></TabsContent>}
          {canSettings && <TabsContent value="funds"><FundsTab /></TabsContent>}
          {canSettings && <TabsContent value="categories"><CategoriesTab /></TabsContent>}
          {canSettings && <TabsContent value="payees"><PayeesTab /></TabsContent>}
          {canSettings && <TabsContent value="coa"><CoaTab /></TabsContent>}
          {canSettings && <TabsContent value="church"><ChurchTab /></TabsContent>}
          {canUsers && <TabsContent value="roles"><RolesTab /></TabsContent>}
          {canUsers && <TabsContent value="users"><UsersTab me={user} /></TabsContent>}
          {canData && <TabsContent value="backup"><BackupTab /></TabsContent>}
        </Tabs>
      )}
    </div>
  );
}

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
              <Label>{f.label}</Label>
              {f.type === "select" ? (
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
  const doDelete = async () => { await api.delete(`/${path}/${deleteId}`); toast.success(`${label} deleted`); setDeleteId(null); load(); };
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
            <div className="min-w-0">{columns(it)}</div>
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
          <AlertDialogHeader><AlertDialogTitle>Delete {label.toLowerCase()}?</AlertDialogTitle><AlertDialogDescription>This action cannot be undone.</AlertDialogDescription></AlertDialogHeader>
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
      ]}
      buildPayload={(f) => ({ name: f.name, mask: f.mask || "", opening_balance: Number(f.opening_balance || 0), opening_date: f.opening_date || "", active: true })}
    />
  );
}

function FundsTab() {
  const { items } = useCrud("funds");
  return (
    <ManagerCard title="Church Funds" description="Track money by purpose, independent of which account holds it."
      items={items} path="funds" label="Fund"
      columns={(f) => <div><div className="font-medium text-slate-800">{f.name}</div><div className="text-xs text-muted-foreground">{f.description || "—"}</div></div>}
      fields={[{ key: "name", label: "Fund Name", placeholder: "Building Fund" }, { key: "description", label: "Description", placeholder: "Optional" }]}
      buildPayload={(f) => ({ name: f.name, description: f.description || "", active: true })}
    />
  );
}

function CategoriesTab() {
  const { items } = useCrud("categories");
  return (
    <ManagerCard title="Categories" description="Group income and expenses for the summary report. Optional on each transaction."
      items={items} path="categories" label="Category"
      columns={(c) => <div className="flex items-center gap-2"><span className="font-medium text-slate-800">{c.name}</span><Badge variant="outline" className={`capitalize ${c.type === "income" ? "text-[#15803D] border-[#BBF7D0]" : "text-[#B91C1C] border-[#FECACA]"}`}>{c.type}</Badge></div>}
      fields={[{ key: "name", label: "Category Name", placeholder: "Utilities" }, { key: "type", label: "Type", type: "select", placeholder: "Choose type", options: [{ value: "income", label: "Income" }, { value: "expense", label: "Expense" }] }]}
      buildPayload={(f) => ({ name: f.name, type: f.type || "expense", active: true })}
    />
  );
}

function PayeesTab() {
  const { items } = useCrud("payees");
  return (
    <ManagerCard title="Payees & Vendors" description="A quick-pick list for recording expenses consistently."
      items={items} path="payees" label="Payee"
      columns={(p) => <div className="font-medium text-slate-800">{p.name}</div>}
      fields={[{ key: "name", label: "Payee / Vendor Name", placeholder: "Frontier Communications" }]}
      buildPayload={(f) => ({ name: f.name, active: true })}
    />
  );
}

function CoaTab() {
  const { items } = useCrud("coa");
  return (
    <ManagerCard title="Chart of Accounts" description="The standard accounting structure, seeded and fully editable."
      items={items} path="coa" label="Account"
      columns={(c) => <div className="flex items-center gap-2"><span className="font-mono text-sm text-muted-foreground">{c.code}</span><span className="font-medium text-slate-800">{c.name}</span><Badge variant="secondary">{c.group}</Badge></div>}
      fields={[
        { key: "code", label: "Code", placeholder: "5000" },
        { key: "name", label: "Name", placeholder: "Utilities" },
        { key: "group", label: "Group", type: "select", placeholder: "Choose group", options: ["Asset", "Liability", "Equity", "Income", "Expense"].map((g) => ({ value: g, label: g })) },
      ]}
      buildPayload={(f) => ({ code: f.code || "", name: f.name, group: f.group || "Expense", active: true })}
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
  const doDelete = async () => { await api.delete(`/auth/users/${deleteId}`); toast.success("User removed"); setDeleteId(null); load(); };

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
              <Badge variant="outline" className={u.role === "admin" ? "text-[#B45309] border-[#FEF3C7]" : ""}>{u.role_name || "—"}</Badge>
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEdit(u)} data-testid={`btn-edit-user-${u.id}`}><Pencil className="h-4 w-4" /></Button>
              {u.id !== me.id && <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={() => setDeleteId(u.id)} data-testid={`btn-delete-user-${u.id}`}><Trash2 className="h-4 w-4" /></Button>}
            </div>
          </div>
        ))}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid="user-dialog">
          <DialogHeader><DialogTitle className="font-serif">{editing ? "Edit User" : "Add User"}</DialogTitle>
            <DialogDescription>{editing ? "Update this user's name, role, or password." : "Create a login and assign a role."}</DialogDescription></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5"><Label>Name</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="user-name-input" /></div>
            <div className="space-y-1.5"><Label>Email</Label><Input type="email" value={form.email} disabled={!!editing} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="user-email-input" /></div>
            <div className="space-y-1.5"><Label>{editing ? "New Password (leave blank to keep)" : "Password"}</Label><Input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder={editing ? "••••••••" : ""} data-testid="user-password-input" /><p className="text-xs text-muted-foreground">{PW_HINT}</p></div>
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
          <p className="text-sm text-muted-foreground">Automatically email each nightly backup to the treasurer for off-site safekeeping, using your own email (SMTP) account.</p></div>
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

  const loadBackups = () => api.get("/backups").then((r) => setBackups(r.data)).catch(() => {});
  useEffect(() => {
    api.get("/settings/backup").then((r) => setCfg(r.data)).catch(() => {});
    loadBackups();
  }, []);

  const doExport = async () => {
    setExporting(true);
    try {
      const res = await api.get("/data/export", { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/json" }));
      const a = document.createElement("a");
      a.href = url; a.download = `church-treasury-backup-${new Date().toISOString().slice(0, 10)}.json`; a.click();
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
    try { await api.post("/backups/run"); toast.success("Backup created"); loadBackups(); }
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
    const name = restoreName; setRestoreName(null);
    try {
      await api.post(`/backups/${name}/restore`);
      toast.success("Restored. Please sign in again.");
      setTimeout(() => { localStorage.removeItem("ct_token"); window.location.href = "/login"; }, 1500);
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
  };

  const fmtSize = (b) => (b > 1024 * 1024 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);

  return (
    <div className="mt-4 space-y-5">
      <div className="grid gap-5 md:grid-cols-2">
        <Card className="p-5 space-y-3">
          <h3 className="font-serif text-lg font-semibold text-slate-900">Export (Backup)</h3>
          <p className="text-sm text-muted-foreground">Download a complete JSON backup of all accounts, transactions, users, roles, and settings.</p>
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
                <div className="font-mono text-sm text-slate-800 truncate">{b.name}</div>
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

      <AlertDialog open={!!restoreName} onOpenChange={(o) => !o && setRestoreName(null)}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>Restore this backup?</AlertDialogTitle>
            <AlertDialogDescription>This replaces all current data with <span className="font-mono text-xs">{restoreName}</span> and signs you out.</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={doRestoreServer} className="bg-destructive hover:bg-destructive/90" data-testid="confirm-restore-server">Yes, restore</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
