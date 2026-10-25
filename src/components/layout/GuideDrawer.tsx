import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Drawer, Button } from '../ui';
import {
  Database,
  CalendarCheck,
  CheckSquare,
  BarChart2,
  FileText,
  ArrowRight,
  ShieldCheck,
  CheckCircle2,
} from 'lucide-react';

export interface GuideDrawerProps {
  open: boolean;
  onClose: () => void;
}

interface GuideStep {
  number: number;
  title: string;
  subtitle: string;
  description: string;
  href: string;
  buttonText: string;
  icon: React.ReactNode;
}

export function GuideDrawer({ open, onClose }: GuideDrawerProps) {
  const navigate = useNavigate();

  const steps: GuideStep[] = [
    {
      number: 1,
      title: 'Master Data & Network Integrity',
      subtitle: 'Upload and validate your supply chain masters',
      description:
        'Verify your 6 core entities: products, locations, warehouses, lanes, stock batches, and daily sales. Any critical validation defect triggers the Fix-First gate before planning.',
      href: '/data',
      buttonText: 'Open Data Desk',
      icon: <Database className="w-5 h-5 text-brand" strokeWidth={1.5} />,
    },
    {
      number: 2,
      title: 'Operational Attention & Stock Health',
      subtitle: 'Identify stock shortages and demand spikes',
      description:
        'The Home dashboard aggregates network-wide inventory into stock-to-demand health ratios: Healthy (>= 1.0), Low Stock (< 1.0), and Critical (< 0.5 or impending expiry).',
      href: '/',
      buttonText: 'View Dashboard',
      icon: <CheckCircle2 className="w-5 h-5 text-brand" strokeWidth={1.5} />,
    },
    {
      number: 3,
      title: 'Run Deterministic Allocation Plan',
      subtitle: 'Two-stage mixed-integer programming (MILP)',
      description:
        'Stage 1 strictly minimizes unmet net demand. Stage 2 minimizes total freight transit cost with deterministic lexicographic tie-breaking, lane gap tolerances, and FEFO expiry caps.',
      href: '/plan',
      buttonText: 'Open Plan Desk',
      icon: <CalendarCheck className="w-5 h-5 text-brand" strokeWidth={1.5} />,
    },
    {
      number: 4,
      title: 'Dispatch Review & Surplus Rescue',
      subtitle: 'Audit line allocations with human-in-the-loop authorization',
      description:
        'Inspect individual dispatch slips with counterfactual explanations. Reallocate cartons or approve shipments with role checks and an 8-second undo safeguard.',
      href: '/review',
      buttonText: 'Review Dispatches',
      icon: <CheckSquare className="w-5 h-5 text-brand" strokeWidth={1.5} />,
    },
    {
      number: 5,
      title: 'Walk-Forward Evaluation & Audit Trail',
      subtitle: 'Empirical multi-seed benchmarks against baselines',
      description:
        'Compare fill rate, cost per unit served, and expiry waste over a 28-day walk-forward replay against Min-Max and Greedy heuristics. Every action is logged in an immutable audit ledger.',
      href: '/evaluate',
      buttonText: 'View Benchmarks',
      icon: <BarChart2 className="w-5 h-5 text-brand" strokeWidth={1.5} />,
    },
  ];

  const handleStepClick = (href: string) => {
    navigate(href);
    onClose();
  };

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="Step-by-Step Operator Guide"
      subtitle="Quick operational workflow for regional FMCG distribution"
      width="w-[480px]"
    >
      <div className="flex flex-col gap-5 py-2">
        <div className="bg-brand-wash p-4 rounded-control border border-brand/20 flex items-start gap-3">
          <ShieldCheck className="w-5 h-5 text-brand shrink-0 mt-0.5" strokeWidth={1.5} />
          <div>
            <h4 className="text-body font-semibold text-brand">Deterministic & Honest</h4>
            <p className="text-meta text-ink-2 mt-0.5">
              VyaparMitra computes every allocation algorithmically without black-box language models in the optimization loop.
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-4">
          {steps.map((step) => (
            <div
              key={step.number}
              className="p-4 bg-surface rounded-control border border-line hover:border-brand/40 transition-colors flex flex-col gap-2.5 shadow-sm"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-7 h-7 rounded-full bg-brand-wash text-brand font-semibold text-meta flex items-center justify-center">
                    {step.number}
                  </div>
                  <h3 className="font-serif font-semibold text-body text-ink">{step.title}</h3>
                </div>
                {step.icon}
              </div>
              <p className="text-meta text-ink-3 font-medium">{step.subtitle}</p>
              <p className="text-meta text-ink-2 leading-relaxed">{step.description}</p>
              <div className="pt-1">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => handleStepClick(step.href)}
                  className="inline-flex items-center gap-1.5"
                >
                  <span>{step.buttonText}</span>
                  <ArrowRight className="w-3.5 h-3.5" strokeWidth={1.5} />
                </Button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </Drawer>
  );
}
