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
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Plus, Pencil, Trash2, Save } from "lucide-react";

export default function Settings() {
  const { user } = useAuth();
  return (
    <div className="space-y-6" data-testid="settings-page">
      <div>
        <h1 className="font-serif text-3xl font-bold text-slate-900">Settings</h1>
        <p className="text-muted-foreground mt-1">Manage accounts, funds, categories, payees, and more.</p>
      </div>

      <Tabs defaultValue="accounts">
        <TabsList className="flex flex-wrap h-auto">
          <TabsTrigger value="accounts" data-testid="settings-tab-accounts">Bank Accounts</TabsTrigger>
          <TabsTrigger value="funds" data-testid="settings-tab-funds">Funds</TabsTrigger>
          <TabsTrigger value="categories" data-testid="settings-tab-categories">Categories</TabsTrigger>
          <TabsTrigger value="payees" data-testid="settings-tab-payees">Payees</TabsTrigger>
          <TabsTrigger value="coa" data-testid="settings-tab-coa">Chart of Accounts</TabsTrigger>
          <TabsTrigger value="church" data-testid="settings-tab-church">Church Info</TabsTrigger>
          {user?.role === "admin" && <TabsTrigger value="users" data-testid="settings-tab-users">Users</TabsTrigger>}
        </TabsList>

        <TabsContent value="accounts"><AccountsTab /></TabsContent>
        <TabsContent value="funds"><FundsTab /></TabsContent>
        <TabsContent value="categories"><CategoriesTab /></TabsContent>
        <TabsContent value="payees"><PayeesTab /></TabsContent>
        <TabsContent value="coa"><CoaTab /></TabsContent>
        <TabsContent value="church"><ChurchTab /></TabsContent>
        {user?.role === "admin" && <TabsContent value="users"><UsersTab me={user} /></TabsContent>}
      </Tabs>
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
        <DialogHeader><DialogTitle className="font-serif">{title}</DialogTitle></DialogHeader>
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
                <Input
                  type={f.type || "text"}
                  value={form[f.key] ?? ""}
                  onChange={(e) => set(f.key, f.type === "number" ? e.target.value : e.target.value)}
                  placeholder={f.placeholder}
                  data-testid={`crud-${f.key}`}
                />
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
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };
  const doDelete = async () => {
    await api.delete(`/${path}/${deleteId}`);
    toast.success(`${label} deleted`); setDeleteId(null); load();
  };

  return (
    <Card className="p-5 mt-4">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="font-serif text-lg font-semibold text-slate-900">{title}</h3>
          <p className="text-sm text-muted-foreground">{description}</p>
        </div>
        <Button size="sm" onClick={() => { setEditing(null); setOpen(true); }} className="bg-[#D97706] hover:bg-[#B45309]" data-testid={`btn-add-${path}`}>
          <Plus className="h-4 w-4 mr-1.5" />Add
        </Button>
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
          <AlertDialogHeader><AlertDialogTitle>Delete {label.toLowerCase()}?</AlertDialogTitle>
            <AlertDialogDescription>This action cannot be undone.</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={doDelete} className="bg-destructive hover:bg-destructive/90" data-testid="confirm-delete">Delete</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}

function AccountsTab() {
  const { items } = useCrud("accounts");
  return (
    <ManagerCard
      title="Bank Accounts" description="Track checking and savings accounts. Opening balance seeds the running balance."
      items={items} path="accounts" label="Account"
      columns={(a) => (
        <div>
          <div className="font-medium text-slate-800">{a.name} <Badge variant="secondary" className="font-mono ml-1">{a.mask}</Badge></div>
          <div className="text-xs text-muted-foreground">Opening {money(a.opening_balance)} as of {a.opening_date || "—"}</div>
        </div>
      )}
      fields={[
        { key: "name", label: "Account Name", placeholder: "General Operating Checking" },
        { key: "mask", label: "Masked Number", placeholder: "*3217" },
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
    <ManagerCard
      title="Church Funds" description="Track money by purpose, independent of which account holds it."
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
    <ManagerCard
      title="Categories" description="Group income and expenses for the summary report. Optional on each transaction."
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
    <ManagerCard
      title="Payees & Vendors" description="A quick-pick list for recording expenses consistently."
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
    <ManagerCard
      title="Chart of Accounts" description="The standard accounting structure, seeded and fully editable."
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
      <div className="space-y-1.5"><Label>Treasurer Name <span className="text-muted-foreground font-normal">(appears on report)</span></Label><Input value={form.treasurer_name || ""} onChange={(e) => setForm({ ...form, treasurer_name: e.target.value })} placeholder="e.g. R. Black" data-testid="treasurer-name-input" /></div>
      <div className="space-y-1.5"><Label>Business Meeting Day <span className="text-muted-foreground font-normal">(optional)</span></Label><Input value={form.meeting_day || ""} onChange={(e) => setForm({ ...form, meeting_day: e.target.value })} placeholder="e.g. Last Wednesday" data-testid="meeting-day-input" /></div>
      <Button onClick={save} className="bg-[#1E293B] hover:bg-[#0F172A]" data-testid="btn-save-church"><Save className="h-4 w-4 mr-2" />Save</Button>
    </Card>
  );
}

function UsersTab({ me }) {
  const [users, setUsers] = useState([]);
  const [open, setOpen] = useState(false);
  const [deleteId, setDeleteId] = useState(null);
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "user" });
  const load = () => api.get("/auth/users").then((r) => setUsers(r.data));
  useEffect(() => { load(); }, []);

  const create = async () => {
    try {
      await api.post("/auth/users", form);
      toast.success("User added");
      setOpen(false); setForm({ name: "", email: "", password: "", role: "user" }); load();
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail)); }
  };
  const doDelete = async () => { await api.delete(`/auth/users/${deleteId}`); toast.success("User removed"); setDeleteId(null); load(); };

  return (
    <Card className="p-5 mt-4">
      <div className="flex items-center justify-between mb-4">
        <div><h3 className="font-serif text-lg font-semibold text-slate-900">Users</h3><p className="text-sm text-muted-foreground">People who can log in. Only the treasurer can manage users.</p></div>
        <Button size="sm" onClick={() => setOpen(true)} className="bg-[#D97706] hover:bg-[#B45309]" data-testid="btn-add-user"><Plus className="h-4 w-4 mr-1.5" />Add User</Button>
      </div>
      <div className="divide-y divide-[#EEEDE7] border-t border-[#EEEDE7]">
        {users.map((u) => (
          <div key={u.id} className="flex items-center justify-between py-3" data-testid={`user-row-${u.id}`}>
            <div>
              <div className="font-medium text-slate-800">{u.name} {u.id === me.id && <span className="text-xs text-muted-foreground">(you)</span>}</div>
              <div className="text-xs text-muted-foreground">{u.email}</div>
            </div>
            <div className="flex items-center gap-3">
              <Badge variant="outline" className={u.role === "admin" ? "text-[#B45309] border-[#FEF3C7]" : ""}>{u.role === "admin" ? "Treasurer" : "User"}</Badge>
              {u.id !== me.id && <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={() => setDeleteId(u.id)} data-testid={`btn-delete-user-${u.id}`}><Trash2 className="h-4 w-4" /></Button>}
            </div>
          </div>
        ))}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid="add-user-dialog">
          <DialogHeader><DialogTitle className="font-serif">Add User</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5"><Label>Name</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="user-name-input" /></div>
            <div className="space-y-1.5"><Label>Email</Label><Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="user-email-input" /></div>
            <div className="space-y-1.5"><Label>Password</Label><Input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} data-testid="user-password-input" /></div>
            <div className="space-y-1.5"><Label>Role</Label>
              <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v })}>
                <SelectTrigger data-testid="user-role-select"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="user">User</SelectItem><SelectItem value="admin">Treasurer (Admin)</SelectItem></SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button><Button onClick={create} className="bg-[#1E293B] hover:bg-[#0F172A]" data-testid="btn-save-user">Add User</Button></DialogFooter>
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
