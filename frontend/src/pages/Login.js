import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { formatApiErrorDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Landmark, Loader2 } from "lucide-react";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email.trim().toLowerCase(), password);
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
          <h1 className="font-serif text-4xl font-bold leading-tight">
            Faithful stewardship, carefully recorded.
          </h1>
          <p className="text-slate-300 leading-relaxed">
            Track income, expenses, and transfers across your church accounts, and produce a
            clean treasurer's report ready for every business meeting.
          </p>
        </div>
        <div className="relative z-10 text-sm text-slate-400">
          Self-hosted · Private · For your church only
        </div>
        <div
          className="absolute -right-24 -bottom-24 h-96 w-96 rounded-full opacity-20"
          style={{ background: "radial-gradient(circle, #D97706, transparent 70%)" }}
        />
      </div>

      <div className="flex items-center justify-center p-6 sm:p-12">
        <div className="w-full max-w-sm">
          <div className="lg:hidden flex items-center gap-3 mb-8">
            <div className="h-10 w-10 rounded-xl bg-[#D97706] grid place-items-center">
              <Landmark className="h-5 w-5 text-white" />
            </div>
            <span className="font-serif text-lg font-semibold text-slate-900">Grace Treasury</span>
          </div>
          <h2 className="font-serif text-2xl font-bold text-slate-900">Welcome back</h2>
          <p className="text-sm text-muted-foreground mt-1 mb-6">Sign in to manage the church treasury.</p>

          <form onSubmit={submit} className="space-y-4" data-testid="login-form">
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@church.org"
                required
                data-testid="login-email-input"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                data-testid="login-password-input"
              />
            </div>
            {error && (
              <p className="text-sm text-destructive" data-testid="login-error">
                {error}
              </p>
            )}
            <Button type="submit" className="w-full" disabled={loading} data-testid="login-submit-button">
              {loading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Sign in
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
