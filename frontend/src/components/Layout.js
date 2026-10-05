import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu";
import { Landmark, LayoutDashboard, ListOrdered, FileText, Settings as SettingsIcon, LogOut, Plus, User } from "lucide-react";
import { useEffect, useState } from "react";
import api from "@/lib/api";
import TransactionDialog from "@/components/TransactionDialog";

const tabs = [
  { name: "Dashboard", path: "/", icon: LayoutDashboard, testid: "nav-item-dashboard" },
  { name: "Transactions", path: "/transactions", icon: ListOrdered, testid: "nav-item-transactions" },
  { name: "Reports", path: "/reports", icon: FileText, testid: "nav-item-reports" },
  { name: "Settings", path: "/settings", icon: SettingsIcon, testid: "nav-item-settings" },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const [quickOpen, setQuickOpen] = useState(false);
  const [churchName, setChurchName] = useState("Church Treasury");

  useEffect(() => {
    api.get("/settings/church").then((r) => r.data?.church_name && setChurchName(r.data.church_name)).catch(() => {});
  }, []);

  return (
    <div className="min-h-screen bg-background">
      <header className="no-print sticky top-0 z-40 bg-[#FDFBF7]/95 backdrop-blur-md border-b border-[#E5E0D8]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="h-9 w-9 rounded-lg bg-[#1E293B] grid place-items-center">
              <Landmark className="h-5 w-5 text-[#D97706]" />
            </div>
            <span className="font-serif text-lg font-semibold text-slate-900 hidden sm:block truncate max-w-[220px]">{churchName}</span>
          </div>

          <nav className="flex items-center gap-1">
            {tabs.map((t) => (
              <NavLink
                key={t.path}
                to={t.path}
                end={t.path === "/"}
                data-testid={t.testid}
                className={({ isActive }) =>
                  `flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive ? "bg-[#1E293B] text-white" : "text-slate-600 hover:bg-[#F4F0E8]"
                  }`
                }
              >
                <t.icon className="h-4 w-4" />
                <span className="hidden md:inline">{t.name}</span>
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            <Button size="sm" onClick={() => setQuickOpen(true)} className="bg-[#D97706] hover:bg-[#B45309]" data-testid="btn-quick-add-transaction">
              <Plus className="h-4 w-4 sm:mr-1.5" />
              <span className="hidden sm:inline">New Entry</span>
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="rounded-full" data-testid="user-menu-trigger">
                  <div className="h-8 w-8 rounded-full bg-[#F4F0E8] grid place-items-center">
                    <User className="h-4 w-4 text-slate-600" />
                  </div>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-52">
                <DropdownMenuLabel>
                  <div className="font-medium">{user?.name}</div>
                  <div className="text-xs text-muted-foreground font-normal">{user?.email}</div>
                  <div className="text-xs text-[#D97706] font-normal capitalize mt-0.5">{user?.role === "admin" ? "Treasurer (Admin)" : "User"}</div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={logout} data-testid="logout-button">
                  <LogOut className="h-4 w-4 mr-2" />
                  Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Outlet />
      </main>

      <TransactionDialog open={quickOpen} onOpenChange={setQuickOpen} />
    </div>
  );
}
