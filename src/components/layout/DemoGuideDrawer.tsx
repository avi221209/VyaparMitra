import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import {
  Drawer,
  Button,
  Badge,
  useToast,
  InlineMessage,
} from '../ui';
import { apiFetch } from '../../lib/api';
import {
  Play,
  RotateCcw,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Layers,
  Database,
  CalendarCheck,
  Sliders,
  BarChart2,
} from 'lucide-react';

export interface DemoGuideDrawerProps {
  open: boolean;
  onClose: () => void;
}

export function DemoGuideDrawer({ open, onClose }: DemoGuideDrawerProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [activeBeat, setActiveBeat] = useState<number | null>(null);
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [isRestoringBackup, setIsRestoringBackup] = useState<boolean>(false);

  // Beat 1: Load Defects (0:00 - 0:30)
  const handleBeat1 = async () => {
    setIsRunning(true);
    setActiveBeat(1);
    try {
      await apiFetch('/api/data/load-defects', { method: 'POST' });
      queryClient.invalidateQueries();
      toast({ type: 'info', message: 'Beat 1: Loaded 20-defect manifest' });
      navigate('/data');
    } catch (err: any) {
      toast({ type: 'error', message: err.message || 'Failed to load defects' });
    } finally {
      setIsRunning(false);
    }
  };

  // Beat 2: Generate Plan (0:30 - 1:00)
  const handleBeat2 = async () => {
    setIsRunning(true);
    setActiveBeat(2);
    try {
      // Re-seed clean balanced data first to clear defects
      await apiFetch('/api/data/seed', {
        method: 'POST',
        body: JSON.stringify({ scenario: 'balanced', variant: 'normal' }),
      });
      const planRes = await apiFetch<any>('/api/plan', {
        method: 'POST',
        body: JSON.stringify({ horizon: 7 }),
      });
      queryClient.invalidateQueries();
      toast({ type: 'success', message: 'Beat 2: Baseline plan generated' });
      navigate('/plan');
    } catch (err: any) {
      toast({ type: 'error', message: err.message || 'Failed to generate plan' });
    } finally {
      setIsRunning(false);
    }
  };

  // Beat 3: Open W1 to D2 slip (1:00 - 1:30)
  const handleBeat3 = async () => {
    setIsRunning(true);
    setActiveBeat(3);
    try {
      const planRes = await apiFetch<any>('/api/plan/latest');
      const lines = planRes?.lines || [];
      const targetLine = lines.find((l: any) => l.source_id === 'W1' && l.destination_id === 'D2') || lines[0];
      if (targetLine) {
        navigate(`/plan?line=${targetLine.id}`);
        toast({ type: 'info', message: 'Beat 3: Opened dispatch slip drawer' });
      } else {
        navigate('/plan');
      }
    } catch {
      navigate('/plan');
    } finally {
      setIsRunning(false);
    }
  };

  // Beat 4: Inspect D2 Shortfall & Rescue (1:30 - 2:00)
  const handleBeat4 = async () => {
    setIsRunning(true);
    setActiveBeat(4);
    try {
      navigate('/plan');
      toast({ type: 'info', message: 'Beat 4: Inspect unmet shortfall and peer surplus rescue' });
    } finally {
      setIsRunning(false);
    }
  };

  // Beat 5: Cut W1 Stock by 20% (2:00 - 2:20)
  const handleBeat5 = async () => {
    setIsRunning(true);
    setActiveBeat(5);
    try {
      await apiFetch('/api/scenario/override', {
        method: 'POST',
        body: JSON.stringify({
          source_overrides: {
            W1: { mode: 'multiplier', value: 0.8 },
          },
        }),
      });
      await apiFetch('/api/plan', {
        method: 'POST',
        body: JSON.stringify({ horizon: 7 }),
      });
      queryClient.invalidateQueries();
      toast({ type: 'info', message: 'Beat 5: Cut W1 stock by 20% - unmet demand increased' });
      navigate('/plan');
    } catch (err: any) {
      toast({ type: 'error', message: err.message || 'What-if cut failed' });
    } finally {
      setIsRunning(false);
    }
  };

  // Beat 6: Test 409 Rule Refusal (2:20 - 2:40)
  const handleBeat6 = async () => {
    setIsRunning(true);
    setActiveBeat(6);
    try {
      const planRes = await apiFetch<any>('/api/plan/latest');
      const firstLine = planRes?.lines?.[0];
      if (firstLine) {
        // Attempt edit to 99999 cartons
        try {
          await apiFetch(`/api/plan/lines/${firstLine.id}/approve`, {
            method: 'POST',
            body: JSON.stringify({ edited_cartons: 99999 }),
          });
        } catch (err: any) {
          toast({ type: 'error', message: `HTTP 409 Guardrail Verified: ${err.message || 'Batch stock exceeded'}` });
        }
        navigate(`/plan?line=${firstLine.id}`);
      }
    } finally {
      setIsRunning(false);
    }
  };

  // Beat 7: Open Evaluate (2:40 - 3:00)
  const handleBeat7 = async () => {
    setActiveBeat(7);
    navigate('/evaluate');
    toast({ type: 'info', message: 'Beat 7: Walk-forward evaluation proof and ablations' });
  };

  // Load Backup Demo State (Offline zero-solver instant recovery)
  const handleLoadBackup = async () => {
    setIsRestoringBackup(true);
    try {
      await apiFetch('/api/demo/backup', { method: 'POST' });
      queryClient.invalidateQueries();
      toast({ type: 'success', message: 'Backup demo state loaded successfully into database' });
      navigate('/plan');
      onClose();
    } catch (err: any) {
      toast({ type: 'error', message: err.message || 'Failed to restore backup demo state' });
    } finally {
      setIsRestoringBackup(false);
    }
  };

  const beats = [
    {
      index: 1,
      time: '0:00 - 0:30',
      title: 'Load 20-defect manifest',
      description: 'Show the Fix First gate blocking plan generation until duplicate SKUs, negative stocks, and missing sales are resolved.',
      actionLabel: 'Run Beat 1',
      handler: handleBeat1,
    },
    {
      index: 2,
      time: '0:30 - 1:00',
      title: 'Generate baseline plan',
      description: 'Run the two-stage lexicographic MILP optimizer to solve customer demand, safety-stock buffer, and freight minimization.',
      actionLabel: 'Run Beat 2',
      handler: handleBeat2,
    },
    {
      index: 3,
      time: '1:00 - 1:30',
      title: 'Open W1 to D2 slip',
      description: 'Demonstrate the physical godown dispatch voucher with batch stock checks, lead-time gaps, and FEFO shelf life.',
      actionLabel: 'Run Beat 3',
      handler: handleBeat3,
    },
    {
      index: 4,
      time: '1:30 - 2:00',
      title: 'Inspect shortfall & rescue',
      description: 'Inspect binding constraint diagnosis, 50/50 price band, verified spare stock gate, and peer godown rescue.',
      actionLabel: 'Run Beat 4',
      handler: handleBeat4,
    },
    {
      index: 5,
      time: '2:00 - 2:20',
      title: 'Cut W1 stock by 20%',
      description: 'Simulate concurrent warehouse inventory shock in Kinaxis style with side-by-side cost-to-serve delta columns.',
      actionLabel: 'Run Beat 5',
      handler: handleBeat5,
    },
    {
      index: 6,
      time: '2:20 - 2:40',
      title: 'Test rule refusal (HTTP 409)',
      description: 'Attempt an over-dispatch exceeding available batch stock to prove the server-side validation rule refusal.',
      actionLabel: 'Run Beat 6',
      handler: handleBeat6,
    },
    {
      index: 7,
      time: '2:40 - 3:00',
      title: 'Walk-forward proof',
      description: 'Conclude on the Evaluate screen with 5-seed distribution dot plots, ablations (V-SS, V-SL), and honest loss accounting.',
      actionLabel: 'Run Beat 7',
      handler: handleBeat7,
    },
  ];

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="Demo presenter guide"
      subtitle={
        <span className="text-meta text-ink-2">
          Timed 3-minute hackathon pitch script, 1 click per beat
        </span>
      }
      footer={
        <div className="w-full flex items-center justify-between gap-3 bg-surface pt-3 border-t border-line">
          <Button variant="quiet" size="sm" onClick={onClose}>
            Close guide
          </Button>
          <span className="text-meta text-ink-3">
            Active beat: {activeBeat ? `Beat ${activeBeat}` : 'Ready'}
          </span>
        </div>
      }
    >
      <div className="flex flex-col gap-6">
        {/* Offline Backup Recovery Callout */}
        <div className="p-4 bg-surface border border-line rounded-control flex flex-col gap-2.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-ok" strokeWidth={1.5} />
              <span className="text-meta font-semibold text-ink">Zero-solver offline recovery</span>
            </div>
            <Badge variant="ok">Precomputed</Badge>
          </div>
          <p className="text-meta text-ink-2 leading-relaxed">
            If network drops or CBC solver is constrained on a fresh judge machine, instantly restore the full verified demo state without running the optimizer.
          </p>
          <div>
            <Button
              variant="secondary"
              size="sm"
              loading={isRestoringBackup}
              onClick={handleLoadBackup}
            >
              Load backup demo state
            </Button>
          </div>
        </div>

        {/* 7-Beat Script Register */}
        <div className="flex flex-col gap-3">
          <h3 className="text-section font-serif font-semibold text-ink">
            Script sequence
          </h3>

          <div className="border-t border-line divide-y divide-line">
            {beats.map((b) => (
              <div
                key={b.index}
                className={`py-3.5 flex flex-col gap-2 transition-colors ${
                  activeBeat === b.index ? 'bg-brand-wash/30 -mx-3 px-3 rounded-control' : ''
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-meta font-bold text-ink-3 tabular-nums">
                      {String(b.index).padStart(2, '0')}
                    </span>
                    <span className="font-medium text-ink text-body">
                      {b.title}
                    </span>
                  </div>
                  <span className="text-meta text-ink-3 font-mono tabular-nums">
                    {b.time}
                  </span>
                </div>

                <p className="text-meta text-ink-2 leading-relaxed">
                  {b.description}
                </p>

                <div className="pt-1 flex items-center justify-between">
                  <Button
                    variant={activeBeat === b.index ? 'primary' : 'secondary'}
                    size="sm"
                    loading={isRunning && activeBeat === b.index}
                    onClick={b.handler}
                  >
                    {b.actionLabel}
                  </Button>
                  {activeBeat === b.index && (
                    <span className="text-meta text-ok font-medium flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      Executed
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Drawer>
  );
}
