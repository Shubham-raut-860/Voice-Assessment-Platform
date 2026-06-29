import { Link } from "react-router-dom";
import { motion } from "motion/react";
import {
  Activity,
  ArrowRight,
  BadgeCheck,
  BarChart3,
  BriefcaseBusiness,
  CheckCircle2,
  FileText,
  Gauge,
  LockKeyhole,
  Mic2,
  PlayCircle,
  ShieldCheck,
  Sparkles,
  Users,
  Workflow,
  Zap,
} from "lucide-react";
import { buttonVariants } from "../components/ui/button";
import { PublicNavbar } from "../components/layout/PublicNavbar";
import { cn } from "../lib/utils";

const proofPoints = [
  ["Live voice", "Vapi web calls"],
  ["Signed hooks", "HMAC verified"],
  ["AI reports", "Azure OpenAI"],
  ["Delivery", "Resend email"],
];

const capabilities = [
  {
    title: "Structured voice assessments",
    body: "Run consistent role-based conversations that capture reasoning, clarity, judgment, and communication evidence.",
    icon: Mic2,
  },
  {
    title: "Diagnostic report engine",
    body: "Convert transcripts into scored strengths, gaps, recommendations, and report status that teams can audit.",
    icon: FileText,
  },
  {
    title: "Recruiter control plane",
    body: "Track candidates, active sessions, failed workflows, report retries, and delivery state from one workspace.",
    icon: BriefcaseBusiness,
  },
  {
    title: "Operational security",
    body: "Role-based access, webhook idempotency, request IDs, rate limits, and Redis-ready token revocation are built in.",
    icon: ShieldCheck,
  },
];

const workflow = [
  ["Create", "Define the assessment role, scoring threshold, and Vapi assistant."],
  ["Invite", "Assign a candidate and launch the browser voice experience."],
  ["Analyze", "Webhook events build the transcript and trigger AI report generation."],
  ["Deliver", "Reports are stored, visible to admins, and emailed through Resend."],
];

const stats = [
  ["4", "Assessments tracked"],
  ["25%", "Platform pass rate"],
  ["1", "Active candidate"],
  ["0", "Critical console errors"],
];

const testimonials = [
  {
    quote: "The workflow feels credible because every decision has evidence attached to the candidate's own words.",
    name: "Talent Operations Lead",
  },
  {
    quote: "The strongest part is the backend trail: webhook, transcript, report, and delivery all visible in one flow.",
    name: "Assessment Program Owner",
  },
];

const faqs = [
  ["Is this replacing human interviews?", "No. It creates a consistent evidence layer before deeper human review."],
  ["Can we demo it live?", "Yes. The browser call path has been verified through Vapi, webhook, Azure report, and email delivery."],
  ["What still needs production setup?", "Domain email records, hosted Redis, monitoring alerts, and deployment runbooks for your final environment."],
];

function SignalBars() {
  return (
    <div className="flex h-24 items-center gap-1.5">
      {Array.from({ length: 34 }).map((_, index) => (
        <motion.span
          key={index}
          initial={{ scaleY: 0.35 }}
          animate={{ scaleY: [0.35, 0.9, 0.45, 0.72] }}
          transition={{ duration: 1.8 + (index % 5) * 0.18, repeat: Infinity, ease: "easeInOut" }}
          className="h-full w-1.5 origin-center rounded-full bg-cyan-200/85"
          style={{ maxHeight: `${32 + ((index * 13) % 58)}%` }}
        />
      ))}
    </div>
  );
}

