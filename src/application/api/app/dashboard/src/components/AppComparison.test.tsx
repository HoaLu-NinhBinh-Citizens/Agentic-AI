import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AppComparison, type AppData } from '@/components/AppComparison';

describe('AppComparison', () => {
  const mockApps: AppData[] = [
    { id: 'reader', name: 'Reader', percentage: 89, icon: '📖' },
    { id: 'edge', name: 'Edge', percentage: 85, icon: '🌐' },
    { id: 'audacity', name: 'Audacity', percentage: 76, icon: '🎵' },
    { id: 'cursor', name: 'Cursor', percentage: 60, icon: '💡' },
    { id: 'chrome', name: 'Chrome', percentage: 58, icon: '🔵' },
  ];

  describe('Rendering', () => {
    it('renders all app cards', () => {
      render(<AppComparison apps={mockApps} />);
      
      mockApps.forEach(app => {
        expect(screen.getByText(app.name)).toBeInTheDocument();
        expect(screen.getByText(`${app.percentage}%`)).toBeInTheDocument();
        expect(screen.getByText(app.icon)).toBeInTheDocument();
      });
    });

    it('renders category navigation buttons', () => {
      render(<AppComparison apps={mockApps} />);
      
      expect(screen.getByText('Tất cả')).toBeInTheDocument();
      expect(screen.getByText('Tin tức')).toBeInTheDocument();
      expect(screen.getByText('Thể thao')).toBeInTheDocument();
      expect(screen.getByText('Giải trí')).toBeInTheDocument();
    });

    it('renders with default apps when no apps prop provided', () => {
      render(<AppComparison />);
      
      expect(screen.getByText('Reader')).toBeInTheDocument();
      expect(screen.getByText('Edge')).toBeInTheDocument();
      expect(screen.getByText('89%')).toBeInTheDocument();
    });
  });

  describe('Selection', () => {
    it('calls onSelectApp when clicking an app card', () => {
      const onSelectApp = vi.fn();
      render(<AppComparison apps={mockApps} onSelectApp={onSelectApp} />);
      
      fireEvent.click(screen.getByText('Reader'));
      expect(onSelectApp).toHaveBeenCalledWith('reader');
    });

    it('calls onSelectApp with empty string when clicking selected app', () => {
      const onSelectApp = vi.fn();
      render(<AppComparison apps={mockApps} selectedAppId="reader" onSelectApp={onSelectApp} />);
      
      fireEvent.click(screen.getByText('Reader'));
      expect(onSelectApp).toHaveBeenCalledWith('');
    });

    it('calls onSelectApp when clicking category button', () => {
      const onSelectApp = vi.fn();
      render(<AppComparison apps={mockApps} onSelectApp={onSelectApp} />);
      
      fireEvent.click(screen.getByText('Tin tức'));
      expect(onSelectApp).toHaveBeenCalledWith('news');
    });
  });

  describe('Visual States', () => {
    it('applies selected styles when app is selected', () => {
      render(<AppComparison apps={mockApps} selectedAppId="reader" />);
      
      const readerCard = screen.getByText('Reader').closest('button');
      expect(readerCard).toHaveClass('ring-2');
      expect(readerCard).toHaveClass('ring-blue-500/50');
    });

    it('does not apply selected styles when app is not selected', () => {
      render(<AppComparison apps={mockApps} selectedAppId="reader" />);
      
      const edgeCard = screen.getByText('Edge').closest('button');
      expect(edgeCard).not.toHaveClass('ring-2');
    });
  });

  describe('Custom Apps', () => {
    it('renders custom app data', () => {
      const customApps: AppData[] = [
        { id: 'custom1', name: 'Custom App', percentage: 95, icon: '⭐' },
      ];
      
      render(<AppComparison apps={customApps} />);
      
      expect(screen.getByText('Custom App')).toBeInTheDocument();
      expect(screen.getByText('95%')).toBeInTheDocument();
      expect(screen.getByText('⭐')).toBeInTheDocument();
    });
  });
});
