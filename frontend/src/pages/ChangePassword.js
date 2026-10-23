import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { formatApiErrorDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Landmark, Loader2, KeyRound } from "lucide-react";
import { toast } from "sonner";

const PW_HINT = "At least 12 characters with uppercase, lowercase, a number, and a symbol.";
const strongPw = (p) => p.length >= 12 && /[A-Z]/.test(p) && /[a-z]/.test(p) && /\d/.test(p) && /[^A-Za-z0-9]/.test(p);

export default function ChangePassword() {
  const { user, changePassword, logout } = useAuth();
  const navigate = useNavigate();
  const forced = !!user?.must_change_password;
  const [form, setForm] = useState({ current: "", next: "", confirm: "" });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (!strongPw(form.next)) return setError(PW_HINT);
    if (form.next !== form.confirm) return setError("The new passwords don't match.");
    setSaving(true);
    try {
      await changePassword(form.current, form.next);
      toast.success("Password changed. Any other devices have been signed out.");
      navigate("/", { replace: true });
    } catch (err) {
      setError(formatApiErrorDetail(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen grid place-items-center bg-background p-6">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-3 mb-8">
          <div className="h-10 w-10 rounded-xl bg-[#D97706] grid place-items-center">
            <Landmark className="h-5 w-5 text-white" />
          </div>
          <span className="font-serif text-lg font-semibold text-slate-900">Grace Treasury</span>
        </div>
        <h2 className="font-serif text-2xl font-bold text-slate-900 flex items-center gap-2">
          <KeyRound className="h-6 w-6 text-[#B45309]" /> {forced ? "Choose a new password" : "Change password"}
        </h2>
        <p className="text-sm text-muted-foreground mt-1 mb-6">
          {forced
            ? "Your password was set by someone else. Choose your own before continuing — only you will know it."
            : "Changing your password signs you out on every other computer and phone."}
        </p>

        <form onSubmit={submit} className="space-y-4" data-testid="change-password-form">
          <div className="space-y-1.5">
            <Label htmlFor="current">{forced ? "Temporary password" : "Current password"}</Label>
            <Input id="current" type="password" autoComplete="current-password" value={form.current} onChange={(e) => set("current", e.target.value)} required data-testid="current-password-input" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="next">New password</Label>
            <Input id="next" type="password" autoComplete="new-password" value={form.next} onChange={(e) => set("next", e.target.value)} required data-testid="new-password-input" />
            <p className="text-xs text-muted-foreground">{PW_HINT}</p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="confirm">Confirm new password</Label>
            <Input id="confirm" type="password" autoComplete="new-password" value={form.confirm} onChange={(e) => set("confirm", e.target.value)} required data-testid="confirm-password-input" />
          </div>
          {error && <p className="text-sm text-destructive" data-testid="change-password-error">{error}</p>}
          <Button type="submit" className="w-full" disabled={saving} data-testid="change-password-submit">
            {saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            Save new password
          </Button>
          <div className="text-center text-sm">
            {forced ? (
              <button type="button" onClick={logout} className="text-muted-foreground hover:underline">Sign out instead</button>
            ) : (
              <Link to="/" className="text-muted-foreground hover:underline">Cancel</Link>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
