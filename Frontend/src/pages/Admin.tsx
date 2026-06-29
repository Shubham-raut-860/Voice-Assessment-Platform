import { useEffect, useState } from "react";
import { RefreshCw, ShieldCheck, UserCog, AlertTriangle } from "lucide-react";
import { adminService, AuthUser, SessionResponse, UserRole } from "../services/api";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";

const roles: UserRole[] = ["admin", "assessor", "candidate"];

export default function Admin() {
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [failedSessions, setFailedSessions] = useState<SessionResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadAdminData();
  }, []);

  async function loadAdminData() {
    setIsLoading(true);
    setError(null);
    try {
      const [userResponse, failedResponse] = await Promise.all([
        adminService.listUsers(1, 100),
        adminService.listFailedSessions(1, 50),
      ]);
      setUsers(userResponse.items);
      setFailedSessions(failedResponse.items);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "admin_data_load_failed");
    } finally {
      setIsLoading(false);
    }
  }

  async function updateUser(user: AuthUser, patch: { role?: UserRole; is_active?: boolean }) {
    setMessage(null);
    setError(null);
    try {
      await adminService.updateUser(user.id, patch);
      setMessage("User updated.");
      await loadAdminData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "user_update_failed");
    }
  }

  async function retryReport(session: SessionResponse) {
    setMessage(null);
    setError(null);
    try {
      await adminService.retryReport(session.id);
      setMessage(`Report retry accepted for ${session.candidate.full_name}.`);
      await loadAdminData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "report_retry_failed");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border bg-background px-3 py-1 text-xs font-semibold text-muted-foreground">
            <ShieldCheck className="h-3.5 w-3.5" />
            Admin Controls
          </div>
          <h1 className="text-3xl font-heading font-semibold tracking-tight">Operations</h1>
          <p className="mt-1 text-muted-foreground">Manage users and recover failed report generation during alpha testing.</p>
        </div>
        <Button variant="outline" className="gap-2" onClick={loadAdminData}>
          <RefreshCw className="h-4 w-4" /> Refresh
        </Button>
      </div>

      {message && <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-700">{message}</div>}
      {error && <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}

      <section className="overflow-hidden rounded-xl border bg-card shadow-sm">
        <div className="flex items-center gap-2 border-b px-5 py-4">
          <UserCog className="h-4 w-4 text-primary" />
          <h2 className="font-heading text-lg font-semibold">Users</h2>
        </div>
        <Table>
          <TableHeader className="bg-muted/30">
            <TableRow>
              <TableHead>User</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Verified</TableHead>
              <TableHead>Active</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow><TableCell colSpan={5} className="h-24 text-center text-muted-foreground">Loading users...</TableCell></TableRow>
            ) : users.length === 0 ? (
              <TableRow><TableCell colSpan={5} className="h-24 text-center text-muted-foreground">No users found.</TableCell></TableRow>
            ) : users.map((user) => (
              <TableRow key={user.id}>
                <TableCell>
                  <div className="font-medium">{user.full_name}</div>
                  <div className="text-xs text-muted-foreground">{user.email}</div>
                </TableCell>
                <TableCell>
                  <select
                    className="h-9 rounded-md border bg-background px-2 text-sm"
                    value={user.role}
                    onChange={(event) => updateUser(user, { role: event.target.value as UserRole })}
                  >
                    {roles.map((role) => <option key={role} value={role}>{role}</option>)}
                  </select>
                </TableCell>
                <TableCell>
                  <Badge variant="outline">{user.is_verified ? "verified" : "unverified"}</Badge>
                </TableCell>
                <TableCell>
                  <Badge className={user.is_active ? "bg-emerald-500/10 text-emerald-700" : "bg-destructive/10 text-destructive"}>
                    {user.is_active ? "active" : "disabled"}
                  </Badge>
                </TableCell>
                <TableCell className="text-right">
                  <Button variant="outline" size="sm" onClick={() => updateUser(user, { is_active: !user.is_active })}>
                    {user.is_active ? "Disable" : "Enable"}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>

      <section className="overflow-hidden rounded-xl border bg-card shadow-sm">
        <div className="flex items-center gap-2 border-b px-5 py-4">
          <AlertTriangle className="h-4 w-4 text-amber-500" />
          <h2 className="font-heading text-lg font-semibold">Failed Sessions</h2>
        </div>
        <Table>
          <TableHeader className="bg-muted/30">
            <TableRow>
              <TableHead>Candidate</TableHead>
              <TableHead>Assessment</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Call ID</TableHead>
              <TableHead className="text-right">Recovery</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {failedSessions.length === 0 ? (
              <TableRow><TableCell colSpan={5} className="h-24 text-center text-muted-foreground">No failed sessions in the current window.</TableCell></TableRow>
            ) : failedSessions.map((session) => (
              <TableRow key={session.id}>
                <TableCell>
                  <div className="font-medium">{session.candidate.full_name}</div>
                  <div className="text-xs text-muted-foreground">{session.candidate.email}</div>
                </TableCell>
                <TableCell>{session.assessment.title}</TableCell>
                <TableCell><Badge variant="outline">{session.status}</Badge></TableCell>
                <TableCell className="max-w-[180px] truncate font-mono text-xs text-muted-foreground">{session.vapi_call_id ?? "not assigned"}</TableCell>
                <TableCell className="text-right">
                  <Button variant="outline" size="sm" className="gap-2" onClick={() => retryReport(session)}>
                    <RefreshCw className="h-4 w-4" /> Retry report
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>
    </div>
  );
}
