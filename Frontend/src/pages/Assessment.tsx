import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Vapi from "@vapi-ai/web";
import {
  Activity,
  ArrowLeft,
  CheckCircle2,
  Clipboard,
  ExternalLink,
  FileText,
  Headphones,
  Mic,
  PhoneCall,
  RefreshCw,
  Shield,
  Square,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { authStore, SessionResponse, sessionsService } from "../services/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";

type MicState = "unknown" | "checking" | "granted" | "blocked" | "unsupported";
type WebCallState = "idle" | "starting" | "live" | "ended" | "failed";
const VAPI_PUBLIC_KEY = import.meta.env.VITE_VAPI_PUBLIC_KEY as string | undefined;

export default function AssessmentExperience() {
  const params = useParams<{ sessionId?: string }>();
  const [sessionId, setSessionId] = useState(params.sessionId ?? "");
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [micState, setMicState] = useState<MicState>("unknown");
  const [webCallState, setWebCallState] = useState<WebCallState>("idle");
  const [webCallId, setWebCallId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [eventLog, setEventLog] = useState<string[]>([]);
  const vapiRef = useRef<Vapi | null>(null);
  const currentUser = authStore.getUser();
  const isAuthenticated = Boolean(authStore.getToken());
  const isAssignedCandidate = currentUser?.role === "candidate" && session?.candidate_id === currentUser.id;
  const isCoordinator = currentUser?.role === "admin" || currentUser?.role === "assessor";
  const canUseBrowserCall = Boolean(isAssignedCandidate && session && session.status !== "completed");

  useEffect(() => {
    if (params.sessionId && isAuthenticated) {
      void loadSession(params.sessionId);
    }
  }, [params.sessionId, isAuthenticated]);

  useEffect(() => {
    return () => {
      void vapiRef.current?.stop().catch(() => undefined);
      vapiRef.current?.removeAllListeners();
      vapiRef.current = null;
    };
  }, []);

  async function loadSession(id = sessionId) {
    if (!id) return;
    setError(null);
    try {
      const loaded = await sessionsService.get(id);
      setSession(loaded);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "session_load_failed");
    }
  }

  async function checkMicrophone() {
    if (!navigator.mediaDevices?.getUserMedia) {
      setMicState("unsupported");
      return;
    }
    setMicState("checking");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((track) => track.stop());
      setMicState("granted");
    } catch {
      setMicState("blocked");
    }
  }

  async function startBrowserAssessment() {
    if (!session) {
      setError("Load a session before starting the browser assessment.");
      return;
    }
    if (!VAPI_PUBLIC_KEY) {
      setError("VITE_VAPI_PUBLIC_KEY is missing from the frontend environment.");
      return;
    }
    if (micState !== "granted") {
      await checkMicrophone();
    }

    setError(null);
    setWebCallState("starting");
    setEventLog(["Starting Vapi browser call"]);

    try {
      const vapi = new Vapi(VAPI_PUBLIC_KEY);
      vapiRef.current = vapi;
      vapi.on("call-start", () => {
        setWebCallState("live");
        appendEvent("Call connected");
      });
      vapi.on("call-end", () => {
        setWebCallState("ended");
        appendEvent("Call ended");
      });
      vapi.on("speech-start", () => appendEvent("Assistant speaking"));
      vapi.on("speech-end", () => appendEvent("Assistant finished speaking"));
      vapi.on("call-start-failed", (event) => {
        setWebCallState("failed");
        const message = stringifyVapiError(event);
        setError(message);
        appendEvent(`Call start failed: ${message}`);
      });
      vapi.on("error", (event) => {
        setWebCallState("failed");
        const message = stringifyVapiError(event);
        setError(message);
        appendEvent(`Vapi error: ${message}`);
      });

      const call = await vapi.start(session.assessment.vapi_assistant_id);
      const callId = typeof call?.id === "string" ? call.id : null;
      if (callId) {
        setWebCallId(callId);
        appendEvent(`Call ID received: ${callId}`);
        const updated = await sessionsService.bindWebCall(session.id, callId);
        setSession(updated);
        appendEvent("Backend session linked to browser call");
      } else {
        appendEvent("Call started without an immediate call ID");
      }
    } catch (caught) {
      setWebCallState("failed");
      setError(caught instanceof Error ? caught.message : "browser_vapi_call_failed");
    }
  }

  async function stopBrowserAssessment() {
    await vapiRef.current?.stop();
    setWebCallState("ended");
    appendEvent("Stop requested");
  }

  async function copyCandidateLink() {
    if (!session) return;
    const link = `${window.location.origin}/demo/${session.id}`;
    try {
      await navigator.clipboard.writeText(link);
      appendEvent("Candidate link copied");
    } catch {
      setError(link);
    }
  }

  function appendEvent(message: string) {
    setEventLog((items) => [new Date().toLocaleTimeString(), message, ...items].slice(0, 10));
  }

  return (
    <div className="min-h-screen bg-background selection:bg-primary/20">
      <header className="flex h-16 items-center border-b bg-background/80 px-6 backdrop-blur-md lg:px-12">
        <Link to="/" className="font-heading text-lg font-bold text-primary">Vocalis.ai</Link>
        <div className="ml-auto flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <Shield className="h-4 w-4" /> Secure Assessment
        </div>
      </header>

      <main className="mx-auto grid min-h-[calc(100vh-4rem)] w-full max-w-6xl gap-8 px-6 py-10 lg:grid-cols-[1fr_380px] lg:items-center">
        <section className="space-y-8">
          <div className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs font-semibold text-muted-foreground">
            <Activity className="h-3.5 w-3.5" />
            {isCoordinator ? "Coordinator handoff" : "Candidate assessment"}
          </div>
          <div className="space-y-4">
            <h1 className="max-w-3xl text-4xl font-heading font-bold tracking-tight sm:text-5xl">
              {isCoordinator ? "Send this assessment to the candidate." : "Prepare for your AI voice assessment."}
            </h1>
            <p className="max-w-2xl text-lg leading-8 text-muted-foreground">
              {isCoordinator
                ? "Admins and assessors do not take the voice assessment here. Share the candidate link or start a phone call from the Candidates page."
                : "This beta flow starts a real Vapi browser call, links the call to the backend session, and lets the webhook pipeline generate the report after the call ends."}
            </p>
          </div>

          {isCoordinator ? (
            <CoordinatorHandoff session={session} onCopyCandidateLink={copyCandidateLink} />
          ) : (
            <>
              <div className="grid gap-4 md:grid-cols-3">
                <ReadinessItem icon={Headphones} title="Quiet room" body="Use headphones and reduce background noise before the call starts." />
                <ReadinessItem icon={Mic} title="Microphone" body="Run the browser check below so audio permission issues are caught early." />
                <ReadinessItem icon={PhoneCall} title="Browser call" body="Use the live browser call path when phone dialing is unavailable for your region." />
              </div>

              <div className="rounded-2xl border bg-card p-5 shadow-sm">
                <div className="mb-4 flex items-center justify-between gap-4">
                  <div>
                    <h2 className="font-heading text-lg font-semibold">Microphone check</h2>
                    <p className="text-sm text-muted-foreground">This uses the real browser permission API. It does not record or upload audio.</p>
                  </div>
                  <MicStateBadge state={micState} />
                </div>
                <Button className="gap-2" onClick={checkMicrophone} disabled={micState === "checking" || !isAssignedCandidate}>
                  <Mic className="h-4 w-4" /> {micState === "checking" ? "Checking..." : "Check microphone"}
                </Button>
                {isAuthenticated && !isAssignedCandidate && (
                  <p className="mt-3 text-sm text-muted-foreground">Sign in as the assigned candidate to use microphone controls.</p>
                )}
              </div>

              <div className="rounded-2xl border bg-card p-5 shadow-sm">
                <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <h2 className="font-heading text-lg font-semibold">Live browser assessment</h2>
                    <p className="text-sm text-muted-foreground">
                      Starts a real Vapi web call through your microphone and links the call ID back to the backend session.
                    </p>
                  </div>
                  <Badge variant={webCallState === "live" ? "default" : "outline"}>{webCallState}</Badge>
                </div>
                <div className="flex flex-wrap gap-3">
                  <Button
                    className="gap-2"
                    onClick={startBrowserAssessment}
                    disabled={!canUseBrowserCall || webCallState === "starting" || webCallState === "live"}
                  >
                    <PhoneCall className="h-4 w-4" />
                    {webCallState === "starting" ? "Connecting..." : "Start browser call"}
                  </Button>
                  <Button
                    className="gap-2"
                    variant="outline"
                    onClick={stopBrowserAssessment}
                    disabled={webCallState !== "live" && webCallState !== "starting"}
                  >
                    <Square className="h-4 w-4" /> Finish call
                  </Button>
                </div>
                {!isAuthenticated && (
                  <p className="mt-3 text-sm text-muted-foreground">Sign in as the assigned candidate before starting the browser call.</p>
                )}
                {session?.status === "completed" && (
                  <p className="mt-3 text-sm text-muted-foreground">This assessment is complete. You can open the report from the button below.</p>
                )}
                {webCallId && <p className="mt-3 font-mono text-xs text-muted-foreground">Web call ID: {webCallId}</p>}
                {(webCallState === "ended" || session?.status === "completed") && session && (
                  <PostCallActions sessionId={session.id} />
                )}
                {eventLog.length > 0 && (
                  <div className="mt-4 rounded-xl border bg-muted/20 p-3">
                    <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Live events</div>
                    <ul className="space-y-1 text-xs text-muted-foreground">
                      {eventLog.map((item, index) => (
                        <li key={`${item}-${index}`}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </>
          )}
        </section>

        <aside className="rounded-2xl border bg-card p-5 shadow-xl">
          <h2 className="font-heading text-xl font-semibold">Session lookup</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Enter a session ID to verify the candidate, assessment, and current call state against the backend.
          </p>

          <div className="mt-5 space-y-3">
            <Input value={sessionId} onChange={(event) => setSessionId(event.target.value)} placeholder="Session UUID" />
            <Button className="w-full" onClick={() => loadSession()} disabled={!isAuthenticated || !sessionId}>
              Load session
            </Button>
            {!isAuthenticated && (
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-800">
                Sign in first to load backend session data.
              </div>
            )}
            {error && <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}</div>}
          </div>

          {session && (
            <div className="mt-6 space-y-4 rounded-xl border bg-muted/20 p-4">
              <div>
                <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Candidate</div>
                <div className="mt-1 font-medium">{session.candidate.full_name}</div>
                <div className="text-sm text-muted-foreground">{session.candidate.email}</div>
              </div>
              <div>
                <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Assessment</div>
                <div className="mt-1 font-medium">{session.assessment.title}</div>
                <div className="text-sm text-muted-foreground">{session.assessment.time_limit_minutes} minutes</div>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm text-muted-foreground">Status</span>
                <Badge variant="outline">{session.status.replace("_", " ")}</Badge>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm text-muted-foreground">Vapi call</span>
                <span className="max-w-[180px] truncate font-mono text-xs">{session.vapi_call_id ?? "not started"}</span>
              </div>
            </div>
          )}
        </aside>
      </main>
    </div>
  );
}

function CoordinatorHandoff({
  session,
  onCopyCandidateLink,
}: {
  session: SessionResponse | null;
  onCopyCandidateLink: () => Promise<void>;
}) {
  return (
    <div className="rounded-2xl border bg-card p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="font-heading text-xl font-semibold">Candidate handoff</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            This page is intentionally not showing microphone controls for admin or assessor accounts. The candidate must sign in and start the assessment from their own account.
          </p>
        </div>
        <Badge variant="outline">No admin microphone</Badge>
      </div>

      {session ? (
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <Button className="gap-2" onClick={onCopyCandidateLink}>
            <Clipboard className="h-4 w-4" /> Copy candidate link
          </Button>
          <Button nativeButton={false} variant="outline" className="gap-2" render={<Link to="/app/candidates" />}>
            <ArrowLeft className="h-4 w-4" /> Back to candidates
          </Button>
          <Button nativeButton={false} variant="outline" className="gap-2 sm:col-span-2" render={<Link to={`/app/reports/${session.id}`} />}>
            <FileText className="h-4 w-4" /> Open report status
          </Button>
        </div>
      ) : (
        <div className="mt-5 rounded-xl border bg-muted/30 p-4 text-sm text-muted-foreground">
          Load a session first to copy its candidate link.
        </div>
      )}
    </div>
  );
}

function PostCallActions({ sessionId }: { sessionId: string }) {
  return (
    <div className="mt-5 rounded-2xl border bg-emerald-500/10 p-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="font-heading text-base font-semibold text-emerald-950">Call finished</h3>
          <p className="mt-1 max-w-xl text-sm leading-6 text-emerald-900/75">
            The backend will receive Vapi webhooks, store the transcript, generate the AI report, and send email when processing completes.
          </p>
        </div>
        <CheckCircle2 className="h-5 w-5 text-emerald-600" />
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button nativeButton={false} size="sm" className="gap-2" render={<Link to={`/app/reports/${sessionId}`} />}>
          <FileText className="h-4 w-4" /> View report status
        </Button>
        <Button nativeButton={false} size="sm" variant="outline" className="gap-2" render={<Link to="/app" />}>
          <ExternalLink className="h-4 w-4" /> Go to dashboard
        </Button>
        <Button size="sm" variant="outline" className="gap-2" onClick={() => window.location.reload()}>
          <RefreshCw className="h-4 w-4" /> Refresh session
        </Button>
      </div>
    </div>
  );
}

function ReadinessItem({ icon: Icon, title, body }: { icon: LucideIcon; title: string; body: string }) {
  return (
    <div className="rounded-2xl border bg-card p-5 shadow-sm">
      <Icon className="mb-4 h-5 w-5 text-primary" />
      <h3 className="font-semibold">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">{body}</p>
    </div>
  );
}

function MicStateBadge({ state }: { state: MicState }) {
  if (state === "granted") {
    return <Badge className="gap-1 bg-emerald-500/10 text-emerald-700"><CheckCircle2 className="h-3.5 w-3.5" /> Ready</Badge>;
  }
  if (state === "blocked" || state === "unsupported") {
    return <Badge className="gap-1 bg-destructive/10 text-destructive"><XCircle className="h-3.5 w-3.5" /> Needs attention</Badge>;
  }
  return <Badge variant="outline">{state === "checking" ? "Checking" : "Not checked"}</Badge>;
}

function stringifyVapiError(value: unknown): string {
  if (value instanceof Error) return value.message;
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return "vapi_error";
  }
}
