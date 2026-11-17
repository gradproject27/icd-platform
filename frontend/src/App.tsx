import { Navigate, Route, Routes } from "react-router";
import { Layout } from "./components/Layout";
import { AiReportPage } from "./pages/AiReportPage";
import { AuditTrailPage } from "./pages/AuditTrailPage";
import { ConfigurationPage } from "./pages/ConfigurationPage";
import { ExplanationPage } from "./pages/ExplanationPage";
import { IncidentDetailPage } from "./pages/IncidentDetailPage";
import { IncidentListPage } from "./pages/IncidentListPage";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { PendingDecisionPage } from "./pages/PendingDecisionPage";
import { ReviewQueuePage } from "./pages/ReviewQueuePage";
import { UploadPage } from "./pages/UploadPage";

// No auth guard yet: the session check is added with login in T2-15 (C5). Every page except
// /login will then require a session (C-01).
export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/incidents" replace />} />
        <Route path="upload" element={<UploadPage />} />
        <Route path="incidents" element={<IncidentListPage />} />
        <Route path="review" element={<ReviewQueuePage />} />
        <Route path="configuration" element={<ConfigurationPage />} />
        <Route path="incidents/:incidentId" element={<IncidentDetailPage />} />
        <Route path="incidents/:incidentId/report" element={<AiReportPage />} />
        <Route path="incidents/:incidentId/decision" element={<PendingDecisionPage />} />
        <Route path="incidents/:incidentId/audit" element={<AuditTrailPage />} />
        <Route path="incidents/:incidentId/explanation" element={<ExplanationPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
