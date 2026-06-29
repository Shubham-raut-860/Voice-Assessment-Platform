import { useEffect, useState } from "react";
import { CheckCircle2, KeyRound, Server, UserRound } from "lucide-react";
import { authService, AuthUser, getApiBaseUrl } from "../services/api";
import { Button } from "../components/ui/button";

export default function Settings() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    authService.me().then(setUser).catch((caught) => {
      setError(caught instanceof Error ? caught.message : "profile_load_failed");
    });
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <div className="mb-3 inline-flex items-center gap-2 rounded-full border bg-background px-3 py-1 text-xs font-semibold text-muted-foreground">
          <UserRound className="h-3.5 w-3.5" />
          Workspace Settings
        </div>
        <h1 className="text-3xl font-heading font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-muted-foreground">Alpha configuration status for the current browser and backend connection.</p>
      </div>

      {error && <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border bg-card p-5 shadow-sm">
          <div className="mb-4 flex items-center gap-2">
            <UserRound className="h-4 w-4 text-primary" />
            <h2 className="font-heading text-lg font-semibold">Profile</h2>
          </div>
          <div className="space-y-3 text-sm">
            <Row label="Name" value={user?.full_name ?? "Loading..."} />
            <Row label="Email" value={user?.email ?? "Loading..."} />
            <Row label="Role" value={user?.role ?? "Loading..."} />
            <Row label="Account status" value={user?.is_active ? "Active" : "Unknown"} />
          </div>
        </div>

        <div className="rounded-xl border bg-card p-5 shadow-sm">
          <div className="mb-4 flex items-center gap-2">
            <Server className="h-4 w-4 text-primary" />
            <h2 className="font-heading text-lg font-semibold">Backend</h2>
          </div>
          <div className="space-y-3 text-sm">
            <Row label="API base URL" value={getApiBaseUrl()} mono />
            <Row label="Auth storage" value="Browser token storage in local demo" />
            <Row label="Environment variables" value="Backend .env loaded server-side" />
          </div>
        </div>
      </section>

      <section className="rounded-xl border bg-card p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <KeyRound className="h-4 w-4 text-primary" />
          <h2 className="font-heading text-lg font-semibold">Alpha Readiness</h2>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {[
            "Authentication wired to backend",
            "Assessment library wired to backend",
            "Session list and Vapi call initiation wired",
            "Admin user management wired",
            "Failed report retry wired",
            "Role-aware signup and portals wired",
            "Candidate Web SDK voice room scheduled for Phase 2",
          ].map((item) => (
            <div key={item} className="flex items-center gap-2 rounded-lg border bg-muted/20 px-3 py-2 text-sm">
              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              {item}
            </div>
          ))}
        </div>
        <div className="mt-5 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-800">
          Local demo sessions use browser token storage. Logout revokes tokens when REDIS_URL is configured; cookie-based sessions remain a later production hardening item.
        </div>
        <div className="mt-5">
          <Button variant="outline" onClick={() => window.location.reload()}>Reload workspace</Button>
        </div>
      </section>
    </div>
  );
}

function Row({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b pb-2 last:border-b-0">
      <span className="text-muted-foreground">{label}</span>
      <span className={mono ? "max-w-[260px] truncate font-mono text-xs" : "font-medium"}>
        {value}
      </span>
    </div>
  );
}
