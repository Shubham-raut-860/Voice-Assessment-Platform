import { Analytics, AssessmentReport, Candidate } from "../types";

export type UserRole = "admin" | "assessor" | "candidate";
export type SessionStatus = "scheduled" | "in_progress" | "completed" | "failed" | "abandoned";
export type ReportStatus = "pending" | "generating" | "completed" | "failed";
export type AssessmentStatus = "draft" | "active" | "completed" | "archived";

export type AuthUser = {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  updated_at: string;
};

type TokenResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
};

export type AssessmentResponse = {
  id: string;
  title: string;
  description: string;
  status: AssessmentStatus;
  vapi_assistant_id: string;
  passing_score: string;
  time_limit_minutes: number;
  created_by_id: string;
  created_at: string;
  updated_at: string;
};

export type AssessmentListResponse = {
  items: AssessmentResponse[];
  total: number;
  page: number;
  page_size: number;
};

export type SessionResponse = {
  id: string;
  assessment_id: string;
  candidate_id: string;
  assessor_id: string | null;
  vapi_call_id: string | null;
  status: SessionStatus;
  scheduled_at: string | null;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
  raw_transcript: string | null;
  created_at: string;
  updated_at: string;
  assessment: AssessmentResponse;
  candidate: AuthUser;
  assessor: AuthUser | null;
};

export type SessionListResponse = {
  items: SessionResponse[];
  total: number;
  page: number;
  page_size: number;
};

export type PlatformStats = {
  total_users: number;
  total_assessments: number;
  total_sessions: number;
  sessions_by_status: Partial<Record<SessionStatus, number>>;
  pass_rate: number;
  avg_score: number;
  reports_generated_today: number;
  emails_sent_today: number;
};

export type ReportResponse = {
  id: string;
  session_id: string;
  overall_score: string | null;
  pass_fail: "pass" | "fail" | "inconclusive";
  strengths: Array<{ area: string; evidence: string; score: number }>;
  weaknesses: Array<{ area: string; evidence: string; score: number }>;
  detailed_analysis: string;
  recommendations: string;
  anthropic_model_used?: string;
  generated_at: string | null;
  created_at: string;
};

