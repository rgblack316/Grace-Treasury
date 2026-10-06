import { useEffect, useState } from "react";
import api from "@/lib/api";
import { money, fmtDate, monthRange } from "@/lib/format";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Printer, Download, Loader2, FileText } from "lucide-react";

export default function Reports() {
  const [accounts, setAccounts] = useState([]);
  const [selected, setSelected] = useState([]);
  const [range, setRange] = useState(monthRange(0));
  const [includeCategory, setIncludeCategory] = useState(true);
  const [includeFunds, setIncludeFunds] = useState(true);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    api.get("/accounts").then((r) => {
      setAccounts(r.data);
      setSelected(r.data.map((a) => a.id));
    });
  }, []);

  const presets = [
    { label: "This Month", get: () => monthRange(0) },
    { label: "Last Month", get: () => monthRange(-1) },
    { label: "This Year", get: () => ({ start: `${new Date().getFullYear()}-01-01`, end: `${new Date().getFullYear()}-12-31` }) },
  ];

  const toggleAccount = (id) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const generate = async () => {
    if (selected.length === 0) return toast.error("Select at least one account");
    setLoading(true);
    try {
      const { data } = await api.get("/reports/treasurer", {
        params: { start: range.start, end: range.end, account_ids: selected.join(",") },
      });
      setReport(data);
    } catch (e) {
      toast.error("Could not generate report");
    } finally {
      setLoading(false);
    }
  };

  const downloadPdf = async () => {
    if (selected.length === 0) return toast.error("Select at least one account");
    setDownloading(true);
    try {
      const res = await api.get("/reports/treasurer/pdf", {
        params: {
          start: range.start,
          end: range.end,
          account_ids: selected.join(","),
          include_category: includeCategory,
          include_funds: includeFunds,
        },
        responseType: "blob",
      });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `treasurers-report-${range.start}-to-${range.end}.pdf`;
      a.click();
      window.URL.revokeObjectURL(url);
      toast.success("PDF downloaded");
    } catch (e) {
      toast.error("Could not download PDF");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="reports-page">
      <div className="no-print">
        <h1 className="font-serif text-3xl font-bold text-slate-900">Treasurer's Report</h1>
        <p className="text-muted-foreground mt-1">Choose a date range and accounts, then view, print, or download.</p>
      </div>

      {/* Controls */}
      <Card className="p-5 no-print space-y-5">
        <div>
          <Label className="text-xs uppercase tracking-wider text-slate-500 font-semibold">Date Range</Label>
          <div className="flex flex-wrap items-end gap-3 mt-2">
            <div className="space-y-1.5">
              <Label className="text-sm">Start</Label>
              <Input type="date" value={range.start} onChange={(e) => setRange((r) => ({ ...r, start: e.target.value }))} data-testid="report-start-date" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-sm">End</Label>
              <Input type="date" value={range.end} onChange={(e) => setRange((r) => ({ ...r, end: e.target.value }))} data-testid="report-end-date" />
            </div>
            <div className="flex gap-2">
              {presets.map((p) => (
                <Button key={p.label} variant="outline" size="sm" onClick={() => setRange(p.get())} data-testid={`report-preset-${p.label.toLowerCase().replace(/\s/g, "-")}`}>
                  {p.label}
                </Button>
              ))}
            </div>
          </div>
        </div>

        <div>
          <Label className="text-xs uppercase tracking-wider text-slate-500 font-semibold">Accounts</Label>
          <div className="flex flex-wrap gap-4 mt-2">
            {accounts.map((a) => (
              <label key={a.id} className="flex items-center gap-2 cursor-pointer" data-testid={`report-account-${a.mask}`}>
                <Checkbox checked={selected.includes(a.id)} onCheckedChange={() => toggleAccount(a.id)} />
                <span className="text-sm">{a.name} <span className="font-mono text-muted-foreground">{a.mask}</span></span>
              </label>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-5">
          <label className="flex items-center gap-2 cursor-pointer">
            <Checkbox checked={includeCategory} onCheckedChange={setIncludeCategory} data-testid="report-include-category" />
            <span className="text-sm">Include category summary</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <Checkbox checked={includeFunds} onCheckedChange={setIncludeFunds} data-testid="report-include-funds" />
            <span className="text-sm">Include fund balances</span>
          </label>
        </div>

        <div className="flex flex-wrap gap-3 pt-1">
          <Button onClick={generate} disabled={loading} className="bg-[#1E293B] hover:bg-[#0F172A]" data-testid="btn-generate-report">
            {loading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <FileText className="h-4 w-4 mr-2" />}
            Generate
          </Button>
          {report && (
            <>
              <Button variant="outline" onClick={() => window.print()} data-testid="btn-print-report">
                <Printer className="h-4 w-4 mr-2" /> Print
              </Button>
              <Button variant="outline" onClick={downloadPdf} disabled={downloading} data-testid="btn-download-pdf">
                {downloading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Download className="h-4 w-4 mr-2" />}
                Download PDF
              </Button>
            </>
          )}
        </div>
      </Card>

      {report && <ReportView report={report} includeCategory={includeCategory} includeFunds={includeFunds} />}
    </div>
  );
}

function ReportView({ report, includeCategory, includeFunds }) {
  return (
    <div className="print-area bg-white border border-[#E5E0D8] rounded-xl p-8 sm:p-12 shadow-sm" data-testid="report-view">
      <div className="text-center border-b-2 border-[#1E293B] pb-4 mb-6">
        <h2 className="font-serif text-3xl font-bold text-slate-900">{report.church?.church_name}</h2>
        <p className="text-slate-600 mt-1">Treasurer's Report</p>
        <p className="text-slate-500 text-sm mt-0.5">{fmtDate(report.start)} — {fmtDate(report.end)}</p>
      </div>

      {report.accounts.map((acc) => (
        <div key={acc.id} className="mb-10 avoid-break">
          <div className="flex items-baseline justify-between border-b border-[#E5E0D8] pb-2">
            <h3 className="font-serif text-xl font-bold text-slate-900">
              Account {acc.mask} <span className="text-sm font-sans font-normal text-slate-500">{acc.name}</span>
            </h3>
            <span className="text-sm text-slate-600">
              Balance Forward {fmtDate(report.start)}: <span className="font-mono font-semibold text-slate-900">{money(acc.balance_forward)}</span>
            </span>
          </div>

          {/* Expenses */}
          <div className="mt-4">
            <div className="text-xs uppercase tracking-wider text-[#B45309] font-bold mb-1.5">Expenses</div>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500 border-b border-[#E5E0D8]">
                  <th className="py-1.5 font-medium">Date</th>
                  <th className="py-1.5 font-medium">Check #</th>
                  <th className="py-1.5 font-medium">Payee</th>
                  <th className="py-1.5 font-medium">Memo / Reason</th>
                  <th className="py-1.5 font-medium text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {acc.expenses.length === 0 && (
                  <tr><td colSpan={5} className="py-2 text-slate-400 italic">No expenses</td></tr>
                )}
                {acc.expenses.map((e, i) => (
                  <tr key={i} className="border-b border-[#F4F0E8]">
                    <td className="py-1.5 font-mono whitespace-nowrap">{fmtDate(e.date)}</td>
                    <td className="py-1.5 font-mono">{e.check_number || "—"}</td>
                    <td className="py-1.5">{e.payee || "—"}</td>
                    <td className="py-1.5 text-slate-600">{e.memo || "—"}</td>
                    <td className="py-1.5 text-right font-mono">{money(e.amount)}</td>
                  </tr>
                ))}
                <tr>
                  <td colSpan={4} className="py-2 text-right font-semibold">Total Expenses</td>
                  <td className="py-2 text-right font-mono font-bold text-[#B91C1C] print-total border-b-2 border-double border-slate-900">{money(acc.total_expenses)}</td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Income */}
          <div className="mt-5">
            <div className="text-xs uppercase tracking-wider text-[#B45309] font-bold mb-1.5">Income</div>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500 border-b border-[#E5E0D8]">
                  <th className="py-1.5 font-medium">Date</th>
                  <th className="py-1.5 font-medium">Source</th>
                  <th className="py-1.5 font-medium">Memo</th>
                  <th className="py-1.5 font-medium text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {acc.incomes.length === 0 && (
                  <tr><td colSpan={4} className="py-2 text-slate-400 italic">No income</td></tr>
                )}
                {acc.incomes.map((it, i) => (
                  <tr key={i} className="border-b border-[#F4F0E8]">
                    <td className="py-1.5 font-mono whitespace-nowrap">{fmtDate(it.date)}</td>
                    <td className="py-1.5">{it.label}</td>
                    <td className="py-1.5 text-slate-600">{it.memo || "—"}</td>
                    <td className="py-1.5 text-right font-mono">{money(it.amount)}</td>
                  </tr>
                ))}
                <tr>
                  <td colSpan={3} className="py-2 text-right font-semibold">Total Income</td>
                  <td className="py-2 text-right font-mono font-bold text-[#15803D] print-total border-b-2 border-double border-slate-900">{money(acc.total_income)}</td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Summary */}
          <div className="mt-5 flex justify-end">
            <table className="text-sm w-full sm:w-80">
              <tbody>
                <tr><td className="py-1 text-slate-600">Balance Forward</td><td className="py-1 text-right font-mono">{money(acc.balance_forward)}</td></tr>
                <tr><td className="py-1 text-slate-600">Total Income</td><td className="py-1 text-right font-mono text-[#15803D]">{money(acc.total_income)}</td></tr>
                <tr><td className="py-1 text-slate-600">Less Expenses</td><td className="py-1 text-right font-mono text-[#B91C1C]">({money(acc.total_expenses)})</td></tr>
                <tr className="border-t border-slate-900">
                  <td className="py-1.5 font-bold text-slate-900">New Balance {fmtDate(report.end)}</td>
                  <td className="py-1.5 text-right font-mono font-bold text-slate-900">{money(acc.new_balance)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      ))}

      {includeCategory && report.category_summary.length > 0 && (
        <div className="mb-8 avoid-break">
          <h3 className="font-serif text-xl font-bold text-slate-900 border-b border-[#E5E0D8] pb-2 mb-3">Income &amp; Expense by Category</h3>
          <table className="w-full text-sm">
            <thead><tr className="text-left text-slate-500 border-b border-[#E5E0D8]"><th className="py-1.5 font-medium">Category</th><th className="py-1.5 font-medium">Type</th><th className="py-1.5 font-medium text-right">Amount</th></tr></thead>
            <tbody>
              {report.category_summary.map((c, i) => (
                <tr key={i} className="border-b border-[#F4F0E8]">
                  <td className="py-1.5">{c.category}</td>
                  <td className="py-1.5 capitalize">{c.type}</td>
                  <td className={`py-1.5 text-right font-mono ${c.type === "income" ? "text-[#15803D]" : "text-[#B91C1C]"}`}>{money(c.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {includeFunds && report.fund_balances.length > 0 && (
        <div className="mb-8 avoid-break">
          <h3 className="font-serif text-xl font-bold text-slate-900 border-b border-[#E5E0D8] pb-2 mb-3">Fund Balances</h3>
          <table className="w-full text-sm">
            <tbody>
              {report.fund_balances.map((f, i) => (
                <tr key={i} className="border-b border-[#F4F0E8]">
                  <td className="py-1.5" style={{ paddingLeft: (f.depth || 0) * 20 }}>{f.depth ? "↳ " : ""}{f.name}</td>
                  <td className="py-1.5 text-right font-mono">{money(f.balance)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-12 pt-6">
        <p className="text-sm text-slate-600">Respectfully submitted,</p>
        <div className="mt-10 flex items-end gap-6">
          <div className="border-t border-slate-900 pt-1 w-64 text-sm text-slate-600">
            {report.church?.treasurer_name ? `${report.church.treasurer_name}, Treasurer` : "Treasurer"}
          </div>
          <div className="border-t border-slate-900 pt-1 w-40 text-sm text-slate-600">Date</div>
        </div>
      </div>
    </div>
  );
}
