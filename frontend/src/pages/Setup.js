import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { formatApiErrorDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Landmark, Loader2, Check, X } from "lucide-react";

const rules = [
  { key: "len", label: "At least 12 characters", test: (p) => p.length >= 12 },
  { key: "upper", label: "An uppercase letter", test: (p) => /[A-Z]/.test(p) },
  { key: "lower", label: "A lowercase letter", test: (p) => /[a-z]/.test(p) },
  { key: "num", label: "A number", test: (p) => /\d/.test(p) },
  { key: "sym", label: "A symbol", test: (p) => /[^A-Za-z0-9]/.test(p) },
];

export default function Setup() {
  const { setup, needsSetup, ready } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", password: "", confirm: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (ready && !needsSetup) {
    navigate("/login", { replace: true });
  }

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const allPass = rules.every((r) => r.test(form.password));
  const match = form.password && form.password === form.confirm;

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (!allPass) return setError("Please meet all password requirements.");
    if (!match) return setError("Passwords do not match.");
    setLoading(true);
    try {
      await setup(form.name.trim(), form.email.trim().toLowerCase(), form.password);
      navigate("/");
    } catch (err) {
      setError(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-background">
      <div className="hidden lg:flex relative flex-col justify-between p-12 bg-[#1E293B] text-white overflow-hidden">
        <div className="relative z-10 flex items-center gap-3">
          <div className="h-11 w-11 rounded-xl bg-[#D97706] grid place-items-center">
            <Landmark className="h-6 w-6 text-white" />
          </div>
          <span className="font-serif text-xl font-semibold">Grace Treasury</span>
        </div>
        <div className="relative z-10 space-y-4 max-w-md">
          <h1 className="font-serif text-4xl font-bold leading-tight">Welcome — let's set up your treasury.</h1>
          <p className="text-slate-300 leading-relaxed">
            This is a fresh installation. Create your administrator (treasurer) account to get started.
            You'll be able to add bank accounts, funds, and additional users with their own roles afterward.
          </p>
        </div>
        <div className="relative z-10 text-sm text-slate-400">Self-hosted · Private · For your church only</div>
        <div className="absolute -right-24 -bottom-24 h-96 w-96 rounded-full opacity-20" style={{ background: "radial-gradient(circle, #D97706, transparent 70%)" }} />
      </div>

      <div className="flex items-center justify-center p-6 sm:p-12">
        <div className="w-full max-w-sm">
          <h2 className="font-serif text-2xl font-bold text-slate-900">Create Administrator Account</h2>
          <p className="text-sm text-muted-foreground mt-1 mb-6">The first account is the treasurer and can manage everything.</p>

          <form onSubmit={submit} className="space-y-4" data-testid="setup-form">
            <div className="space-y-1.5">
              <Label htmlFor="name">Your Name</Label>
              <Input id="name" value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Jane Smith" required data-testid="setup-name-input" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" value={form.email} onChange={(e) => set("email", e.target.value)} placeholder="you@church.org" required data-testid="setup-email-input" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input id="password" type="password" value={form.password} onChange={(e) => set("password", e.target.value)} placeholder="••••••••••••" required data-testid="setup-password-input" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="confirm">Confirm Password</Label>
              <Input id="confirm" type="password" value={form.confirm} onChange={(e) => set("confirm", e.target.value)} placeholder="••••••••••••" required data-testid="setup-confirm-input" />
            </div>

            <ul className="space-y-1 text-sm" data-testid="password-rules">
              {rules.map((r) => {
                const ok = r.test(form.password);
                return (
                  <li key={r.key} className={`flex items-center gap-2 ${ok ? "text-[#15803D]" : "text-muted-foreground"}`}>
                    {ok ? <Check className="h-4 w-4" /> : <X className="h-4 w-4" />} {r.label}
                  </li>
                );
              })}
              <li className={`flex items-center gap-2 ${match ? "text-[#15803D]" : "text-muted-foreground"}`}>
                {match ? <Check className="h-4 w-4" /> : <X className="h-4 w-4" />} Passwords match
              </li>
            </ul>

            {error && <p className="text-sm text-destructive" data-testid="setup-error">{error}</p>}
            <Button type="submit" className="w-full bg-[#1E293B] hover:bg-[#0F172A]" disabled={loading} data-testid="setup-submit-button">
              {loading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Create Account & Continue
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