type UserListResponse = {
  items: AuthUser[];
  total: number;
  page: number;
  page_size: number;
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8787";
const TOKEN_KEY = "voice_assessment_token";
const USER_KEY = "voice_assessment_user";

export const authStore = {
  getToken: (): string | null => window.localStorage.getItem(TOKEN_KEY),
  getUser: (): AuthUser | null => {
    const raw = window.localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as AuthUser;
    } catch {
      window.localStorage.removeItem(USER_KEY);
      return null;
    }
  },
  setSession: (token: string, user: AuthUser): void => {
    window.localStorage.setItem(TOKEN_KEY, token);
    window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  clear: (): void => {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(USER_KEY);
  },
};

export const authService = {
  login: async (email: string, password: string): Promise<AuthUser> => {
    const token = await request<TokenResponse>("/api/v1/auth/login", {
      method: "POST",
      body: { email, password },
    });
    const user = await request<AuthUser>("/api/v1/auth/me", { token: token.access_token });
    authStore.setSession(token.access_token, user);
    return user;
  },
  register: async (
    email: string,
    password: string,
    fullName: string,
    role: UserRole = "candidate",
    inviteCode?: string,
  ): Promise<AuthUser> => {
    await request<AuthUser>("/api/v1/auth/register", {
      method: "POST",
      body: { email, password, full_name: fullName, role, invite_code: inviteCode || undefined },
    });
    return authService.login(email, password);
  },
  me: async (): Promise<AuthUser> => requestWithAuth<AuthUser>("/api/v1/auth/me"),
  logout: async (): Promise<void> => {
    const token = authStore.getToken();
    if (token) {
      await request("/api/v1/auth/logout", { method: "POST", token }).catch(() => undefined);
    }
    authStore.clear();
  },
};

export const assessmentsService = {
  list: async (page = 1, pageSize = 50, status?: AssessmentStatus): Promise<AssessmentListResponse> => {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (status) query.set("status", status);
    return requestWithAuth<AssessmentListResponse>(`/api/v1/assessments?${query.toString()}`);
  },
  create: async (data: {
    title: string;
    description: string;
    status: AssessmentStatus;
    vapi_assistant_id: string;
    passing_score: string;
    time_limit_minutes: number;
  }): Promise<AssessmentResponse> =>
    requestWithAuth<AssessmentResponse>("/api/v1/assessments", {
      method: "POST",
      body: data,
    }),
  update: async (id: string, data: Partial<AssessmentResponse>): Promise<AssessmentResponse> =>
    requestWithAuth<AssessmentResponse>(`/api/v1/assessments/${id}`, {
      method: "PATCH",
      body: data,
    }),
  archive: async (id: string): Promise<void> =>
    requestWithAuth<void>(`/api/v1/assessments/${id}`, {
      method: "DELETE",
    }),
};

export const sessionsService = {
  list: async (page = 1, pageSize = 50, status?: SessionStatus): Promise<SessionListResponse> => {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (status) query.set("status", status);
    return requestWithAuth<SessionListResponse>(`/api/v1/sessions?${query.toString()}`);
  },
  get: async (id: string): Promise<SessionResponse> => requestWithAuth<SessionResponse>(`/api/v1/sessions/${id}`),
  create: async (data: {
    assessment_id: string;
    candidate_id: string;
    assessor_id?: string | null;
    scheduled_at?: string | null;
  }): Promise<SessionResponse> =>
    requestWithAuth<SessionResponse>("/api/v1/sessions", {
      method: "POST",
      body: data,
    }),
  startCall: async (sessionId: string, customerNumber?: string | null): Promise<{ call_id: string; web_call_url: string | null }> =>
    requestWithAuth<{ call_id: string; web_call_url: string | null }>(`/api/v1/sessions/${sessionId}/start-call`, {
      method: "POST",
      body: customerNumber ? { customer_number: customerNumber } : {},
    }),
  bindWebCall: async (sessionId: string, callId: string): Promise<SessionResponse> =>
    requestWithAuth<SessionResponse>(`/api/v1/sessions/${sessionId}/bind-web-call`, {
      method: "POST",
      body: { call_id: callId },
    }),
};

export const candidatesService = {
  getRecent: async (): Promise<Candidate[]> => {
    const sessions = await sessionsService.list(1, 50);
    return sessions.items.map(sessionToCandidate);
  },
};

export const reportsService = {
  getReport: async (sessionId: string): Promise<AssessmentReport> => {
    const report = await requestWithAuth<ReportResponse | { status: ReportStatus }>(
      `/api/v1/sessions/${sessionId}/report`,
    );
    if (!("overall_score" in report)) {
      throw new Error(`report_${report.status}`);
    }
    return {
      id: report.id,
      candidateId: report.session_id,
      overallScore: Number(report.overall_score ?? 0),
      passFail: report.pass_fail,
      strengths: report.strengths,
      weaknesses: report.weaknesses,
      detailedAnalysis: report.detailed_analysis,
      recommendations: report.recommendations,
      date: dateOnly(report.generated_at ?? report.created_at),
      modelUsed: report.anthropic_model_used,
    };
  },
};

export const analyticsService = {
  getStats: async (): Promise<Analytics> => {
    try {
      const stats = await requestWithAuth<PlatformStats>("/api/v1/admin/stats");
      return {
        totalAssessments: stats.total_assessments,
        passRate: Math.round(stats.pass_rate * 1000) / 10,
        averageScore: stats.avg_score,
        assessmentsByRole: Object.entries(stats.sessions_by_status).map(([name, value]) => ({
          name,
          value: value ?? 0,
        })),
        scoreDistribution: [
          { bucket: "0-50", count: 0 },
          { bucket: "50-60", count: 0 },
          { bucket: "60-70", count: 0 },
          { bucket: "70-80", count: 0 },
          { bucket: "80-90", count: 0 },
          { bucket: "90-100", count: 0 },
        ],
        trends: [],
        competencyAverages: [],
      };
    } catch {
      const sessions = await sessionsService.list(1, 100);
      const completed = sessions.items.filter((session) => session.status === "completed").length;
      return {
        totalAssessments: sessions.total,
        passRate: sessions.total ? Math.round((completed / sessions.total) * 1000) / 10 : 0,
        averageScore: 0,
        assessmentsByRole: groupSessionsByAssessment(sessions.items),
        scoreDistribution: [],
        trends: [],
        competencyAverages: [],
      };
    }
  },
};

export const adminService = {
  createUser: async (data: {
    email: string;
    password: string;
    full_name: string;
    role: UserRole;
  }): Promise<AuthUser> =>
    requestWithAuth<AuthUser>("/api/v1/admin/users", {
      method: "POST",
      body: data,
    }),
  listUsers: async (page = 1, pageSize = 50, role?: UserRole): Promise<UserListResponse> => {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (role) query.set("role", role);
    return requestWithAuth<UserListResponse>(`/api/v1/admin/users?${query.toString()}`);
  },
  lookupUserByEmail: async (email: string): Promise<AuthUser> => {
    const query = new URLSearchParams({ email });
    return requestWithAuth<AuthUser>(`/api/v1/admin/users/lookup?${query.toString()}`);
  },
  updateUser: async (id: string, data: { role?: UserRole; is_active?: boolean }): Promise<AuthUser> =>
    requestWithAuth<AuthUser>(`/api/v1/admin/users/${id}`, {
      method: "PATCH",
      body: data,
    }),
  listFailedSessions: async (page = 1, pageSize = 20): Promise<SessionListResponse> =>
    requestWithAuth<SessionListResponse>(`/api/v1/admin/sessions/failed?page=${page}&page_size=${pageSize}`),
  retryReport: async (sessionId: string): Promise<void> =>
    requestWithAuth<void>(`/api/v1/admin/sessions/${sessionId}/retry-report`, {
      method: "POST",
    }),
};

export function getApiBaseUrl(): string {
  return API_BASE_URL;
}

async function requestWithAuth<T>(
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<T> {
  const token = authStore.getToken();
  if (!token) throw new Error("not_authenticated");
  return request<T>(path, { ...options, token });
}

async function request<T = unknown>(
  path: string,
  options: { method?: string; body?: unknown; token?: string } = {},
): Promise<T> {
  const headers = new Headers();
  if (options.body !== undefined) headers.set("Content-Type", "application/json");
  if (options.token) headers.set("Authorization", `Bearer ${options.token}`);

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  if (!response.ok) {
    throw new Error(await readError(response));
  }

  if (response.status === 204 || response.status === 202) return undefined as T;
  return (await response.json()) as T;
}

async function readError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
  } catch {
    return `${response.status} ${response.statusText}`;
  }
}

function sessionToCandidate(session: SessionResponse): Candidate {
  return {
    id: session.id,
    name: session.candidate.full_name,
    email: session.candidate.email,
    role: session.assessment.title,
    status: mapStatus(session.status),
    score: undefined,
    date: dateOnly(session.created_at),
    avatarUrl: undefined,
    callId: session.vapi_call_id ?? undefined,
    durationSeconds: session.duration_seconds ?? undefined,
  };
}

function mapStatus(status: SessionStatus): Candidate["status"] {
  if (status === "scheduled") return "scheduled";
  if (status === "abandoned") return "failed";
  return status;
}

function dateOnly(value: string): string {
  return value.slice(0, 10);
}

function groupSessionsByAssessment(sessions: SessionResponse[]): { name: string; value: number }[] {
  const counts = new Map<string, number>();
  sessions.forEach((session) => {
    counts.set(session.assessment.title, (counts.get(session.assessment.title) ?? 0) + 1);
  });
  return Array.from(counts, ([name, value]) => ({ name, value }));
}
