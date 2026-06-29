export interface Candidate {
  id: string;
  name: string;
  email: string;
  role: string;
  status: 'scheduled' | 'invited' | 'in_progress' | 'completed' | 'failed';
  score?: number;
  date: string;
  avatarUrl?: string;
  callId?: string;
  durationSeconds?: number;
}

export interface AssessmentReport {
  id: string;
  candidateId: string;
  overallScore: number;
  passFail: 'pass' | 'fail' | 'inconclusive';
  strengths: Finding[];
  weaknesses: Finding[];
  detailedAnalysis: string;
  recommendations: string;
  date: string;
  modelUsed?: string;
}

export interface Finding {
  area: string;
  evidence: string;
  score: number;
}

export interface Analytics {
  totalAssessments: number;
  passRate: number;
  averageScore: number;
  assessmentsByRole: { name: string; value: number }[];
  scoreDistribution: { bucket: string; count: number }[];
  trends: { date: string; volume: number; avgScore: number }[];
  competencyAverages?: { area: string; avgScore: number }[];
}
