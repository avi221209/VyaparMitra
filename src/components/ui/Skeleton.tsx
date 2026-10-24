import React from 'react';

export interface SkeletonProps {
  className?: string;
  width?: string;
  height?: string;
}

export function Skeleton({ className = '', width, height }: SkeletonProps) {
  return (
    <div
      style={{ width, height }}
      className={`bg-line/60 animate-pulse rounded-chip ${className}`}
    />
  );
}
