/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */
import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppLayout } from "./components/layout/AppLayout";
import { TooltipProvider } from "./components/ui/tooltip";
import { Navigate, Outlet } from "react-router-dom";
import { authStore } from "./services/api";

const Landing = lazy(() => import("./pages/Landing"));
const Auth = lazy(() => import("./pages/Auth"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Assessments = lazy(() => import("./pages/Assessments"));
const Candidates = lazy(() => import("./pages/Candidates"));
const ReportViewer = lazy(() => import("./pages/Report"));
const AssessmentExperience = lazy(() => import("./pages/Assessment"));
const Admin = lazy(() => import("./pages/Admin"));
const Settings = lazy(() => import("./pages/Settings"));

function ProtectedRoute() {
  return authStore.getToken() ? <Outlet /> : <Navigate replace to="/auth" />;
}

function RouteLoader() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background text-sm font-medium text-muted-foreground">
      <div className="flex items-center gap-3 rounded-full border bg-card px-4 py-2 shadow-sm">
        <span className="h-2 w-2 animate-pulse rounded-full bg-primary" />
        Loading workspace
      </div>
    </div>
  );
}

export default function App() {
  return (
    <TooltipProvider>
      <BrowserRouter>
        <Suspense fallback={<RouteLoader />}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/auth" element={<Auth />} />
            <Route path="/demo" element={<AssessmentExperience />} />
            <Route path="/demo/:sessionId" element={<AssessmentExperience />} />

            <Route element={<ProtectedRoute />}>
              <Route path="/app" element={<AppLayout />}>
                <Route index element={<Dashboard />} />
                <Route path="assessments" element={<Assessments />} />
                <Route path="candidates" element={<Candidates />} />
                <Route path="reports" element={<Candidates />} />
                <Route path="reports/:id" element={<ReportViewer />} />
                <Route path="admin" element={<Admin />} />
                <Route path="settings" element={<Settings />} />
              </Route>
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </TooltipProvider>
  );
}
