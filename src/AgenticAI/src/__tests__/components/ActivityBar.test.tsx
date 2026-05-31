jest.mock('react-icons/fi', () => ({
  FiFolder: () => 'FiFolder',
  FiSearch: () => 'FiSearch',
  FiGitBranch: () => 'FiGitBranch',
  FiTerminal: () => 'FiTerminal',
  FiSettings: () => 'FiSettings',
}));

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { ActivityBar } from '../../renderer/components/ActivityBar';
import { useAppStore } from '../../renderer/store/useAppStore';

describe('ActivityBar', () => {
  beforeEach(() => {
    useAppStore.setState({
      activeSidebarView: 'explorer',
    });
  });

  it('should render all activity icons', () => {
    render(<ActivityBar />);
    
    expect(screen.getByText('FiFolder')).toBeInTheDocument();
    expect(screen.getByText('FiSearch')).toBeInTheDocument();
    expect(screen.getByText('FiGitBranch')).toBeInTheDocument();
    expect(screen.getByText('FiTerminal')).toBeInTheDocument();
    expect(screen.getByText('FiSettings')).toBeInTheDocument();
  });

  it('should have Explorer button with correct title', () => {
    render(<ActivityBar />);
    
    const explorerButton = screen.getByTitle('Explorer');
    expect(explorerButton).toBeInTheDocument();
  });

  it('should have Search button with correct title', () => {
    render(<ActivityBar />);
    
    const searchButton = screen.getByTitle('Search');
    expect(searchButton).toBeInTheDocument();
  });

  it('should have Source Control button with correct title', () => {
    render(<ActivityBar />);
    
    const gitButton = screen.getByTitle('Source Control');
    expect(gitButton).toBeInTheDocument();
  });

  it('should have Terminal button with correct title', () => {
    render(<ActivityBar />);
    
    const terminalButton = screen.getByTitle('Terminal');
    expect(terminalButton).toBeInTheDocument();
  });

  it('should have Settings button with correct title', () => {
    render(<ActivityBar />);
    
    const settingsButton = screen.getByTitle('Settings');
    expect(settingsButton).toBeInTheDocument();
  });

  it('should switch to explorer view when clicked', () => {
    render(<ActivityBar />);
    
    const explorerButton = screen.getByTitle('Explorer');
    fireEvent.click(explorerButton);
    
    expect(useAppStore.getState().activeSidebarView).toBe('explorer');
  });

  it('should switch to search view when clicked', () => {
    render(<ActivityBar />);
    
    const searchButton = screen.getByTitle('Search');
    fireEvent.click(searchButton);
    
    expect(useAppStore.getState().activeSidebarView).toBe('search');
  });

  it('should switch to git view when clicked', () => {
    render(<ActivityBar />);
    
    const gitButton = screen.getByTitle('Source Control');
    fireEvent.click(gitButton);
    
    expect(useAppStore.getState().activeSidebarView).toBe('git');
  });

  it('should switch to terminal view when clicked', () => {
    render(<ActivityBar />);
    
    const terminalButton = screen.getByTitle('Terminal');
    fireEvent.click(terminalButton);
    
    expect(useAppStore.getState().activeSidebarView).toBe('terminal');
  });

  it('should open settings when settings button is clicked', () => {
    render(<ActivityBar />);
    
    const settingsButton = screen.getByTitle('Settings');
    fireEvent.click(settingsButton);
    
    expect(useAppStore.getState().activeSidebarView).toBe('settings');
  });

  it('should apply active class to current view', () => {
    useAppStore.setState({ activeSidebarView: 'git' });
    
    render(<ActivityBar />);
    
    const gitButton = screen.getByTitle('Source Control');
    expect(gitButton.closest('button')).toHaveClass('activity-icon', 'active');
  });

  it('should not apply active class to non-current views', () => {
    useAppStore.setState({ activeSidebarView: 'explorer' });
    
    render(<ActivityBar />);
    
    const gitButton = screen.getByTitle('Source Control');
    expect(gitButton.closest('button')).not.toHaveClass('active');
  });

  it('should render 5 activity icons', () => {
    render(<ActivityBar />);
    
    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThanOrEqual(5);
  });
});
