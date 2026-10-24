import React, { useState, useMemo, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  DataTable,
  Badge,
  EmptyState,
  Select,
  Input,
  formatCartons,
} from '../components/ui';
import { apiFetch } from '../lib/api';
import { FileText, Filter, Search } from 'lucide-react';

export interface DecisionLogEntry {
  id: number;
  plan_line_id?: string;
  actor_role: string;
  action: string;
  old_value?: string;
  new_value?: string;
  note?: string;
  timestamp: string;
}

export function AuditPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const urlRole = searchParams.get('role') || 'all';
  const urlAction = searchParams.get('action') || 'all';
  const urlQ = searchParams.get('q') || '';

  const [roleFilter, setRoleFilter] = useState<string>(urlRole);
  const [actionFilter, setActionFilter] = useState<string>(urlAction);
  const [searchQuery, setSearchQuery] = useState<string>(urlQ);

  // Sync to URL
  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    if (roleFilter !== 'all') next.set('role', roleFilter);
    else next.delete('role');

    if (actionFilter !== 'all') next.set('action', actionFilter);
    else next.delete('action');

    if (searchQuery) next.set('q', searchQuery);
    else next.delete('q');

    setSearchParams(next, { replace: true });
  }, [roleFilter, actionFilter, searchQuery]);

  const { data: logs = [], isLoading } = useQuery<DecisionLogEntry[]>({
    queryKey: ['audit-logs'],
    queryFn: async () => {
      try {
        const res = await apiFetch<any>('/api/audit');
        return Array.isArray(res) ? res : res.logs || [];
      } catch {
        const fallback = await apiFetch<DecisionLogEntry[]>('/api/decision-logs');
        return fallback || [];
      }
    },
    refetchInterval: 5000,
  });

  const formatDateTimeIN = (isoStr: string) => {
    if (!isoStr) return '—';
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    return d.toLocaleString('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  };

  const describeChange = (entry: DecisionLogEntry) => {
    const { action, old_value, new_value, note } = entry;
    if (action === 'EDIT' || action === 'EDIT_REFUSED') {
      if (old_value && new_value) {
        return `from ${old_value} to ${new_value} cartons`;
      }
    }
    if (action === 'APPROVE') {
      return old_value ? `approved with ${old_value} cartons` : 'allocation approved';
    }
    if (action === 'REJECT') {
      return note ? `rejected with reason: ${note}` : 'allocation rejected';
    }
    if (action === 'OPTIMIZE') {
      return 'two-stage deterministic optimization run executed';
    }
    if (action === 'OVERRIDE') {
      return note || 'what-if parameter override applied';
    }
    return note || (new_value ? `set to ${new_value}` : 'action recorded');
  };

  const filteredLogs = useMemo(() => {
    return logs.filter((log) => {
      const matchRole = roleFilter === 'all' || log.actor_role.toLowerCase() === roleFilter.toLowerCase();
      const matchAction = actionFilter === 'all' || log.action.toUpperCase() === actionFilter.toUpperCase();
      const matchSearch =
        !searchQuery ||
        (log.plan_line_id && log.plan_line_id.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (log.note && log.note.toLowerCase().includes(searchQuery.toLowerCase())) ||
        log.action.toLowerCase().includes(searchQuery.toLowerCase());
      return matchRole && matchAction && matchSearch;
    });
  }, [logs, roleFilter, actionFilter, searchQuery]);

  const columns = [
    {
      key: 'timestamp',
      header: 'Timestamp',
      width: '180px',
      render: (r: DecisionLogEntry) => (
        <span className="tabular-nums text-ink text-meta">
          {formatDateTimeIN(r.timestamp)}
        </span>
      ),
    },
    {
      key: 'actor_role',
      header: 'Role',
      width: '130px',
      render: (r: DecisionLogEntry) => {
        const role = r.actor_role?.toLowerCase();
        const variant =
          role === 'reviewer'
            ? 'brand'
            : role === 'planner'
            ? 'turmeric'
            : role === 'warehouse'
            ? 'neutral'
            : 'neutral';
        return <Badge variant={variant}>{r.actor_role}</Badge>;
      },
    },
    {
      key: 'action',
      header: 'Action',
      width: '140px',
      render: (r: DecisionLogEntry) => (
        <span className="font-semibold text-ink text-meta">{r.action}</span>
      ),
    },
    {
      key: 'changes',
      header: 'Changes',
      render: (r: DecisionLogEntry) => (
        <span className="text-body text-ink-2 font-normal">
          {describeChange(r)}
        </span>
      ),
    },
    {
      key: 'plan_line_id',
      header: 'Entity / Line',
      width: '140px',
      render: (r: DecisionLogEntry) => (
        <span className="text-meta text-ink-3 tabular-nums">
          {r.plan_line_id ? r.plan_line_id.substring(0, 10) : '—'}
        </span>
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      {/* Intro Header */}
      <section className="flex flex-col gap-1 pb-4 border-b border-line">
        <h2 className="text-section font-serif font-semibold text-ink">
          Decision Log and Audit Trail
        </h2>
        <p className="text-body text-ink-2">
          Immutable log of every optimization run, approval, edit refusal, rejection, and manual scenario adjustment.
        </p>
      </section>

      {/* Filters Bar */}
      <section className="flex flex-wrap items-center justify-between gap-4 py-3 px-4 bg-surface border-y border-line text-body">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5 text-meta text-ink-2">
            <Filter className="w-4 h-4 text-ink-3" strokeWidth={1.5} />
            <span>Filter by:</span>
          </div>

          <Select
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            className="h-8 text-meta"
          >
            <option value="all">All roles</option>
            <option value="planner">Planner</option>
            <option value="reviewer">Reviewer</option>
            <option value="warehouse">Warehouse</option>
            <option value="system">System</option>
          </Select>

          <Select
            value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}
            className="h-8 text-meta"
          >
            <option value="all">All actions</option>
            <option value="OPTIMIZE">Optimize</option>
            <option value="APPROVE">Approve</option>
            <option value="EDIT">Edit</option>
            <option value="EDIT_REFUSED">Edit refused</option>
            <option value="REJECT">Reject</option>
            <option value="OVERRIDE">Override</option>
          </Select>
        </div>

        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-4 h-4 text-ink-3 absolute left-2.5 top-2.5" strokeWidth={1.5} />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search action or note..."
              className="pl-8 h-8 text-meta w-48 sm:w-64"
            />
          </div>
        </div>
      </section>

      {/* Table */}
      <section className="flex flex-col gap-4">
        {logs.length === 0 ? (
          <EmptyState
            title="No audit entries"
            description="Actions taken during planning and reviews will be permanently logged here."
          />
        ) : (
          <DataTable
            columns={columns}
            data={filteredLogs}
            keyExtractor={(l) => String(l.id)}
            loading={isLoading}
            emptyMessage="No audit logs match selected filters."
          />
        )}
      </section>
    </div>
  );
}
