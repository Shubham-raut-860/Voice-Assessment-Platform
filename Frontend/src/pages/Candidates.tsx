import { type FormEvent, useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { Search, Filter, MoreHorizontal, CheckCircle2, Circle, UserPlus, Mic, ExternalLink, Copy, PhoneCall } from "lucide-react";
import { adminService, AssessmentResponse, assessmentsService, authStore, candidatesService, SessionResponse, sessionsService } from "../services/api";
import { Candidate } from "../types";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { Badge } from "../components/ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "../components/ui/avatar";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "../components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "../components/ui/tooltip";

export default function Candidates() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [assessments, setAssessments] = useState<AssessmentResponse[]>([]);
  const [candidateSessions, setCandidateSessions] = useState<SessionResponse[]>([]);
  const [createdSession, setCreatedSession] = useState<SessionResponse | null>(null);
  const [isInviting, setIsInviting] = useState(false);
  const [phoneNumbers, setPhoneNumbers] = useState<Record<string, string>>({});
  const [startingPhoneSessionId, setStartingPhoneSessionId] = useState<string | null>(null);
  const userRole = authStore.getUser()?.role ?? "candidate";
  const [inviteForm, setInviteForm] = useState({
    fullName: "",
    email: "",
    password: "DemoCandidate123!",
    assessmentId: "",
  });

  useEffect(() => {
    if (userRole === "candidate") {
      sessionsService.list(1, 50)
        .then((response) => setCandidateSessions(response.items))
        .catch((caught) => setError(caught instanceof Error ? caught.message : "sessions_load_failed"));
      return;
    }

    candidatesService.getRecent()
      .then(setCandidates)
      .catch((caught) => setError(caught instanceof Error ? caught.message : "candidates_load_failed"));

    assessmentsService.list(1, 100, "active")
      .then((response) => {
        setAssessments(response.items);
        setInviteForm((current) => ({
          ...current,
          assessmentId: current.assessmentId || response.items[0]?.id || "",
        }));
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "active_assessments_load_failed"));
  }, [userRole]);

  async function inviteCandidate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    setIsInviting(true);
    try {
      const user = await createOrFindCandidate();
      const session = await sessionsService.create({
        assessment_id: inviteForm.assessmentId,
        candidate_id: user.id,
      });
      setCreatedSession(session);
      setMessage(`Candidate session created for ${user.full_name}. Candidate login: ${user.email}`);
      setInviteForm({
        fullName: "",
        email: "",
        password: "DemoCandidate123!",
        assessmentId: assessments[0]?.id || "",
      });
      const refreshed = await candidatesService.getRecent();
      setCandidates(refreshed);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "candidate_invite_failed");
    } finally {
      setIsInviting(false);
    }
  }

  async function createOrFindCandidate() {
    try {
      return await adminService.createUser({
        email: inviteForm.email,
        password: inviteForm.password,
        full_name: inviteForm.fullName,
        role: "candidate",
      });
    } catch (caught) {
      if (!(caught instanceof Error) || !caught.message.includes("email_already_registered")) {
        throw caught;
      }
      const existing = await adminService.lookupUserByEmail(inviteForm.email);
      if (existing.role !== "candidate") {
        throw new Error(`email_belongs_to_${existing.role}`);
      }
      return existing;
    }
  }

  async function copyCandidateLink(sessionId: string) {
    const link = `${window.location.origin}/demo/${sessionId}`;
    try {
      await navigator.clipboard.writeText(link);
      setMessage("Candidate assessment link copied.");
    } catch {
      setError(link);
    }
  }

  async function startPhoneCall(sessionId: string) {
    const customerNumber = phoneNumbers[sessionId]?.trim() ?? "";
    if (!/^\+[1-9]\d{7,14}$/.test(customerNumber)) {
      setError("Enter the candidate phone number in E.164 format, for example +919766017525.");
      return;
    }

    setError(null);
    setMessage(null);
    setStartingPhoneSessionId(sessionId);
    try {
      const response = await sessionsService.startCall(sessionId, customerNumber);
      setMessage(`Phone call started. Vapi call ID: ${response.call_id}`);
      setPhoneNumbers((current) => ({ ...current, [sessionId]: "" }));
      const refreshed = await candidatesService.getRecent();
      setCandidates(refreshed);
    } catch (caught) {
      setError(caught instanceof Error ? formatPhoneCallError(caught.message) : "Phone call could not be started.");
    } finally {
      setStartingPhoneSessionId(null);
    }
  }

  if (userRole === "candidate") {
    return <CandidateSessions sessions={candidateSessions} error={error} />;
  }

  const filtered = candidates.filter(c => {
    const matchesSearch = c.name.toLowerCase().includes(searchTerm.toLowerCase()) || 
                          c.role.toLowerCase().includes(searchTerm.toLowerCase());
    let matchesDate = true;
    if (startDate) {
      matchesDate = matchesDate && c.date >= startDate;
    }
    if (endDate) {
      matchesDate = matchesDate && c.date <= endDate;
    }
    return matchesSearch && matchesDate;
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-3xl font-heading font-semibold tracking-tight">Assign assessments</h1>
          <p className="text-muted-foreground mt-1">Pick a candidate and assessment. The platform creates the session.</p>
        </div>
        <Button className="gap-2" onClick={() => document.getElementById("candidate-invite-card")?.scrollIntoView({ behavior: "smooth" })}>
          <UserPlus className="h-4 w-4" /> Invite Candidate
        </Button>
      </div>

      <form id="candidate-invite-card" onSubmit={inviteCandidate} className="rounded-xl border bg-card p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <UserPlus className="h-4 w-4 text-primary" />
          <h2 className="font-heading text-lg font-semibold">Assign assessment to candidate</h2>
        </div>
        <div className="grid gap-4 lg:grid-cols-[1fr_1fr_1fr_auto]">
          <Input
            required
            placeholder="Candidate name"
            value={inviteForm.fullName}
            onChange={(event) => setInviteForm({ ...inviteForm, fullName: event.target.value })}
          />
          <Input
            required
            type="email"
            placeholder="[email-redacted]"
            value={inviteForm.email}
            onChange={(event) => setInviteForm({ ...inviteForm, email: event.target.value })}
          />
          <select
            required
            className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            value={inviteForm.assessmentId}
            onChange={(event) => setInviteForm({ ...inviteForm, assessmentId: event.target.value })}
          >
            <option value="" disabled>Select assessment</option>
            {assessments.map((assessment) => (
              <option key={assessment.id} value={assessment.id}>{assessment.title}</option>
            ))}
          </select>
          <Button type="submit" disabled={isInviting || !inviteForm.assessmentId}>
            {isInviting ? "Assigning..." : "Assign"}
          </Button>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          New candidates use the demo password <span className="font-mono">DemoCandidate123!</span>. Existing candidates keep their current password.
        </p>
        <p className="mt-2 text-xs text-muted-foreground">
          Phone calls require backend <span className="font-mono">VAPI_CALL_MODE=phone</span> and a Vapi/Twilio phone number ID.
          Browser calls remain available from the candidate link.
        </p>
      </form>

      <div className="flex flex-col sm:flex-row gap-4 items-center">
        <div className="relative flex-1 w-full max-w-sm">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input 
            type="search" 
            placeholder="Search candidates or roles..." 
            className="pl-9 bg-background w-full"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-2 w-full sm:w-auto overflow-x-auto">
          <Input 
            type="date"
            className="w-auto bg-background"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            title="Start Date"
          />
          <span className="text-muted-foreground">-</span>
          <Input 
            type="date"
            className="w-auto bg-background"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            title="End Date"
          />
          <Button variant="outline" className="gap-2 sm:ms-2 bg-background flex-shrink-0">
            <Filter className="h-4 w-4" /> Filters
          </Button>
        </div>
      </div>

      <div className="rounded-xl border bg-card text-card-foreground shadow-sm overflow-hidden">
        {message && (
          <div className="flex flex-wrap items-center justify-between gap-3 border-b bg-emerald-500/10 px-4 py-3 text-sm text-emerald-700">
            <span>{message}</span>
            {createdSession && (
              <Button nativeButton={false} size="sm" variant="outline" render={<Link to={`/demo/${createdSession.id}`} />}>
                Review handoff
              </Button>
            )}
          </div>
        )}
        {error && <div className="border-b bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}
        <div className="border-b bg-muted/30 px-4 py-3 text-sm font-semibold text-muted-foreground">
          Candidate sessions
        </div>
        {filtered.length === 0 ? (
          <div className="px-4 py-10 text-center text-sm text-muted-foreground">No candidates found.</div>
        ) : (
          <div className="divide-y">
            {filtered.map((candidate) => (
              <div key={candidate.id} className="group grid gap-4 p-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)_auto] xl:items-center">
                <div className="flex min-w-0 items-center gap-3">
                  <Avatar className="h-10 w-10 rounded-xl border">
                    <AvatarImage src={candidate.avatarUrl} alt={candidate.name} />
                    <AvatarFallback className="rounded-xl">{candidate.name.substring(0, 2).toUpperCase()}</AvatarFallback>
                  </Avatar>
                  <div className="min-w-0">
                    {candidate.status === "completed" ? (
                      <Link to={`/app/reports/${candidate.id}`} className="truncate font-semibold text-foreground hover:underline">
                        {candidate.name}
                      </Link>
                    ) : (
                      <div className="truncate font-semibold text-foreground">{candidate.name}</div>
                    )}
                    <div className="truncate text-sm text-muted-foreground">{candidate.email}</div>
                    <div className="mt-1 line-clamp-1 text-xs text-muted-foreground">{candidate.role}</div>
                  </div>
                </div>

                <div className="grid gap-2 text-sm sm:grid-cols-3 xl:grid-cols-1">
                  <Tooltip>
                    <TooltipTrigger render={<div className="flex w-fit cursor-help items-center gap-2" />}>
                      {candidate.status === "completed" ? <CheckCircle2 className="h-4 w-4 text-emerald-500" /> : <Circle className="h-4 w-4 text-muted-foreground" />}
                      <span className="capitalize">{candidate.status.replace("_", " ")}</span>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p>Last stage update: {candidate.date}</p>
                    </TooltipContent>
                  </Tooltip>
                  <span className="text-muted-foreground tabular-nums">{candidate.date}</span>
                  <span className="max-w-full truncate font-mono text-xs text-muted-foreground">
                    {candidate.callId ? `Call ${candidate.callId}` : "Call not started"}
                  </span>
                </div>

                <div className="flex flex-wrap items-center gap-2 xl:justify-end">
                  {candidate.status === "completed" ? (
                    <Button nativeButton={false} variant="outline" size="sm" render={<Link to={`/app/reports/${candidate.id}`} />}>
                      View report
                    </Button>
                  ) : (
                    <Button nativeButton={false} size="sm" className="gap-2" render={<Link to={`/demo/${candidate.id}`} />}>
                      <ExternalLink className="h-4 w-4" /> Review handoff
                    </Button>
                  )}
                  {candidate.status !== "completed" && !candidate.callId && (
                    <div className="flex min-w-[19rem] max-w-full flex-wrap items-center gap-2 rounded-full border bg-background p-1">
                      <Input
                        type="tel"
                        inputMode="tel"
                        placeholder="+919766017525"
                        value={phoneNumbers[candidate.id] ?? ""}
                        onChange={(event) => setPhoneNumbers((current) => ({ ...current, [candidate.id]: event.target.value }))}
                        className="h-8 min-w-[10.5rem] flex-1 rounded-full border-0 bg-transparent px-3 text-sm shadow-none focus-visible:ring-0"
                        aria-label={`Phone number for ${candidate.name}`}
                      />
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 shrink-0 gap-1 rounded-full"
                        onClick={() => startPhoneCall(candidate.id)}
                        disabled={startingPhoneSessionId === candidate.id}
                      >
                        <PhoneCall className="h-3.5 w-3.5" />
                        {startingPhoneSessionId === candidate.id ? "Calling..." : "Call phone"}
                      </Button>
                    </div>
                  )}
                  <Button variant="outline" size="sm" className="gap-2" onClick={() => copyCandidateLink(candidate.id)}>
                    <Copy className="h-4 w-4" /> Copy link
                  </Button>
                  {candidate.status === "completed" && candidate.score !== undefined && (
                    <span className="rounded-full bg-muted px-2.5 py-1 font-mono text-sm font-medium">
                      {candidate.score}
                    </span>
                  )}
                  <DropdownMenu>
                    <DropdownMenuTrigger render={<Button variant="ghost" className="h-8 w-8 p-0" />}>
                      <MoreHorizontal className="h-4 w-4" />
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem render={<Link to={`/app/reports/${candidate.id}`} />} disabled={candidate.status !== "completed"}>
                        View report
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => navigator.clipboard.writeText(candidate.email)}>
                        Copy email
                      </DropdownMenuItem>
                      <DropdownMenuItem>Send reminder</DropdownMenuItem>
                      <DropdownMenuItem className="text-destructive focus:bg-destructive focus:text-destructive-foreground">Archive</DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function formatPhoneCallError(message: string): string {
  if (message.includes("vapi_international_calls_require_twilio_or_paid_number")) {
    return "This Vapi number cannot place international calls. Connect your Twilio number in Vapi, copy the new Vapi phone-number ID into VAPI_PHONE_NUMBER_ID, then retry.";
  }
  if (message.includes("phone_call_mode_not_enabled")) {
    return "Phone mode is not enabled. Set VAPI_CALL_MODE=phone and restart the backend.";
  }
  if (message.includes("customer_number_required_for_phone_call_mode")) {
    return "Enter the candidate phone number in E.164 format, for example +919766017525.";
  }
  if (message.includes("session_call_already_bound")) {
    return "This session already has a Vapi call attached. Create a fresh session before starting another phone call.";
  }
  if (message.includes("vapi_phone_number_not_ready_or_not_accessible")) {
    return "The configured Vapi phone number is not ready or not accessible. Check the Vapi Phone Numbers page.";
  }
  return message;
}

function CandidateSessions({ sessions, error }: { sessions: SessionResponse[]; error: string | null }) {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-heading font-semibold tracking-tight">My assessments</h1>
        <p className="text-muted-foreground mt-1">Start your assigned voice assessment from here.</p>
      </div>

      {error && <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}

      <div className="rounded-xl border bg-card text-card-foreground shadow-sm overflow-hidden">
        <Table>
          <TableHeader className="bg-muted/30">
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
                <TableCell>
                  <div className="flex items-center gap-2">
                    {session.status === "completed" ? <CheckCircle2 className="h-4 w-4 text-emerald-500" /> : <Circle className="h-4 w-4 text-muted-foreground" />}
                    <span className="text-sm capitalize">{session.status.replace("_", " ")}</span>
                  </div>
                </TableCell>
                <TableCell className="max-w-[200px] truncate font-mono text-xs text-muted-foreground">
                  {session.vapi_call_id ?? "not started"}
                </TableCell>
                <TableCell className="text-right">
                  {session.status === "completed" ? (
                    <Button nativeButton={false} variant="outline" size="sm" render={<Link to={`/app/reports/${session.id}`} />}>
                      View report
                    </Button>
                  ) : (
                    <Button nativeButton={false} size="sm" className="gap-2" render={<Link to={`/demo/${session.id}`} />}>
                      <Mic className="h-4 w-4" /> Start
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
