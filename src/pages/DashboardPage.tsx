import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';

export function DashboardPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-summary'],
    queryFn: () => apiFetch<any>('/api/v1/dashboard/summary'),
  });

  if (isLoading) {
    return (
      <div className="p-8">
        <div className="animate-pulse flex flex-col gap-4">
          <div className="h-8 w-64 bg-line rounded" />
          <div className="h-32 w-full bg-line rounded" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h2 className="text-section font-serif font-semibold text-ink">
          Operational Overview
        </h2>
      </div>
    </div>
  );
}

export default DashboardPage;
