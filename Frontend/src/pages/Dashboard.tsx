import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, BarChart3, Clock, FileCheck, Mic, Users, type LucideIcon } from "lucide-react";
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Tooltip as RechartsTooltip } from "recharts";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { Analytics, Candidate } from "../types";
import { analyticsService, authStore, candidatesService, SessionResponse, sessionsService } from "../services/api";

export default function Dashboard() {
  const user = authStore.getUser();
  if (user?.role === "candidate") {
    return <CandidateDashboard />;
  }
  return <RecruiterDashboard />;
}

function CandidateDashboard() {
  const [sessions, setSessions] = useState<SessionResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    sessionsService.list(1, 20)
      .then((response) => setSessions(response.items))
      .catch((caught) => setError(caught instanceof Error ? caught.message : "sessions_load_failed"))
      .finally(() => setIsLoading(false));
  }, []);

  if (isLoading) {
    return <div className="p-8 text-center text-muted-foreground animate-pulse">Loading your assessments...</div>;
  }

  if (error) {
    return <ConnectionError error={error} />;
  }

  const nextSession = sessions.find((session) => session.status === "scheduled" || session.status === "in_progress");

  return (
    <div className="space-y-8">
      <div className="rounded-3xl border bg-card p-8 shadow-sm">
        <div className="inline-flex items-center gap-2 rounded-full border bg-background px-3 py-1 text-xs font-semibold text-muted-foreground">
          <Mic className="h-3.5 w-3.5" />
          Candidate portal
        </div>
        <h1 className="mt-5 max-w-3xl text-4xl font-heading font-semibold tracking-tight">
          Your voice assessment is ready.
        </h1>
        <p className="mt-3 max-w-2xl text-muted-foreground">
          Start from your assigned session. The call runs in the browser, then the report is generated after the assessment ends.
        </p>
        {nextSession ? (
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <Button nativeButton={false} className="gap-2" render={<Link to={`/demo/${nextSession.id}`} />}>
              <Mic className="h-4 w-4" /> Start assessment
            </Button>
            <Badge variant="outline">{nextSession.assessment.title}</Badge>
          </div>
        ) : (
          <div className="mt-6 rounded-2xl border bg-muted/30 p-4 text-sm text-muted-foreground">
            You do not have a scheduled assessment right now.
          </div>
        )}
      </div>

      <div className="rounded-xl border bg-card shadow-sm">
        <div className="border-b p-5">
          <h2 className="font-heading text-xl font-semibold">My assessments</h2>
          <p className="mt-1 text-sm text-muted-foreground">Every assigned session appears here.</p>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Assessment</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Call</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sessions.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="h-24 text-center text-muted-foreground">
                  No assessments assigned yet.
                </TableCell>
              </TableRow>
            ) : sessions.map((session) => (
              <TableRow key={session.id}>
                <TableCell>
                  <div className="font-medium">{session.assessment.title}</div>
                  <div className="text-xs text-muted-foreground">{session.assessment.time_limit_minutes} minutes</div>
                </TableCell>
                <TableCell><Badge variant="outline">{session.status.replace("_", " ")}</Badge></TableCell>
                <TableCell className="max-w-[180px] truncate font-mono text-xs text-muted-foreground">
                  {session.vapi_call_id ?? "not started"}
                </TableCell>
                <TableCell className="text-right">
                  {session.status === "completed" ? (
                    <Button nativeButton={false} variant="outline" size="sm" render={<Link to={`/app/reports/${session.id}`} />}>
                      View report
                    </Button>
                  ) : (
                    <Button nativeButton={false} size="sm" render={<Link to={`/demo/${session.id}`} />}>
                      Start
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function RecruiterDashboard() {
  const [stats, setStats] = useState<Analytics | null>(null);
  const [recent, setRecent] = useState<Candidate[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([analyticsService.getStats(), candidatesService.getRecent()])
      .then(([nextStats, nextRecent]) => {
        setStats(nextStats);
        setRecent(nextRecent);
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "dashboard_load_failed"));
  }, []);

  if (error) return <ConnectionError error={error} />;
  if (!stats) return <div className="p-8 text-center text-muted-foreground animate-pulse">Loading dashboard...</div>;
  const hasCompetencyData = (stats.competencyAverages || []).length > 0;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-heading font-semibold tracking-tight">Overview</h1>
        <p className="text-muted-foreground mt-1">Create sessions, track candidates, and review generated reports.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Metric title="Total Sessions" value={stats.totalAssessments.toLocaleString()} icon={BarChart3} hint="All assessment sessions" />
        <Metric title="Pass Rate" value={`${stats.passRate}%`} icon={FileCheck} hint="Completed sessions" />
        <Metric title="Active Candidates" value={String(recent.filter((candidate) => candidate.status === "in_progress" || candidate.status === "invited").length)} icon={Users} hint="In progress or scheduled" />
        <Metric title="Average Score" value={stats.averageScore ? `${Math.round(stats.averageScore)}/100` : "-"} icon={Clock} hint="Generated reports" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 className="text-xl font-heading font-semibold tracking-tight">Recent Pipeline</h2>
              <p className="text-sm text-muted-foreground">The latest assigned candidate sessions.</p>
            </div>
            <Button nativeButton={false} render={<Link to="/app/candidates" />}>Assign candidate</Button>
          </div>
          <div className="mt-4 rounded-xl border bg-card shadow-sm">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Candidate</TableHead>
                  <TableHead>Assessment</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">AI Score</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recent.map((candidate) => (
                  <TableRow key={candidate.id}>
                    <TableCell className="font-medium">
                      {candidate.status === "completed" ? (
                        <Link to={`/app/reports/${candidate.id}`} className="hover:underline">{candidate.name}</Link>
                      ) : candidate.name}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{candidate.role}</TableCell>
                    <TableCell><Badge variant={candidate.status === "completed" ? "default" : "secondary"}>{candidate.status.replace("_", " ")}</Badge></TableCell>
                    <TableCell className="text-right font-mono">{candidate.score ?? "-"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>

        <div>
          <h2 className="text-xl font-heading font-semibold tracking-tight">Competency Radar</h2>
          <Card className="mt-4 h-[350px]">
            <CardHeader className="pb-2">
              <CardDescription>Company-wide platform strengths</CardDescription>
            </CardHeader>
            <CardContent>
              {hasCompetencyData ? (
                <div className="mt-4 h-[250px] min-w-0">
                  <ResponsiveContainer width="100%" height="100%">
                    <RadarChart cx="50%" cy="50%" outerRadius="70%" data={stats.competencyAverages || []}>
                      <PolarGrid stroke="hsl(var(--muted-foreground)/0.3)" />
                      <PolarAngleAxis dataKey="area" tick={{ fontSize: 11, fill: "hsl(var(--foreground))" }} />
                      <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} axisLine={false} />
                      <RechartsTooltip contentStyle={{ borderRadius: "8px", border: "1px solid hsl(var(--border))", backgroundColor: "hsl(var(--background))" }} />
                      <Radar name="Platform Average" dataKey="avgScore" stroke="hsl(var(--primary))" fill="hsl(var(--primary))" fillOpacity={0.4} />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="mt-4 flex h-[250px] items-center justify-center rounded-2xl border border-dashed bg-muted/30 p-6 text-center">
                  <div>
                    <BarChart3 className="mx-auto h-8 w-8 text-muted-foreground" />
                    <p className="mt-3 text-sm font-medium">Competency data appears after generated reports.</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      Complete a few candidate assessments to populate this chart.
                    </p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Metric({ title, value, icon: Icon, hint }: { title: string; value: string; icon: LucideIcon; hint: string }) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold font-mono">{value}</div>
        <p className="text-xs text-muted-foreground mt-1 flex items-center">
          <ArrowUpRight className="mr-1 h-3 w-3" />
          {hint}
        </p>
      </CardContent>
    </Card>
  );
}

function ConnectionError({ error }: { error: string }) {
  return (
    <div className="rounded-3xl border bg-card p-8 text-center shadow-sm">
      <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">!</div>
      <h1 className="text-2xl font-semibold">Backend connection needed</h1>
      <p className="mx-auto mt-2 max-w-xl text-muted-foreground">
        Start the Worker on port 8787 and the backend on port 8001, then refresh this page.
      </p>
      <pre className="mx-auto mt-5 max-w-xl overflow-auto rounded-2xl bg-muted p-4 text-left text-sm text-muted-foreground">{error}</pre>
    </div>
  );
}
