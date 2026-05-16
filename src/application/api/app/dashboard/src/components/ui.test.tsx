import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  StatusIndicator,
  ProgressBar,
  Card,
  MetricCard,
  Badge,
  Table,
} from '@/components/ui';

describe('StatusIndicator', () => {
  it('renders with connected status', () => {
    render(<StatusIndicator status="connected" label="Agent" />);
    expect(screen.getByText('Agent')).toBeInTheDocument();
  });

  it('renders with disconnected status', () => {
    render(<StatusIndicator status="disconnected" label="Offline" />);
    expect(screen.getByText('Offline')).toBeInTheDocument();
  });

  it('renders with error status', () => {
    render(<StatusIndicator status="error" label="Error" />);
    expect(screen.getByText('Error')).toBeInTheDocument();
  });

  it('renders without label', () => {
    const { container } = render(<StatusIndicator status="connected" />);
    expect(container.querySelector('.rounded-full')).toBeInTheDocument();
  });
});

describe('ProgressBar', () => {
  it('renders with default values', () => {
    render(<ProgressBar value={50} />);
    const bar = document.querySelector('.bg-blue-500');
    expect(bar).toBeInTheDocument();
  });

  it('renders with custom color', () => {
    render(<ProgressBar value={75} color="green" />);
    const bar = document.querySelector('.bg-green-500');
    expect(bar).toBeInTheDocument();
  });

  it('clamps value between 0 and 100', () => {
    const { container } = render(<ProgressBar value={150} />);
    const innerBar = container.querySelector('.bg-blue-500');
    expect(innerBar).toBeInTheDocument();
    expect(innerBar?.getAttribute('style')).toContain('width: 100%');
  });

  it('handles zero value', () => {
    const { container } = render(<ProgressBar value={0} />);
    const innerBar = container.querySelector('.bg-blue-500');
    expect(innerBar).toBeInTheDocument();
    expect(innerBar?.getAttribute('style')).toContain('width: 0%');
  });

  it('renders with label when showLabel is true', () => {
    render(<ProgressBar value={50} showLabel />);
    expect(screen.getByText('50%')).toBeInTheDocument();
  });
});

describe('Card', () => {
  it('renders with title', () => {
    render(
      <Card title="Test Card">
        <p>Content</p>
      </Card>
    );
    expect(screen.getByText('Test Card')).toBeInTheDocument();
  });

  it('renders children content', () => {
    render(
      <Card title="Card">
        <span data-testid="content">Card Content</span>
      </Card>
    );
    expect(screen.getByTestId('content')).toBeInTheDocument();
  });

  it('renders headerRight when provided', () => {
    render(
      <Card title="Card" headerRight={<button>Action</button>}>
        Content
      </Card>
    );
    expect(screen.getByRole('button', { name: 'Action' })).toBeInTheDocument();
  });

  it('applies custom className', () => {
    const { container } = render(
      <Card title="Card" className="custom-class">
        Content
      </Card>
    );
    expect(container.firstChild).toHaveClass('custom-class');
  });
});

describe('MetricCard', () => {
  it('renders label and value', () => {
    render(<MetricCard label="Uptime" value="24h" />);
    expect(screen.getByText('Uptime')).toBeInTheDocument();
    expect(screen.getByText('24h')).toBeInTheDocument();
  });

  it('renders with numeric value', () => {
    render(<MetricCard label="Tasks" value={42} />);
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  it('renders unit when provided', () => {
    render(<MetricCard label="Speed" value={100} unit="km/h" />);
    expect(screen.getByText('km/h')).toBeInTheDocument();
  });

  it('renders change indicator', () => {
    render(
      <MetricCard
        label="Rate"
        value="95%"
        change={{ value: 5, type: 'increase' }}
      />
    );
    expect(screen.getByText('+5%')).toBeInTheDocument();
  });

  it('renders icon when provided', () => {
    render(
      <MetricCard
        label="Test"
        value="100"
        icon={<span data-testid="icon">Icon</span>}
      />
    );
    expect(screen.getByTestId('icon')).toBeInTheDocument();
  });
});

describe('Badge', () => {
  it('renders children text', () => {
    render(<Badge>Test Badge</Badge>);
    expect(screen.getByText('Test Badge')).toBeInTheDocument();
  });

  it('renders with default variant', () => {
    render(<Badge>Default</Badge>);
    const badge = screen.getByText('Default');
    expect(badge).toHaveClass('bg-gray-700');
  });

  it('renders with success variant', () => {
    render(<Badge variant="success">Success</Badge>);
    const badge = screen.getByText('Success');
    expect(badge).toHaveClass('bg-green-900');
  });

  it('renders with warning variant', () => {
    render(<Badge variant="warning">Warning</Badge>);
    const badge = screen.getByText('Warning');
    expect(badge).toHaveClass('bg-yellow-900');
  });

  it('renders with error variant', () => {
    render(<Badge variant="error">Error</Badge>);
    const badge = screen.getByText('Error');
    expect(badge).toHaveClass('bg-red-900');
  });

  it('renders with info variant', () => {
    render(<Badge variant="info">Info</Badge>);
    const badge = screen.getByText('Info');
    expect(badge).toHaveClass('bg-blue-900');
  });
});

describe('Table', () => {
  const columns = [
    { key: 'name', label: 'Name', width: '150px' },
    { key: 'status', label: 'Status', width: '100px' },
    { key: 'value', label: 'Value' },
  ];

  const data = [
    { name: 'Item 1', status: 'Active', value: '100' },
    { name: 'Item 2', status: 'Inactive', value: '50' },
  ];

  it('renders with data', () => {
    render(<Table columns={columns} data={data} />);
    expect(screen.getByText('Item 1')).toBeInTheDocument();
    expect(screen.getByText('Item 2')).toBeInTheDocument();
  });

  it('renders column headers', () => {
    render(<Table columns={columns} data={data} />);
    expect(screen.getByText('Name')).toBeInTheDocument();
    expect(screen.getByText('Status')).toBeInTheDocument();
    expect(screen.getByText('Value')).toBeInTheDocument();
  });

  it('renders empty state with emptyMessage', () => {
    render(<Table columns={columns} data={[]} emptyMessage="No data available" />);
    expect(screen.getByText('No data available')).toBeInTheDocument();
  });

  it('renders default empty state', () => {
    render(<Table columns={columns} data={[]} />);
    expect(screen.getByText('No data')).toBeInTheDocument();
  });

  it('renders with custom empty message', () => {
    render(
      <Table
        columns={columns}
        data={[]}
        emptyMessage="Custom empty message"
      />
    );
    expect(screen.getByText('Custom empty message')).toBeInTheDocument();
  });
});
