import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, CheckCircle2, AlertTriangle, FileText, Download, Target, Lightbulb, Clock, RefreshCw } from "lucide-react";
import { AssessmentReport, Analytics } from "../types";
import { reportsService, analyticsService } from "../services/api";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Progress } from "../components/ui/progress";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from 'recharts';
import { motion } from 'motion/react';
import { downloadReportAsPDF } from "../lib/pdf";

export default function ReportViewer() {
  const { id } = useParams<{ id: string }>();
  const [report, setReport] = useState<AssessmentReport | null>(null);
  const [stats, setStats] = useState<Analytics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (id) {
      reportsService.getReport(id).then(setReport).catch((caught) => {
        setError(caught instanceof Error ? caught.message : "report_load_failed");
      });
    }
    analyticsService.getStats().then(setStats).catch(() => undefined);
  }, [id]);

  if (error) return <ReportStatusMessage code={error} />;
  if (!report) return <div className="p-8 text-center text-muted-foreground animate-pulse">Analyzing transcript...</div>;

  const isPass = report.passFail === 'pass';

  const chartData = report?.strengths.concat(report?.weaknesses).map(finding => {
    const orgAvgItem = stats?.competencyAverages?.find(c => c.area === finding.area);
    return {
      name: finding.area,
      Candidate: finding.score,
      'Org Average': orgAvgItem ? orgAvgItem.avgScore : 72
    }
  }) || [];

  return (
    <div className="max-w-5xl mx-auto space-y-8 pb-12">
      <div className="flex items-center justify-between print-hide">
        <div className="space-y-1">
           <Link to="/app" className="inline-flex items-center text-sm font-medium text-muted-foreground hover:text-foreground mb-4">
             <ArrowLeft className="mr-2 h-4 w-4" /> Back to pipeline
           </Link>
           <h1 className="text-3xl font-heading font-semibold tracking-tight tracking-tight flex items-center gap-3">
             Executive Summary
             <Badge variant={isPass ? 'default' : 'destructive'} className={`text-sm px-3 py-0.5 ${isPass ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 hover:bg-emerald-500/25 border-none' : ''}`}>
               {isPass ? 'Strong Hire' : 'No Hire'}
             </Badge>
           </h1>
           <p className="text-muted-foreground">Generated {report.date}{report.modelUsed ? ` via ${report.modelUsed}` : ""}</p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="outline" className="gap-2" onClick={downloadReportAsPDF}>
            <Download className="h-4 w-4" /> Export PDF
          </Button>
          <Button className="gap-2">
            <FileText className="h-4 w-4" /> View Full Transcript
          </Button>
        </div>
      </div>

      <div className="grid md:grid-cols-3 gap-6">
        <Card className="md:col-span-1 bg-muted/20 border-border/50 flex flex-col justify-center items-center p-8">
           <div className="text-sm font-medium text-muted-foreground uppercase tracking-widest mb-4">Overall AI Score</div>
           <div className="relative flex items-center justify-center">
             <svg className="w-40 h-40 transform -rotate-90">
               <circle className="text-muted stroke-current" strokeWidth="8" cx="80" cy="80" r="70" fill="transparent"></circle>
               <motion.circle 
                 className="text-primary stroke-current" 
                 strokeLinecap="round" 
                 strokeWidth="8" 
                 strokeDasharray={440} 
                 initial={{ strokeDashoffset: 440 }}
                 animate={{ strokeDashoffset: 440 - (440 * report.overallScore) / 100 }}
                 transition={{ duration: 1.5, ease: "easeOut" }}
                 cx="80" cy="80" r="70" fill="transparent">
               </motion.circle>
             </svg>
             <span className="absolute text-5xl font-bold font-mono tracking-tighter">
               {report.overallScore}
             </span>
           </div>
        </Card>
        
        <Card className="md:col-span-2">
          <CardHeader>
             <CardTitle className="flex items-center gap-2 font-heading"><Lightbulb className="h-5 w-5 text-amber-500"/> AI Reasoning</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <p className="leading-relaxed text-foreground/90">{report.detailedAnalysis}</p>
            <div className="bg-muted px-4 py-3 rounded-lg border border-border/50 text-sm">
              <span className="font-semibold block mb-1">Recommendation</span>
              <span className="text-muted-foreground">{report.recommendations}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="competencies" className="w-full">
        <TabsList className="w-full md:w-auto grid w-full grid-cols-2 md:inline-flex md:h-10 print-hide">
          <TabsTrigger value="competencies">Competencies Detail</TabsTrigger>
          <TabsTrigger value="raw_data">Transcript Metadata</TabsTrigger>
        </TabsList>
        <TabsContent value="competencies" className="mt-6 space-y-6 block">
           <div className="grid md:grid-cols-2 gap-6 w-full">
              {/* Strengths */}
              <div className="space-y-4">
                <h3 className="font-heading text-lg font-semibold flex items-center gap-2">
                  <CheckCircle2 className="h-5 w-5 text-emerald-500" /> Key Strengths
                </h3>
                {report.strengths.map((item, i) => (
                  <Card key={i} className="shadow-none border-border/50">
                    <CardContent className="p-4 space-y-3">
                       <div className="flex justify-between items-center">
                          <span className="font-semibold text-sm">{item.area}</span>
                          <span className="font-mono text-xs text-muted-foreground">{item.score}/100</span>
                       </div>
                       <Progress value={item.score} className="h-1.5" />
                       <p className="text-sm text-muted-foreground">"{item.evidence}"</p>
                    </CardContent>
                  </Card>
                ))}
              </div>

              {/* Weaknesses */}
              <div className="space-y-4">
                <h3 className="font-heading text-lg font-semibold flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5 text-amber-500" /> Areas to Probe
                </h3>
                {report.weaknesses.map((item, i) => (
                  <Card key={i} className="shadow-none border-border/50 bg-amber-50/10 dark:bg-amber-950/5">
                    <CardContent className="p-4 space-y-3">
                       <div className="flex justify-between items-center">
                          <span className="font-semibold text-sm">{item.area}</span>
                          <span className="font-mono text-xs text-muted-foreground">{item.score}/100</span>
                       </div>
                       <Progress value={item.score} className="h-1.5 [&>div]:bg-amber-500" />
                       <p className="text-sm text-muted-foreground">"{item.evidence}"</p>
                    </CardContent>
                  </Card>
                ))}
              </div>
           </div>
           
           {/* Trend Chart */}
           <Card className="mt-8 border-border/50 shadow-none">
             <CardHeader>
               <CardTitle className="text-lg font-heading">Competency Breakdown vs. Organization Average</CardTitle>
               <CardDescription>Benchmark of candidate's detailed scores against your company's historic technical screen performance.</CardDescription>
             </CardHeader>
             <CardContent>
               <div className="h-[300px] w-full mt-4">
                 <ResponsiveContainer width="100%" height="100%">
                   <BarChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                     <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--muted-foreground)/0.2)" />
                     <XAxis dataKey="name" tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
                     <YAxis tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
                     <Tooltip 
                       contentStyle={{ borderRadius: '8px', border: '1px solid hsl(var(--border))', backgroundColor: 'hsl(var(--background))' }}
                     />
                     <Legend iconType="circle" wrapperStyle={{ fontSize: '14px', paddingTop: '10px' }} />
                     <Bar dataKey="Candidate" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} maxBarSize={40} />
                     <Bar dataKey="Org Average" fill="hsl(var(--muted))" radius={[4, 4, 0, 0]} maxBarSize={40} />
                   </BarChart>
                 </ResponsiveContainer>
               </div>
             </CardContent>
           </Card>
        </TabsContent>
        <TabsContent value="raw_data" className="mt-6">
           <Card>
             <CardContent className="p-12 text-center text-muted-foreground flex flex-col items-center justify-center">
                <Target className="h-8 w-8 mb-4 opacity-50" />
                <p>Transcript metadata is securely stored in isolation.</p>
                <p className="text-sm">Access requires audit logging authorization.</p>
             </CardContent>
           </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function ReportStatusMessage({ code }: { code: string }) {
  const normalized = code.toLowerCase();
  const isPending = normalized.includes("report_pending") || normalized.includes("report_generating");
  const isFailed = normalized.includes("report_failed");
  const isMissing = normalized.includes("report_not_found");
  const title = isPending
    ? "Report generation is still in progress"
    : isFailed
      ? "Report generation failed"
      : isMissing
        ? "Report is not available yet"
        : "Report could not be loaded";
  const body = isPending
    ? "The voice session has been captured, but the AI report worker has not finished writing the final analysis."
    : isFailed
      ? "The backend marked this report generation attempt as failed. An admin can retry generation from the admin tools."
      : isMissing
        ? "No report record exists for this session yet. This usually means the voice workflow has not reached analysis."
        : "The backend returned an unexpected report state. The session itself is still available from the candidate pipeline.";

  return (
    <div className="mx-auto flex min-h-[60vh] max-w-2xl items-center justify-center p-8">
      <Card className="w-full border-border/60 shadow-sm">
        <CardHeader className="text-center">
          <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-muted">
            {isPending ? <Clock className="h-5 w-5 text-primary" /> : <AlertTriangle className="h-5 w-5 text-amber-500" />}
          </div>
          <CardTitle className="font-heading text-2xl">{title}</CardTitle>
          <CardDescription>{body}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-center">
          <div className="rounded-xl bg-muted px-4 py-3 font-mono text-xs text-muted-foreground">{code}</div>
          <div className="flex flex-col justify-center gap-3 sm:flex-row">
            <Button variant="outline" nativeButton={false} render={<Link to="/app/candidates" />}>
              <ArrowLeft className="mr-2 h-4 w-4" /> Back to candidates
            </Button>
            <Button onClick={() => window.location.reload()}>
              <RefreshCw className="mr-2 h-4 w-4" /> Refresh status
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