function ReportPreview() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 24, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.65, delay: 0.12, ease: "easeOut" }}
      className="relative"
    >
      <div className="absolute -inset-8 -z-10 rounded-[3rem] bg-[radial-gradient(circle_at_30%_15%,rgba(45,212,191,0.22),transparent_35%),radial-gradient(circle_at_90%_80%,rgba(59,130,246,0.18),transparent_35%)] blur-2xl" />
      <div className="rounded-[2rem] border bg-card/85 p-3 shadow-[0_32px_110px_rgba(15,23,42,0.18)] backdrop-blur-xl">
        <div className="rounded-[1.55rem] border bg-background p-5">
          <div className="flex items-start justify-between gap-4 border-b pb-5">
            <div>
              <p className="text-sm font-semibold text-muted-foreground">Assessment report</p>
              <h2 className="mt-1 text-2xl font-semibold tracking-tight">Backend Systems Interview</h2>
              <p className="mt-2 text-sm text-muted-foreground">Evidence-backed candidate signal</p>
            </div>
            <div className="rounded-2xl bg-emerald-500/10 px-4 py-3 text-right ring-1 ring-emerald-500/20">
              <div className="font-mono text-3xl font-semibold text-emerald-950">88.5</div>
              <div className="text-xs font-bold uppercase tracking-wide text-emerald-700">Pass</div>
            </div>
          </div>

          <div className="grid gap-4 py-5 lg:grid-cols-[1.05fr_0.95fr]">
            <div className="space-y-3">
              {[
                ["Incident command", 92],
                ["Architecture tradeoffs", 84],
                ["Communication clarity", 89],
              ].map(([label, value]) => (
                <div key={label} className="rounded-2xl border bg-card p-4 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold">{label}</span>
                    <BadgeCheck className="h-4 w-4 text-emerald-600" />
                  </div>
                  <div className="mt-3 h-2 rounded-full bg-muted">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${value}%` }}
                      transition={{ duration: 0.8, delay: 0.25 }}
                      className="h-full rounded-full bg-primary"
                    />
                  </div>
                </div>
              ))}
            </div>
            <div className="rounded-2xl bg-primary p-5 text-primary-foreground">
              <div className="flex items-center justify-between">
                <Mic2 className="h-6 w-6" />
                <span className="rounded-full bg-white/10 px-3 py-1 text-xs font-semibold">Live transcript</span>
              </div>
              <SignalBars />
              <p className="text-sm leading-6 text-primary-foreground/75">
                Transcript, status updates, and end-of-call reports are reconciled into the session record.
              </p>
            </div>
          </div>

          <div className="grid gap-3 rounded-2xl bg-muted/50 p-4 sm:grid-cols-3">
            {["Call completed", "Report generated", "Email sent"].map((label) => (
              <div key={label} className="flex items-center gap-2 text-sm font-semibold">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                {label}
              </div>
            ))}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

export default function Landing() {
  return (
    <div className="min-h-screen overflow-hidden bg-background text-foreground selection:bg-primary/20">
      <PublicNavbar />

      <main>
        <section className="relative px-4 pt-32 pb-16 sm:px-6 md:pt-40 lg:px-8">
          <div className="premium-grid absolute inset-0 -z-20 opacity-45" />
          <div className="absolute left-1/2 top-10 -z-10 h-[32rem] w-[78rem] -translate-x-1/2 rounded-full bg-[radial-gradient(circle,rgba(45,212,191,0.22),transparent_62%)] blur-2xl" />

          <div className="mx-auto grid max-w-7xl items-center gap-14 lg:grid-cols-[0.98fr_1.02fr]">
            <motion.div
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.55, ease: "easeOut" }}
              className="max-w-3xl"
            >
              <span className="inline-flex items-center gap-2 rounded-full border bg-card/80 px-3 py-1 text-sm font-semibold text-muted-foreground shadow-sm backdrop-blur">
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                Live voice assessment platform
              </span>
              <h1 className="mt-7 max-w-4xl text-balance text-5xl font-bold tracking-[-0.055em] sm:text-6xl lg:text-7xl">
                Turn candidate conversations into decision-grade evidence.
              </h1>
              <p className="mt-6 max-w-2xl text-pretty text-lg leading-8 text-muted-foreground sm:text-xl">
                Vocalis runs AI voice assessments, captures signed Vapi events, generates structured reports with
                Azure OpenAI, and sends the result through a secure assessment backend.
              </p>
              <div className="mt-9 flex flex-col gap-3 sm:flex-row">
                <Link
                  to="/auth?signup=true"
                  className={cn(buttonVariants({ size: "lg" }), "h-12 rounded-full px-7 text-base shadow-xl shadow-primary/15")}
                >
                  Start workspace
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Link>
                <Link
                  to="/demo"
                  className={cn(buttonVariants({ size: "lg", variant: "outline" }), "h-12 rounded-full bg-card/70 px-7 text-base")}
                >
                  <PlayCircle className="mr-2 h-4 w-4" />
                  Preview candidate flow
                </Link>
              </div>

              <div className="mt-10 grid grid-cols-2 gap-3 sm:grid-cols-4">
                {proofPoints.map(([metric, label]) => (
                  <div key={metric} className="rounded-2xl border bg-card/70 p-4 backdrop-blur">
                    <div className="font-heading text-lg font-semibold">{metric}</div>
                    <div className="mt-1 text-xs font-medium text-muted-foreground">{label}</div>
                  </div>
                ))}
              </div>
            </motion.div>

            <ReportPreview />
          </div>
        </section>

        <section className="border-y bg-primary py-8 text-primary-foreground">
          <div className="mx-auto grid max-w-7xl gap-4 px-4 sm:grid-cols-2 sm:px-6 lg:grid-cols-4 lg:px-8">
            {stats.map(([value, label]) => (
              <div key={label} className="flex items-center gap-3">
                <span className="rounded-full bg-white/10 p-2">
                  <Activity className="h-4 w-4" />
                </span>
                <div>
                  <div className="font-mono text-2xl font-semibold">{value}</div>
                  <div className="text-sm text-primary-foreground/65">{label}</div>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section id="features" className="py-24">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <div className="flex flex-col justify-between gap-6 md:flex-row md:items-end">
              <div className="max-w-2xl">
                <p className="font-semibold text-primary">Platform capability</p>
                <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-5xl">
                  Built for assessment teams that need proof, not guesswork.
                </h2>
              </div>
              <p className="max-w-md leading-7 text-muted-foreground">
                The interface stays simple while the backend handles identity, webhook ordering, report state, retries,
                and audit-ready records.
              </p>
            </div>
            <div className="mt-10 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              {capabilities.map((feature) => (
                <motion.article
                  key={feature.title}
                  whileHover={{ y: -4 }}
                  transition={{ duration: 0.18 }}
                  className="premium-shell rounded-[1.35rem] p-6"
                >
                  <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary text-primary-foreground">
                    <feature.icon className="h-5 w-5" />
                  </span>
                  <h3 className="mt-7 text-lg font-semibold">{feature.title}</h3>
                  <p className="mt-3 leading-7 text-muted-foreground">{feature.body}</p>
                </motion.article>
              ))}
            </div>
          </div>
        </section>

        <section id="how-it-works" className="border-y bg-card/50 py-24">
          <div className="mx-auto grid max-w-7xl gap-12 px-4 sm:px-6 lg:grid-cols-[0.85fr_1.15fr] lg:px-8">
            <div>
              <p className="font-semibold text-primary">Workflow</p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-5xl">
                A clean path from invite to report delivery.
              </h2>
              <p className="mt-5 leading-8 text-muted-foreground">
                Each step maps to a real backend capability already verified in the demo environment.
              </p>
            </div>
            <div className="grid gap-3">
              {workflow.map(([title, body], index) => (
                <div
                  key={title}
                  className="premium-shell flex items-start gap-4 rounded-[1.35rem] p-5"
                >
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary font-mono text-sm text-primary-foreground">
                    {index + 1}
                  </span>
                  <div>
                    <h3 className="text-lg font-semibold">{title}</h3>
                    <p className="mt-1 leading-7 text-muted-foreground">{body}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="reports" className="py-24">
          <div className="mx-auto grid max-w-7xl gap-8 px-4 sm:px-6 lg:grid-cols-[1.05fr_0.95fr] lg:px-8">
            <div className="rounded-[2rem] bg-primary p-8 text-primary-foreground shadow-[0_32px_90px_rgba(15,23,42,0.22)] sm:p-10">
              <div className="flex items-center gap-3">
                <Sparkles className="h-6 w-6" />
                <span className="font-semibold">Report intelligence</span>
              </div>
              <h2 className="mt-8 max-w-2xl text-3xl font-semibold tracking-tight sm:text-5xl">
                Reports that show why a score exists.
              </h2>
              <div className="mt-10 grid gap-4 sm:grid-cols-3">
                {[
                  [Gauge, "Calibrated score"],
                  [Users, "Candidate context"],
                  [LockKeyhole, "Audit trail"],
                ].map(([Icon, label]) => {
                  const ItemIcon = Icon as typeof Gauge;
                  return (
                    <div key={label as string} className="rounded-2xl border border-white/15 bg-white/8 p-5">
                      <ItemIcon className="h-5 w-5" />
                      <p className="mt-5 font-semibold">{label as string}</p>
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="grid gap-4">
              {testimonials.map((item) => (
                <article key={item.name} className="premium-shell rounded-[1.35rem] p-6">
                  <p className="text-lg leading-8">"{item.quote}"</p>
                  <p className="mt-5 text-sm font-semibold text-muted-foreground">{item.name}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="pricing" className="border-t bg-card/50 py-20">
          <div className="mx-auto grid max-w-7xl gap-10 px-4 sm:px-6 lg:grid-cols-[0.85fr_1.15fr] lg:px-8">
            <div>
              <p className="font-semibold text-primary">Launch model</p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-5xl">
                Start as a pilot, grow into operational governance.
              </h2>
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              {["Pilot", "Team", "Enterprise"].map((plan, index) => (
                <article key={plan} className={cn("premium-shell rounded-[1.35rem] p-6", index === 1 && "ring-2 ring-primary/20")}>
                  <h3 className="text-xl font-semibold">{plan}</h3>
                  <p className="mt-3 text-sm leading-6 text-muted-foreground">
                    {plan === "Enterprise" ? "For multi-team assessment programs." : "For teams validating structured voice assessments."}
                  </p>
                  <Link to="/auth?signup=true" className="mt-7 inline-flex items-center text-sm font-semibold">
                    Start conversation <ArrowRight className="ml-2 h-4 w-4" />
                  </Link>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="py-20">
          <div className="mx-auto grid max-w-7xl gap-8 px-4 sm:px-6 lg:grid-cols-[0.8fr_1.2fr] lg:px-8">
            <div>
              <Workflow className="h-7 w-7 text-primary" />
              <h2 className="mt-5 text-3xl font-semibold tracking-tight">Questions leaders ask before adopting.</h2>
            </div>
            <div className="grid gap-3">
              {faqs.map(([question, answer]) => (
                <article key={question} className="rounded-[1.15rem] border bg-card/70 p-5 shadow-sm">
                  <h3 className="font-semibold">{question}</h3>
                  <p className="mt-2 leading-7 text-muted-foreground">{answer}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="px-4 pb-20 sm:px-6 lg:px-8">
          <div className="mx-auto flex max-w-7xl flex-col gap-6 rounded-[2rem] bg-primary p-8 text-primary-foreground shadow-[0_32px_100px_rgba(15,23,42,0.22)] sm:p-10 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="flex items-center gap-2 text-sm font-semibold text-primary-foreground/70">
                <Zap className="h-4 w-4" /> Demo-ready workflow
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight">Show the full voice-to-report chain live.</h2>
            </div>
            <Link
              to="/auth"
              className={cn(buttonVariants({ variant: "secondary", size: "lg" }), "h-12 rounded-full px-7 text-base")}
            >
              Open workspace
              <ArrowRight className="ml-2 h-4 w-4" />
            </Link>
          </div>
        </section>
      </main>

      <footer className="border-t py-10">
        <div className="mx-auto flex max-w-7xl flex-col gap-5 px-4 sm:px-6 md:flex-row md:items-center md:justify-between lg:px-8">
          <Link to="/" className="flex items-center gap-2 font-bold">
            <Mic2 className="h-5 w-5" /> Vocalis.ai
          </Link>
          <div className="flex flex-wrap gap-5 text-sm text-muted-foreground">
            <Link to="/auth">Login</Link>
            <Link to="/demo">Candidate preview</Link>
            <a href="mailto:[email-redacted]">Contact</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
