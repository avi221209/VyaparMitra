import React, { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider, Button, Skeleton, ErrorBoundary } from './components/ui';
import { AppShell } from './components/layout/AppShell';

// Route-level code splitting for fast initial load
const DataPage = lazy(() => import('./pages/DataPage').then((m) => ({ default: m.DataPage })));
const PlanPage = lazy(() => import('./pages/PlanPage').then((m) => ({ default: m.PlanPage })));
const ReviewPage = lazy(() => import('./pages/ReviewPage').then((m) => ({ default: m.ReviewPage })));
const EvaluatePage = lazy(() => import('./pages/EvaluatePage').then((m) => ({ default: m.EvaluatePage })));
const AuditPage = lazy(() => import('./pages/AuditPage').then((m) => ({ default: m.AuditPage })));
const DashboardPage = lazy(() => import('./pages/DashboardPage').then((m) => ({ default: m.DashboardPage })));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10000,
      refetchOnWindowFocus: false,
    },
  },
});

function RouteLoadingFallback() {
  return (
    <div className="flex flex-col gap-4 p-4 max-w-4xl animate-pulse">
      <Skeleton className="h-10 w-48" />
      <Skeleton className="h-28 w-full" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

function PageWrapper({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  React.useEffect(() => {
    document.title = `${title} — VyaparMitra`;
  }, [title]);

  return (
    <AppShell pageTitle={title}>
      <ErrorBoundary>
        <Suspense fallback={<RouteLoadingFallback />}>
          {children}
        </Suspense>
      </ErrorBoundary>
    </AppShell>
  );
}


function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] text-center p-8">
      <h2 className="text-display font-serif font-bold text-ink mb-2">404</h2>
      <h3 className="text-section font-serif text-ink-2 mb-4">Page not found</h3>
      <p className="text-body text-ink-3 max-w-sm mb-6">
        The requested screen does not exist. Return to the planning ledger.
      </p>
      <Button variant="primary" onClick={() => (window.location.href = '/')}>
        Go to Home
      </Button>
    </div>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            <Route
              path="/"
              element={
                <PageWrapper title="Home">
                  <DashboardPage />
                </PageWrapper>
              }
            />
            <Route
              path="/data"
              element={
                <PageWrapper title="Data and Network Validation">
                  <DataPage />
                </PageWrapper>
              }
            />
            <Route
              path="/plan"
              element={
                <PageWrapper title="Distribution Plan">
                  <PlanPage />
                </PageWrapper>
              }
            />
            <Route
              path="/review"
              element={
                <PageWrapper title="Plan Review and Approval">
                  <ReviewPage />
                </PageWrapper>
              }
            />
            <Route
              path="/evaluate"
              element={
                <PageWrapper title="Walk-Forward Evaluation">
                  <EvaluatePage />
                </PageWrapper>
              }
            />
            <Route
              path="/audit"
              element={
                <PageWrapper title="Decision Log and Audit Trail">
                  <AuditPage />
                </PageWrapper>
              }
            />
            <Route
              path="*"
              element={
                <PageWrapper title="Page Not Found">
                  <NotFoundPage />
                </PageWrapper>
              }
            />
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}
export default App;
