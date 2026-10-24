import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Drawer, Button, Field, Input, InlineMessage, useToast } from '../ui';
import { apiFetch } from '../../lib/api';
import { RotateCcw } from 'lucide-react';

export interface SettingsDrawerProps {
  open: boolean;
  onClose: () => void;
}

export function SettingsDrawer({ open, onClose }: SettingsDrawerProps) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const { data: currentSettings, isLoading } = useQuery({
    queryKey: ['system-settings'],
    queryFn: () => apiFetch<any>('/api/settings'),
    enabled: open,
  });

  const [formState, setFormState] = useState<any>({});

  React.useEffect(() => {
    if (currentSettings) {
      setFormState({
        H: currentSettings.H,
        z: currentSettings.z,
        Gmax: currentSettings.Gmax,
        planner_reserve: currentSettings.planner_reserve,
        min_remaining_shelf_days: currentSettings.min_remaining_shelf_days,
      });
    }
  }, [currentSettings]);

  const updateMutation = useMutation({
    mutationFn: (updated: any) =>
      apiFetch('/api/settings', {
        method: 'PUT',
        body: JSON.stringify(updated),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['system-settings'] });
      toast({ type: 'success', message: 'Settings saved' });
      onClose();
    },
    onError: (err: any) => {
      toast({ type: 'error', message: err.message || 'Failed to save settings' });
    },
  });

  const resetMutation = useMutation({
    mutationFn: () => apiFetch('/api/settings/reset', { method: 'POST' }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['system-settings'] });
      toast({ type: 'info', message: 'Settings reset to default parameters' });
      onClose();
    },
    onError: (err: any) => {
      toast({ type: 'error', message: err.message || 'Failed to reset settings' });
    },
  });

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="System Settings"
      subtitle="Operational tolerances and optimizer parameters"
      footer={
        <div className="w-full flex items-center justify-between">
          <Button
            variant="quiet"
            loading={resetMutation.isPending}
            onClick={() => resetMutation.mutate()}
            icon={<RotateCcw className="w-3.5 h-3.5" strokeWidth={1.5} />}
          >
            Reset to defaults
          </Button>
          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={updateMutation.isPending}
              onClick={() => updateMutation.mutate(formState)}
            >
              Save settings
            </Button>
          </div>
        </div>
      }
    >
      <div className="flex flex-col gap-5">
        <Field
          label="Planning horizon (H, days)"
          hint="Calendar days of future demand covered by this planning run."
        >
          <Input
            type="number"
            min={1}
            max={28}
            value={formState.H || 7}
            onChange={(e) => setFormState({ ...formState, H: parseInt(e.target.value) || 7 })}
          />
        </Field>

        <Field
          label="Safety-stock z-score (z)"
          hint="Statistical multiplier determining target fulfillment service level (default 1.28 ≈ 90%)."
        >
          <Input
            type="number"
            step="0.01"
            value={formState.z || 1.28}
            onChange={(e) => setFormState({ ...formState, z: parseFloat(e.target.value) || 1.28 })}
          />
        </Field>

        <Field
          label="Maximum lead time gap (Gmax, days)"
          hint="Maximum allowed gap between arrival date and destination stockout date (default 1 day)."
        >
          <Input
            type="number"
            min={0}
            max={7}
            value={formState.Gmax || 1}
            onChange={(e) => setFormState({ ...formState, Gmax: parseInt(e.target.value) || 1 })}
          />
        </Field>

        <Field
          label="Planner reserve (cartons)"
          hint="Cartons withheld per warehouse batch before allocation to guard against physical shrinkage."
        >
          <Input
            type="number"
            min={0}
            value={formState.planner_reserve || 0}
            onChange={(e) => setFormState({ ...formState, planner_reserve: parseInt(e.target.value) || 0 })}
          />
        </Field>

        <Field
          label="Minimum acceptance shelf life (Eshort, days)"
          hint="Minimum remaining shelf life required at destination receiving dock (default 21 days)."
        >
          <Input
            type="number"
            min={1}
            value={formState.min_remaining_shelf_days || 21}
            onChange={(e) => setFormState({ ...formState, min_remaining_shelf_days: parseInt(e.target.value) || 21 })}
          />
        </Field>
      </div>
    </Drawer>
  );
}
