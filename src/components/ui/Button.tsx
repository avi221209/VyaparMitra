import React, { forwardRef } from 'react';
import { Loader2 } from 'lucide-react';

export type ButtonVariant = 'primary' | 'secondary' | 'quiet' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: React.ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = 'secondary',
      size = 'md',
      loading = false,
      disabled = false,
      icon,
      children,
      className = '',
      ...props
    },
    ref
  ) => {
    const baseStyles =
      'inline-flex items-center justify-center font-medium font-sans rounded-control border text-body select-none transition-colors duration-100 focus-visible:outline-2 focus-visible:outline-brand focus-visible:outline-offset-2 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50';

    const sizeStyles = {
      sm: 'h-8 px-2.5 text-meta gap-1.5',
      md: 'h-9 px-3.5 text-body gap-2',
      lg: 'h-10 px-4 text-body gap-2.5',
    }[size];

    const variantStyles = {
      primary:
        'bg-brand text-surface border-brand hover:opacity-90 active:opacity-95 shadow-none',
      secondary:
        'bg-surface text-ink border-line-strong hover:bg-paper active:bg-paper',
      quiet:
        'bg-transparent text-ink-2 border-transparent hover:bg-paper hover:text-ink active:bg-paper',
      danger:
        'bg-madder text-surface border-madder hover:opacity-90 active:opacity-95',
    }[variant];


    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        aria-busy={loading}
        className={`${baseStyles} ${sizeStyles} ${variantStyles} ${className}`}
        {...props}
      >
        {loading ? (
          <Loader2 className="w-4 h-4 animate-spin text-current" strokeWidth={1.5} />
        ) : (
          icon && <span className="inline-flex shrink-0">{icon}</span>
        )}
        <span>{children}</span>
      </button>
    );
  }
);

Button.displayName = 'Button';
