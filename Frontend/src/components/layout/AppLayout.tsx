import { useMemo, useState } from "react";
import { Link, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { ClipboardList, Mic2, Users, LayoutDashboard, FileText, Settings, LogOut, Menu, ShieldCheck } from "lucide-react";
import { Button } from "../ui/button";
import { Sheet, SheetContent, SheetTrigger } from "../ui/sheet";
import { authService, authStore, UserRole } from "../../services/api";

const navItems = [
  { name: "Dashboard", candidateName: "My overview", href: "/app", icon: LayoutDashboard, roles: ["admin", "assessor", "candidate"] },
  { name: "Assessments", href: "/app/assessments", icon: ClipboardList, roles: ["admin", "assessor"] },
  { name: "Candidates", href: "/app/candidates", icon: Users, roles: ["admin", "assessor"] },
  { name: "Reports", candidateName: "My sessions", href: "/app/reports", icon: FileText, roles: ["admin", "assessor", "candidate"] },
  { name: "Admin", href: "/app/admin", icon: ShieldCheck, roles: ["admin"] },
  { name: "Settings", href: "/app/settings", icon: Settings, roles: ["admin", "assessor", "candidate"] },
];

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const user = authStore.getUser();
  const userRole = user?.role ?? "candidate";
  const visibleNavItems = useMemo(
    () => navItems.filter((item) => item.roles.includes(userRole)),
    [userRole],
  );
  const currentRestrictedItem = navItems
    .filter((item) => item.href !== "/app")
    .find((item) => location.pathname === item.href || location.pathname.startsWith(`${item.href}/`));
  const canViewCurrentRoute = !currentRestrictedItem || currentRestrictedItem.roles.includes(userRole);

  async function handleLogout() {
    await authService.logout();
    navigate("/");
  }

  async function handleMobileLogout() {
    setIsMobileMenuOpen(false);
    await handleLogout();
  }

  return (
    <div className="flex min-h-screen w-full bg-muted/20">
      {/* Desktop Sidebar */}
      <aside className="hidden border-r bg-background/90 backdrop-blur-xl w-72 flex-col lg:flex">
        <div className="flex h-16 items-center border-b px-6">
          <Link to="/" className="flex items-center gap-2 font-bold text-lg tracking-tight font-heading">
            <Mic2 className="h-5 w-5 text-primary" />
            Vocalis.ai
          </Link>
        </div>
        <div className="px-4 py-4">
          <div className="rounded-2xl border bg-muted/40 p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Signed in</div>
            <div className="mt-1 truncate font-semibold">{user?.full_name ?? "Workspace user"}</div>
            <div className="mt-1 truncate text-sm text-muted-foreground">{user?.email}</div>
            <div className="mt-3 inline-flex rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold capitalize text-primary">
              {userRole} portal
            </div>
          </div>
        </div>
        <div className="flex-1 overflow-auto py-4">
          <nav className="grid gap-1 px-4 text-sm font-medium">
            {visibleNavItems.map((item) => {
              const isActive = location.pathname === item.href || (item.href !== "/app" && location.pathname.startsWith(item.href));
              const label = userRole === "candidate" && item.candidateName ? item.candidateName : item.name;
              return (
                <Link
                  key={item.href}
                  to={item.href}
                  className={`flex items-center gap-3 rounded-xl px-3 py-2.5 transition-all hover:text-primary ${
                    isActive ? "bg-primary text-primary-foreground shadow-sm hover:text-primary-foreground" : "text-muted-foreground hover:bg-muted/70"
                  }`}
                >
                  <item.icon className="h-4 w-4" />
                  {label}
                </Link>
              );
            })}
          </nav>
        </div>
        <div className="mt-auto border-t p-4">
          <Button variant="ghost" className="w-full justify-start gap-2 text-muted-foreground hover:text-foreground" onClick={handleLogout}>
            <LogOut className="h-4 w-4" />
            Logout
          </Button>
        </div>
      </aside>

      <div className="flex flex-col flex-1 min-h-screen">
        {/* Mobile Header */}
        <header className="flex h-14 lg:hidden items-center gap-4 border-b bg-background px-6">
          <Sheet open={isMobileMenuOpen} onOpenChange={setIsMobileMenuOpen}>
            <SheetTrigger render={<Button variant="ghost" size="icon" className="shrink-0 lg:hidden" />}>
                <Menu className="h-5 w-5" />
                <span className="sr-only">Toggle navigation menu</span>
            </SheetTrigger>
            <SheetContent side="left" className="w-64 p-0">
              <div className="flex h-full flex-col">
                <div className="flex h-16 items-center border-b px-6">
                  <Link to="/" className="flex items-center gap-2 font-bold text-lg font-heading" onClick={() => setIsMobileMenuOpen(false)}>
                    <Mic2 className="h-5 w-5 text-primary" />
                    Vocalis.ai
                  </Link>
                </div>
                <div className="border-b p-4">
                  <div className="rounded-2xl border bg-muted/40 p-4">
                    <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Signed in</div>
                    <div className="mt-1 truncate font-semibold">{user?.full_name ?? "Workspace user"}</div>
                    <div className="mt-1 truncate text-sm text-muted-foreground">{user?.email}</div>
                    <div className="mt-3 inline-flex rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold capitalize text-primary">
                      {userRole} portal
                    </div>
                  </div>
                </div>
                <nav className="grid gap-2 p-4 text-sm font-medium">
                  {visibleNavItems.map((item) => {
                    const isActive = location.pathname === item.href || (item.href !== "/app" && location.pathname.startsWith(item.href));
                    const label = userRole === "candidate" && item.candidateName ? item.candidateName : item.name;
                    return (
                      <Link
                        key={item.href}
                        to={item.href}
                        onClick={() => setIsMobileMenuOpen(false)}
                        className={`flex items-center gap-3 rounded-lg px-3 py-2 transition-all ${
                          isActive ? "bg-muted text-primary" : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        <item.icon className="h-4 w-4" />
                        {label}
                      </Link>
                    );
                  })}
                </nav>
                <div className="mt-auto border-t p-4">
                  <Button variant="ghost" className="w-full justify-start gap-2 text-muted-foreground hover:text-foreground" onClick={handleMobileLogout}>
                    <LogOut className="h-4 w-4" />
                    Logout
                  </Button>
                </div>
              </div>
            </SheetContent>
          </Sheet>
          <div className="w-full flex-1">
            <span className="font-heading font-semibold text-sm">Vocalis</span>
          </div>
        </header>

        {/* Main Content */}
        <main className="flex-1 p-5 sm:p-6 lg:p-8 w-full max-w-7xl mx-auto">
          {canViewCurrentRoute ? <Outlet /> : <Navigate replace to="/app" />}
        </main>
      </div>
    </div>
  );
}
