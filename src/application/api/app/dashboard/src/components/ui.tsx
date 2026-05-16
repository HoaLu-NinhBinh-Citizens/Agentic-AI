import { clsx } from 'clsx';

interface StatusIndicatorProps {
  status: 'connected' | 'disconnected' | 'running' | 'error' | 'warning';
  size?: 'sm' | 'md' | 'lg';
  pulse?: boolean;
  label?: string;
  className?: string;
}

const sizeClasses = {
  sm: 'w-2 h-2',
  md: 'w-3 h-3',
  lg: 'w-4 h-4',
};

const colorClasses = {
  connected: 'bg-green-500',
  running: 'bg-blue-500',
  warning: 'bg-yellow-500',
  error: 'bg-red-500',
  disconnected: 'bg-gray-400',
};

export function StatusIndicator({ 
  status, 
  size = 'md', 
  pulse = false,
  label,
  className
}: StatusIndicatorProps) {
  return (
    <div className={clsx("flex items-center gap-2", className)}>
      <span 
        className={clsx(
          'rounded-full',
          sizeClasses[size],
          colorClasses[status],
          pulse && 'animate-pulse-slow'
        )} 
      />
      {label && (
        <span className="text-sm text-gray-400">{label}</span>
      )}
    </div>
  );
}

interface ProgressBarProps {
  value: number;
  max?: number;
  color?: 'blue' | 'green' | 'yellow' | 'red';
  size?: 'sm' | 'md';
  showLabel?: boolean;
}

export function ProgressBar({ 
  value, 
  max = 100, 
  color = 'blue',
  size = 'md',
  showLabel = false 
}: ProgressBarProps) {
  const percent = Math.min(100, Math.max(0, (value / max) * 100));
  
  const colorClasses = {
    blue: 'bg-blue-500',
    green: 'bg-green-500',
    yellow: 'bg-yellow-500',
    red: 'bg-red-500',
  };
  
  const sizeClasses = {
    sm: 'h-1',
    md: 'h-2',
  };

  return (
    <div className="flex items-center gap-2">
      <div className={clsx('flex-1 bg-gray-700 rounded-full overflow-hidden', sizeClasses[size])}>
        <div 
          className={clsx('h-full transition-all duration-300', colorClasses[color])}
          style={{ width: `${percent}%` }}
        />
      </div>
      {showLabel && (
        <span className="text-sm text-gray-400 w-12 text-right">{percent.toFixed(0)}%</span>
      )}
    </div>
  );
}

interface CardProps {
  title?: string;
  children: React.ReactNode;
  className?: string;
  headerRight?: React.ReactNode;
}

export function Card({ title, children, className, headerRight }: CardProps) {
  return (
    <div className={clsx('bg-gray-800 rounded-lg border border-gray-700 overflow-hidden', className)}>
      {title && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
          <h3 className="text-sm font-medium text-gray-200">{title}</h3>
          {headerRight}
        </div>
      )}
      <div className="p-4">
        {children}
      </div>
    </div>
  );
}

interface MetricCardProps {
  label: string;
  value: string | number;
  unit?: string;
  change?: { value: number; type: 'increase' | 'decrease' };
  icon?: React.ReactNode;
}

export function MetricCard({ label, value, unit, change, icon }: MetricCardProps) {
  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-gray-400 mb-1">{label}</p>
          <div className="flex items-baseline gap-1">
            <span className="text-2xl font-semibold text-white">{value}</span>
            {unit && <span className="text-sm text-gray-500">{unit}</span>}
          </div>
          {change && (
            <p className={clsx(
              'text-xs mt-1',
              change.type === 'increase' ? 'text-green-400' : 'text-red-400'
            )}>
              {change.type === 'increase' ? '+' : '-'}{change.value}%
            </p>
          )}
        </div>
        {icon && (
          <div className="text-gray-500">
            {icon}
          </div>
        )}
      </div>
    </div>
  );
}

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'error' | 'info';
  size?: 'sm' | 'md';
}

export function Badge({ children, variant = 'default', size = 'sm' }: BadgeProps) {
  const variantClasses = {
    default: 'bg-gray-700 text-gray-300',
    success: 'bg-green-900 text-green-300',
    warning: 'bg-yellow-900 text-yellow-300',
    error: 'bg-red-900 text-red-300',
    info: 'bg-blue-900 text-blue-300',
  };

  const sizeClasses = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-2.5 py-1 text-sm',
  };

  return (
    <span className={clsx(
      'inline-flex items-center rounded-full font-medium',
      variantClasses[variant],
      sizeClasses[size]
    )}>
      {children}
    </span>
  );
}

interface TableProps {
  columns: { key: string; label: string; width?: string }[];
  data: Record<string, React.ReactNode>[];
  emptyMessage?: string;
}

export function Table({ columns, data, emptyMessage = 'No data' }: TableProps) {
  if (data.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-gray-700">
            {columns.map(col => (
              <th 
                key={col.key}
                className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider py-2 px-3"
                style={{ width: col.width }}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={i} className="border-b border-gray-700/50 hover:bg-gray-700/30">
              {columns.map(col => (
                <td key={col.key} className="py-2 px-3 text-sm text-gray-300">
                  {row[col.key] !== undefined && row[col.key] !== null
                    ? typeof row[col.key] === 'string' || typeof row[col.key] === 'number'
                      ? String(row[col.key])
                      : row[col.key]
                    : '-'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
