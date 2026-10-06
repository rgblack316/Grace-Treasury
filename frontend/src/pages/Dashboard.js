import { useEffect, useState } from "react";
import api from "@/lib/api";
import { money, fmtDate } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Link } from "react-router-dom";
import { Landmark, PiggyBank, TrendingUp, TrendingDown, ArrowLeftRight, Wallet } from "lucide-react";

export default function Dashboard() {
  const [data, setData] = useState(null);

  useEffect(() => {
    api.get("/dashboard").then((r) => setData(r.data));
  }, []);

  if (!data) return <div className="text-slate-500">Loading dashboard…</div>;

  const typeMeta = {
    income: { icon: TrendingUp, color: "text-[#15803D]", sign: "+" },
    expense: { icon: TrendingDown, color: "text-[#B91C1C]", sign: "−" },
    transfer: { icon: ArrowLeftRight, color: "text-[#1D4ED8]", sign: "" },
  };

  return (
    <div className="space-y-8" data-testid="dashboard-page">
      <div>
        <h1 className="font-serif text-3xl font-bold text-slate-900">Dashboard</h1>
        <p className="text-muted-foreground mt-1">An overview of your church's finances.</p>
      </div>

      <Card className="p-6 bg-[#1E293B] text-white border-0 flex items-center justify-between avoid-break">
        <div>
          <div className="text-xs uppercase tracking-wider text-slate-400 font-semibold flex items-center gap-2">
            <Wallet className="h-4 w-4" /> Total Across All Accounts
          </div>
          <div className="font-mono text-4xl font-bold mt-2" data-testid="total-balance">{money(data.total_balance)}</div>
        </div>
        <Landmark className="h-16 w-16 text-[#D97706] opacity-40 hidden sm:block" />
      </Card>

      <div>
        <h2 className="font-serif text-xl font-semibold text-slate-900 mb-4">Bank Accounts</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {data.accounts.map((a) => (
            <Link key={a.id} to={`/transactions?account=${a.id}`}>
              <Card className="p-5 hover:shadow-md transition-shadow border-[#E5E0D8]" data-testid={`account-card-${a.mask}`}>
                <div className="flex items-center justify-between">
                  <div className="h-10 w-10 rounded-lg bg-[#F4F0E8] grid place-items-center">
                    <Landmark className="h-5 w-5 text-[#1E293B]" />
                  </div>
                  <Badge variant="secondary" className="font-mono">{a.mask}</Badge>
                </div>
                <div className="mt-4 text-sm text-muted-foreground">{a.name}</div>
                <div className="font-mono text-2xl font-bold text-slate-900 mt-1">{money(a.balance)}</div>
              </Card>
            </Link>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div className="lg:col-span-2">
          <h2 className="font-serif text-xl font-semibold text-slate-900 mb-4">Fund Balances</h2>
          <Card className="divide-y divide-[#EEEDE7]">
            {data.funds.length === 0 && <div className="p-5 text-sm text-muted-foreground">No funds yet.</div>}
            {data.funds.map((f) => (
              <div key={f.id} className="flex items-center justify-between p-4" data-testid={`fund-row-${f.name}`} style={{ paddingLeft: 16 + (f.depth || 0) * 20 }}>
                <div className="flex items-center gap-3 min-w-0">
                  <div className="h-9 w-9 rounded-lg bg-[#FEF3C7] grid place-items-center shrink-0">
                    <PiggyBank className="h-4 w-4 text-[#B45309]" />
                  </div>
                  <div className="min-w-0">
                    <span className="text-sm font-medium text-slate-800">{f.depth ? "↳ " : ""}{f.name}</span>
                    {f.has_children ? <div className="text-xs text-muted-foreground">Own {money(f.balance)} · includes nested</div> : null}
                  </div>
                </div>
                <span className="font-mono font-semibold text-slate-900">{money(f.has_children ? f.rolled_balance : f.balance)}</span>
              </div>
            ))}
          </Card>
        </div>

        <div className="lg:col-span-3">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-serif text-xl font-semibold text-slate-900">Recent Activity</h2>
            <Link to="/transactions" className="text-sm text-[#B45309] hover:underline font-medium">View all</Link>
          </div>
          <Card className="divide-y divide-[#EEEDE7]">
            {data.recent.length === 0 && <div className="p-5 text-sm text-muted-foreground">No transactions yet.</div>}
            {data.recent.map((t) => {
              const m = typeMeta[t.type];
              return (
                <div key={t.id} className="flex items-center justify-between p-4" data-testid={`recent-txn-${t.id}`}>
                  <div className="flex items-center gap-3 min-w-0">
                    <m.icon className={`h-5 w-5 shrink-0 ${m.color}`} />
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-slate-800 truncate">
                        {t.payee_name || t.memo || (t.type === "transfer" ? "Transfer" : t.type === "income" ? "Deposit" : "Expense")}
                      </div>
                      <div className="text-xs text-muted-foreground">{fmtDate(t.date)} · {t.account_mask}</div>
                    </div>
                  </div>
                  <span className={`font-mono font-semibold ${m.color}`}>{m.sign}{money(t.amount)}</span>
                </div>
              );
            })}
          </Card>
        </div>
      </div>
    </div>
  );
}
