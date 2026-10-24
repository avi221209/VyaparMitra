import React, { forwardRef } from 'react';

export interface FieldProps {
  label?: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: React.ReactNode;
  className?: string;
  id?: string;
}

export function Field({
  label,
  hint,
  error,
  required,
  children,
  className = '',
  id,
}: FieldProps) {
  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      {label && (
        <label
          htmlFor={id}
          className="text-meta font-medium text-ink flex items-center justify-between"
        >
          <span>
            {label}
            {required && <span className="text-madder ml-0.5">*</span>}
          </span>
        </label>
      )}
      {children}
      {error && <span className="text-meta text-madder font-normal">{error}</span>}
      {!error && hint && <span className="text-meta text-ink-3 font-normal">{hint}</span>}
    </div>
  );
}

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  error?: boolean;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ error = false, className = '', type = 'text', ...props }, ref) => {
    const isNumber = type === 'number';
    return (
      <input
        ref={ref}
        type={type}
        className={`h-9 px-3 bg-surface text-ink border rounded-control text-body transition-colors duration-100 placeholder:text-ink-3 disabled:bg-paper disabled:text-ink-3 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-brand focus-visible:outline-offset-2 ${
          error ? 'border-madder' : 'border-line-strong'
        } ${isNumber ? 'tabular-nums text-right' : ''} ${className}`}
        {...props}
      />
    );
  }
);

Input.displayName = 'Input';

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  error?: boolean;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ error = false, className = '', children, ...props }, ref) => {
    return (
      <select
        ref={ref}
        className={`h-9 px-3 bg-surface text-ink border rounded-control text-body transition-colors duration-100 disabled:bg-paper disabled:text-ink-3 focus-visible:outline-2 focus-visible:outline-brand focus-visible:outline-offset-2 ${
          error ? 'border-madder' : 'border-line-strong'
        } ${className}`}
        {...props}
      >
        {children}
      </select>
    );
  }
);

Select.displayName = 'Select';
