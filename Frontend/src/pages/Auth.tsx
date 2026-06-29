import React, { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { motion } from "motion/react";
import {
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  Database,
  Eye,
  EyeOff,
  FileCheck2,
  KeyRound,
  LockKeyhole,
  Mail,
  MailCheck,
  Mic2,
  RadioTower,
  ServerCog,
  ShieldCheck,
  Sparkles,
  UserRound,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { authService, UserRole } from "../services/api";
import { cn } from "../lib/utils";

const demoEmail = "[email-redacted]";
const demoPassword = "DemoAdmin123!";

const statusItems = [
  ["Vapi webhook", "Signed events verified"],
  ["Azure report", "Structured scoring ready"],
  ["Resend email", "Delivery timestamp stored"],
];

const pipelineSteps = [
  { label: "Vapi", icon: RadioTower },
  { label: "Webhook", icon: ServerCog },
  { label: "Azure AI", icon: BrainCircuit },
  { label: "Report", icon: FileCheck2 },
  { label: "Email", icon: MailCheck },
];

const signupRoleOptions: Array<{ value: UserRole; label: string; description: string; badge: string }> = [
  {
    value: "candidate",
    label: "Candidate",
    description: "Take assigned voice assessments and review your own reports.",
    badge: "Open signup",
  },
  {
    value: "assessor",
    label: "Assessor",
    description: "Create assessments, start sessions, and review candidate outcomes.",
    badge: "Invite required",
  },
  {
    value: "admin",
    label: "Admin",
    description: "Manage users, analytics, recovery, and platform operations.",
    badge: "Admin invite",
  },
];

export default function Auth() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const isSignup = searchParams.get("signup") === "true";
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [signupRole, setSignupRole] = useState<UserRole>("candidate");
  const [inviteCode, setInviteCode] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    if (isSignup && signupRole !== "candidate" && inviteCode.trim() === "") {
      setError("invite_code_required_for_staff_signup");
      setIsSubmitting(false);
      return;
    }
    try {
      if (isSignup) {
        await authService.register(
          email,
          password,
          fullName,
          signupRole,
          signupRole === "candidate" ? undefined : inviteCode.trim(),
        );
      } else {
        await authService.login(email, password);
      }
      navigate("/app");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "authentication_failed");
    } finally {
      setIsSubmitting(false);
    }
  };

  const fillDemoAccount = () => {
    setEmail(demoEmail);
    setPassword(demoPassword);
    setError(null);
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-background text-foreground selection:bg-primary/20">
      <div className="premium-grid absolute inset-0 -z-20 opacity-40" />
      <div className="absolute left-0 top-0 -z-10 h-[28rem] w-[28rem] -translate-x-1/2 rounded-full bg-accent/45 blur-3xl" />
      <div className="absolute bottom-0 right-0 -z-10 h-[28rem] w-[28rem] translate-x-1/4 rounded-full bg-chart-3/20 blur-3xl" />

      <div className="mx-auto grid min-h-screen max-w-[92rem] lg:grid-cols-[0.95fr_1.05fr]">
        <section className="flex min-h-screen flex-col px-5 py-6 sm:px-8 lg:px-12">
          <div className="flex items-center justify-between">
            <Link to="/" className="flex w-fit items-center gap-2 font-heading text-xl font-bold">
              <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-lg shadow-primary/15">
                <Mic2 className="h-5 w-5" />
              </span>
              Vocalis.ai
            </Link>
            <Link to="/" className="text-sm font-semibold text-muted-foreground transition hover:text-foreground">
              Home
            </Link>
          </div>

          <div className="flex flex-1 items-center py-10">
            <motion.div
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.45, ease: "easeOut" }}
              className="mx-auto w-full max-w-[30rem]"
            >
              <div className="mb-6">
                <span className="inline-flex items-center gap-2 rounded-full border bg-card/80 px-3 py-1 text-sm font-semibold text-muted-foreground shadow-sm">
                  <ShieldCheck className="h-4 w-4 text-emerald-600" />
                  Assessment command center
                </span>
                <h1 className="mt-6 text-4xl font-bold tracking-[-0.045em] sm:text-5xl">
                  {isSignup ? "Set up your secure workspace." : "Sign in to your live demo workspace."}
                </h1>
                <p className="mt-4 max-w-md text-base leading-7 text-muted-foreground">
                  {isSignup
                    ? "Create access for assessment operations, candidate sessions, reports, and admin analytics."
                    : "Review sessions, inspect candidate reports, and verify the voice-to-report workflow."}
                </p>
              </div>

              <div className="mb-5 grid grid-cols-2 rounded-2xl border bg-card/70 p-1 shadow-sm">
                <Link
                  to="/auth"
                  className={cn(
                    "rounded-xl px-4 py-2.5 text-center text-sm font-semibold transition",
                    !isSignup ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  Sign in
                </Link>
                <Link
                  to="/auth?signup=true"
                  className={cn(
                    "rounded-xl px-4 py-2.5 text-center text-sm font-semibold transition",
                    isSignup ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  Request access
                </Link>
              </div>

              <form className="rounded-[1.6rem] border bg-card/90 p-5 shadow-[0_26px_90px_rgba(15,23,42,0.10)] backdrop-blur-xl sm:p-6" onSubmit={handleAuth}>
                <div className="space-y-5">
                  {isSignup && (
                    <>
                      <div className="space-y-2">
                        <Label htmlFor="fullName">Full name</Label>
                        <div className="relative">
                          <UserRound className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                          <Input
                            id="fullName"
                            value={fullName}
                            onChange={(event) => setFullName(event.target.value)}
                            required
                            className="h-12 rounded-2xl bg-background/80 pl-10"
                            placeholder="Alex Morgan"
                          />
                        </div>
                      </div>

                      <div className="space-y-3">
                        <div>
                          <Label>Choose your portal</Label>
                          <p className="mt-1 text-xs leading-5 text-muted-foreground">
                            Candidates can self-register. Staff and admin accounts require an invite code.
                          </p>
                        </div>
                        <div className="grid gap-2">
                          {signupRoleOptions.map((option) => (
                            <button
                              key={option.value}
                              type="button"
                              onClick={() => {
                                setSignupRole(option.value);
                                setError(null);
                              }}
                              className={cn(
                                "rounded-2xl border p-3 text-left transition hover:border-primary/40 hover:bg-primary/5",
                                signupRole === option.value
                                  ? "border-primary bg-primary/10 shadow-sm"
                                  : "border-border bg-background/70",
                              )}
                            >
                              <span className="flex items-start justify-between gap-3">
                                <span>
                                  <span className="block text-sm font-semibold">{option.label}</span>
                                  <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                                    {option.description}
                                  </span>
                                </span>
                                <span
                                  className={cn(
                                    "shrink-0 rounded-full px-2 py-1 text-[0.68rem] font-bold uppercase tracking-wide",
                                    signupRole === option.value
                                      ? "bg-primary text-primary-foreground"
                                      : "bg-muted text-muted-foreground",
                                  )}
                                >
                                  {option.badge}
                                </span>
                              </span>
                            </button>
                          ))}
                        </div>
                      </div>

                      {signupRole !== "candidate" && (
                        <div className="space-y-2">
                          <Label htmlFor="inviteCode">{signupRole === "admin" ? "Admin invite code" : "Staff invite code"}</Label>
                          <div className="relative">
                            <LockKeyhole className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                            <Input
                              id="inviteCode"
                              value={inviteCode}
                              onChange={(event) => setInviteCode(event.target.value)}
                              required
                              className="h-12 rounded-2xl bg-background/80 pl-10"
                              placeholder="Paste invite code"
                            />
                          </div>
                        </div>
                      )}
                    </>
                  )}

                  <div className="space-y-2">
                    <Label htmlFor="email">Email</Label>
                    <div className="relative">
                      <Mail className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                      <Input
                        id="email"
                        type="email"
                        placeholder="[email-redacted]"
                        value={email}
                        onChange={(event) => setEmail(event.target.value)}
                        required
                        className="h-12 rounded-2xl bg-background/80 pl-10"
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label htmlFor="password">Password</Label>
                      <span className="text-xs font-semibold text-muted-foreground" title="Password reset is not enabled in this backend yet.">
                        Forgot password?
                      </span>
                    </div>
                    <div className="relative">
                      <KeyRound className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                      <Input
                        id="password"
                        type={showPassword ? "text" : "password"}
                        value={password}
                        onChange={(event) => setPassword(event.target.value)}
                        minLength={isSignup ? 8 : 1}
                        required
                        className="h-12 rounded-2xl bg-background/80 pl-10 pr-11"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword((value) => !value)}
                        className="absolute right-3 top-1/2 rounded-md p-1 text-muted-foreground transition hover:text-foreground"
                        aria-label={showPassword ? "Hide password" : "Show password"}
                      >
                        {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>

                  {error && (
                    <div className="rounded-2xl border border-destructive/20 bg-destructive/10 px-3 py-3 text-sm font-medium text-destructive">
                      {error}
                    </div>
                  )}

                  <Button type="submit" className="h-12 w-full rounded-2xl text-base font-semibold shadow-lg shadow-primary/15" disabled={isSubmitting}>
                    {isSubmitting ? "Working..." : isSignup ? "Create account" : "Enter workspace"}
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </Button>
                </div>

                {!isSignup && (
                  <button
                    type="button"
                    onClick={fillDemoAccount}
                    disabled={isSubmitting}
                    className="mt-5 flex w-full items-center justify-between rounded-2xl border bg-background/70 px-4 py-3 text-left transition hover:bg-background disabled:opacity-60"
                  >
                    <span>
                      <span className="block text-sm font-semibold">Use demo admin account</span>
                      <span className="mt-0.5 block text-xs text-muted-foreground">{demoEmail}</span>
                    </span>
                    <span className="rounded-full bg-primary/10 p-2 text-primary">
                      <ArrowRight className="h-4 w-4" />
                    </span>
                  </button>
                )}

                {!isSignup && (
                  <div className="mt-4 rounded-2xl border bg-background/70 px-4 py-3 text-sm text-muted-foreground">
                    Login is role-aware automatically. Your account opens the candidate, assessor, or admin portal after sign in.
                  </div>
                )}
              </form>

              <p className="mt-6 text-center text-sm text-muted-foreground">
                {isSignup ? "Already approved?" : "Need a new workspace?"}{" "}
                <Link to={isSignup ? "/auth" : "/auth?signup=true"} className="font-semibold text-foreground hover:underline">
                  {isSignup ? "Sign in" : "Request access"}
                </Link>
              </p>
            </motion.div>
          </div>
        </section>

        <section className="hidden min-h-screen p-5 lg:block">
          <div className="relative flex h-full overflow-hidden rounded-[2.25rem] bg-[#06131f] p-8 text-white shadow-[0_30px_100px_rgba(15,23,42,0.25)]">
            <div className="absolute inset-0 bg-[linear-gradient(135deg,rgba(20,184,166,0.32),rgba(8,47,73,0.24)_42%,rgba(15,23,42,0.10)),linear-gradient(315deg,rgba(56,189,248,0.22),transparent_48%)]" />
            <div className="premium-grid absolute inset-0 opacity-[0.08]" />

            <div className="relative z-10 flex w-full flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-sm font-semibold text-white/85 backdrop-blur">
                  <Sparkles className="h-4 w-4 text-cyan-200" />
                  Demo proof verified
                </span>
                <span className="rounded-full bg-emerald-400/20 px-3 py-1 text-sm font-bold text-emerald-100">
                  Ready
                </span>
              </div>

              <motion.div
                initial={{ y: 18 }}
                animate={{ y: 0 }}
                transition={{ duration: 0.55, delay: 0.1 }}
                className="mx-auto w-full max-w-2xl"
              >
                <div className="mb-6">
                  <p className="text-sm font-semibold uppercase tracking-[0.24em] text-cyan-100/70">Assessment OS</p>
                  <h2 className="mt-3 max-w-xl text-5xl font-semibold leading-tight tracking-[-0.05em]">
                    Voice signal, scored and delivered.
                  </h2>
                </div>

                <div className="grid gap-4">
                  <div className="grid grid-cols-5 gap-2">
                    {pipelineSteps.map((step, index) => (
                      <div key={step.label} className="relative rounded-2xl border border-white/12 bg-white/[0.10] p-3 text-center backdrop-blur">
                        {index < pipelineSteps.length - 1 && (
                          <span className="absolute left-[calc(100%-0.25rem)] top-1/2 h-px w-3 bg-cyan-200/45" />
                        )}
                        <step.icon className="mx-auto h-5 w-5 text-cyan-100" />
                        <div className="mt-2 text-xs font-semibold text-white/78">{step.label}</div>
                      </div>
                    ))}
                  </div>

                  <div className="grid gap-4 lg:grid-cols-[1fr_0.82fr]">
                    <div className="rounded-[1.5rem] border border-cyan-200/15 bg-[#020b14] p-5 shadow-2xl">
                      <div className="flex items-center justify-between">
                        <span className="flex items-center gap-2 text-sm font-semibold text-white/75">
                          <Mic2 className="h-4 w-4 text-cyan-200" /> Candidate voice session
                        </span>
                        <span className="rounded-full bg-cyan-300/15 px-2.5 py-1 text-xs font-semibold text-cyan-100">
                          completed
                        </span>
                      </div>
                      <div className="mt-5 flex h-24 items-center gap-1">
                        {Array.from({ length: 34 }).map((_, index) => (
                          <span
                            key={index}
                            className="w-1 flex-1 rounded-full bg-cyan-200"
                            style={{ height: `${22 + ((index * 17) % 64)}%` }}
                          />
                        ))}
                      </div>
                      <div className="mt-5 grid grid-cols-2 gap-3 text-xs">
                        <div className="rounded-xl bg-white/8 p-3">
                          <span className="block text-white/50">Call ID</span>
                          <span className="mt-1 block font-mono text-cyan-100">019e82ea</span>
                        </div>
                        <div className="rounded-xl bg-white/8 p-3">
                          <span className="block text-white/50">Transcript</span>
                          <span className="mt-1 block font-semibold text-emerald-100">captured</span>
                        </div>
                      </div>
                    </div>

                    <div className="grid gap-4">
                      <div className="rounded-[1.5rem] border border-emerald-200/30 bg-emerald-50 p-5 text-emerald-950 shadow-xl">
                        <div className="flex items-start justify-between">
                          <div>
                            <p className="text-sm font-bold text-emerald-700">AI report score</p>
                            <p className="mt-2 font-mono text-5xl font-semibold">88.5</p>
                          </div>
                          <span className="rounded-full bg-emerald-600 px-3 py-1 text-xs font-bold uppercase tracking-wide text-white">
                            pass
                          </span>
                        </div>
                      </div>
                      <div className="rounded-[1.5rem] border border-white/12 bg-white/[0.10] p-5 backdrop-blur">
                        <p className="flex items-center gap-2 text-sm font-semibold text-white/75">
                          <Database className="h-4 w-4" /> Session state
                        </p>
                        <div className="mt-4 space-y-2">
                          {["Webhook idempotency", "Report persisted", "Email timestamp"].map((item) => (
                            <div key={item} className="flex items-center justify-between text-sm">
                              <span className="text-white/62">{item}</span>
                              <CheckCircle2 className="h-4 w-4 text-emerald-200" />
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="grid gap-3">
                    {statusItems.map(([title, body]) => (
                      <div key={title} className="rounded-2xl border border-white/12 bg-white/[0.10] p-4 backdrop-blur">
                        <div className="flex items-center gap-3">
                          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-400/15">
                            <CheckCircle2 className="h-5 w-5 text-emerald-200" />
                          </span>
                          <div>
                            <h3 className="font-semibold text-white">{title}</h3>
                            <p className="text-sm text-white/60">{body}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="grid grid-cols-3 gap-3 text-sm text-white/90">
                    {["No mock login", "Real backend", "Browser tested"].map((item) => (
                      <div key={item} className="rounded-2xl border border-white/15 bg-white/[0.10] p-4 font-semibold backdrop-blur shadow-lg">
                        {item}
                      </div>
                    ))}
                  </div>
                </div>
              </motion.div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
