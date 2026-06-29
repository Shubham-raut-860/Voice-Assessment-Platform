import { type FormEvent, useEffect, useMemo, useState } from "react";
import { Archive, CheckCircle2, ClipboardList, Plus, RotateCcw } from "lucide-react";
import { AssessmentResponse, AssessmentStatus, assessmentsService } from "../services/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Badge } from "../components/ui/badge";

const statusTone: Record<AssessmentStatus, string> = {
  draft: "bg-muted text-muted-foreground",
  active: "bg-emerald-500/10 text-emerald-700",
  completed: "bg-blue-500/10 text-blue-700",
  archived: "bg-amber-500/10 text-amber-700",
};

export default function Assessments() {
  const [assessments, setAssessments] = useState<AssessmentResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    title: "",
    description: "",
    vapi_assistant_id: "",
    passing_score: "75.00",
    time_limit_minutes: "30",
    status: "active" as AssessmentStatus,
  });

  const activeCount = useMemo(() => assessments.filter((item) => item.status === "active").length, [assessments]);

  useEffect(() => {
    void loadAssessments();
  }, []);

  async function loadAssessments() {
    setIsLoading(true);
    setError(null);
    try {
      const response = await assessmentsService.list(1, 100);
      setAssessments(response.items);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "assessments_load_failed");
    } finally {
      setIsLoading(false);
    }
  }

  async function createAssessment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSaving(true);
    setError(null);
    try {
      await assessmentsService.create({
        title: form.title,
        description: form.description,
        vapi_assistant_id: form.vapi_assistant_id,
        passing_score: Number(form.passing_score).toFixed(2),
        time_limit_minutes: Number(form.time_limit_minutes),
        status: form.status,
      });
      setForm({
        title: "",
        description: "",
        vapi_assistant_id: "",
        passing_score: "75.00",
        time_limit_minutes: "30",
        status: "active",
      });
      await loadAssessments();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "assessment_create_failed");
    } finally {
      setIsSaving(false);
    }
  }

  async function setAssessmentStatus(assessment: AssessmentResponse, status: AssessmentStatus) {
    setError(null);
    try {
      await assessmentsService.update(assessment.id, { status });
      await loadAssessments();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "assessment_update_failed");
    }
  }

  async function archiveAssessment(assessment: AssessmentResponse) {
    setError(null);
    try {
      await assessmentsService.archive(assessment.id);
      await loadAssessments();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "assessment_archive_failed");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border bg-background px-3 py-1 text-xs font-semibold text-muted-foreground">
            <ClipboardList className="h-3.5 w-3.5" />
            Assessment Library
          </div>
          <h1 className="text-3xl font-heading font-semibold tracking-tight">Assessments</h1>
          <p className="mt-1 text-muted-foreground">
            Configure Vapi-backed assessment templates and keep demo-ready flows organized.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:flex">
          <div className="rounded-xl border bg-card px-4 py-3">
            <div className="text-xs font-medium text-muted-foreground">Total</div>
            <div className="text-2xl font-semibold">{assessments.length}</div>
          </div>
          <div className="rounded-xl border bg-card px-4 py-3">
            <div className="text-xs font-medium text-muted-foreground">Active</div>
            <div className="text-2xl font-semibold">{activeCount}</div>
          </div>
        </div>
      </div>

      {error && <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}

      <form onSubmit={createAssessment} className="rounded-xl border bg-card p-5 shadow-sm">
        <div className="mb-5 flex items-center gap-2">
          <Plus className="h-4 w-4 text-primary" />
          <h2 className="font-heading text-lg font-semibold">Create assessment</h2>
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="title">Title</Label>
            <Input id="title" required value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="assistant">Vapi assistant UUID</Label>
            <Input id="assistant" required value={form.vapi_assistant_id} onChange={(event) => setForm({ ...form, vapi_assistant_id: event.target.value })} />
          </div>
          <div className="space-y-2 lg:col-span-2">
            <Label htmlFor="description">Description</Label>
            <Input id="description" required value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="score">Passing score</Label>
            <Input id="score" type="number" min="0" max="100" step="0.01" value={form.passing_score} onChange={(event) => setForm({ ...form, passing_score: event.target.value })} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="time-limit">Time limit minutes</Label>
            <Input id="time-limit" type="number" min="1" max="1440" value={form.time_limit_minutes} onChange={(event) => setForm({ ...form, time_limit_minutes: event.target.value })} />
          </div>
        </div>
        <div className="mt-5 flex justify-end">
          <Button type="submit" disabled={isSaving}>{isSaving ? "Creating..." : "Create assessment"}</Button>
        </div>
      </form>

      <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
        <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 border-b bg-muted/30 px-4 py-3 text-sm font-semibold text-muted-foreground">
          <span>Assessment templates</span>
          <span>Status and actions</span>
        </div>

        {isLoading ? (
          <div className="px-4 py-10 text-center text-sm text-muted-foreground">Loading assessments...</div>
        ) : assessments.length === 0 ? (
          <div className="px-4 py-10 text-center text-sm text-muted-foreground">No assessments yet.</div>
        ) : (
          <div className="divide-y">
            {assessments.map((assessment) => (
              <div key={assessment.id} className="grid gap-4 p-4 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-center">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-heading text-base font-semibold">{assessment.title}</h3>
                    <Badge className={statusTone[assessment.status]}>{assessment.status}</Badge>
                  </div>
                  <p className="mt-2 line-clamp-2 max-w-4xl text-sm leading-6 text-muted-foreground">
                    {assessment.description}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
                    <span className="rounded-full border bg-background px-2.5 py-1">
                      Passing {assessment.passing_score}
                    </span>
                    <span className="rounded-full border bg-background px-2.5 py-1">
                      {assessment.time_limit_minutes} minutes
                    </span>
                    <span className="max-w-full truncate rounded-full border bg-background px-2.5 py-1 font-mono">
                      Assistant {assessment.vapi_assistant_id}
                    </span>
                  </div>
                </div>

                <div className="flex flex-wrap justify-start gap-2 xl:justify-end">
                  <Button variant="outline" size="sm" className="gap-2" onClick={() => setAssessmentStatus(assessment, "active")}>
                    <CheckCircle2 className="h-4 w-4" /> Active
                  </Button>
                  <Button variant="outline" size="sm" className="gap-2" onClick={() => setAssessmentStatus(assessment, "draft")}>
                    <RotateCcw className="h-4 w-4" /> Draft
                  </Button>
                  <Button variant="outline" size="sm" className="gap-2 text-destructive" onClick={() => archiveAssessment(assessment)}>
                    <Archive className="h-4 w-4" /> Archive
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
