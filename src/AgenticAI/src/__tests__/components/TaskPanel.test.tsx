jest.mock('react-icons/fi', () => ({
  FiPlus: () => 'FiPlus',
  FiCheck: () => 'FiCheck',
  FiTrash2: () => 'FiTrash2',
}));

jest.mock('react-markdown', () => ({
  __esModule: true,
  default: ({ children }: any) => children,
}));

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { TaskPanel } from '../../renderer/components/TaskPanel';
import { useAppStore } from '../../renderer/store/useAppStore';

describe('TaskPanel', () => {
  beforeEach(() => {
    useAppStore.setState({
      tasks: [],
      spec: null,
    });
  });

  it('should render tasks header', () => {
    render(<TaskPanel />);
    
    expect(screen.getByText('Tasks')).toBeInTheDocument();
  });

  it('should show task stats', () => {
    render(<TaskPanel />);
    
    expect(screen.getByText('0 todo')).toBeInTheDocument();
    expect(screen.getByText('0 doing')).toBeInTheDocument();
    expect(screen.getByText('0 done')).toBeInTheDocument();
  });

  it('should render input for new task', () => {
    render(<TaskPanel />);
    
    const input = screen.getByPlaceholderText('Add new task...');
    expect(input).toBeInTheDocument();
  });

  it('should render add button', () => {
    render(<TaskPanel />);
    
    expect(screen.getByText('FiPlus')).toBeInTheDocument();
  });

  it('should show no tasks message when task list is empty', () => {
    render(<TaskPanel />);
    
    expect(screen.getByText('No tasks yet. Add one above!')).toBeInTheDocument();
  });

  it('should add task when pressing Enter', () => {
    render(<TaskPanel />);
    
    const input = screen.getByPlaceholderText('Add new task...') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'New task' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    
    expect(useAppStore.getState().tasks).toContainEqual(
      expect.objectContaining({
        title: 'New task',
        status: 'todo',
        priority: 'medium',
      })
    );
  });

  it('should add task when clicking add button', () => {
    render(<TaskPanel />);
    
    const input = screen.getByPlaceholderText('Add new task...') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'Button task' } });
    
    const addButton = screen.getByText('FiPlus').closest('button')!;
    fireEvent.click(addButton);
    
    expect(useAppStore.getState().tasks).toContainEqual(
      expect.objectContaining({
        title: 'Button task',
        status: 'todo',
      })
    );
  });

  it('should clear input after adding task', () => {
    render(<TaskPanel />);
    
    const input = screen.getByPlaceholderText('Add new task...') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'New task' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    
    expect(input.value).toBe('');
  });

  it('should not add empty task', () => {
    render(<TaskPanel />);
    
    const input = screen.getByPlaceholderText('Add new task...') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '   ' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    
    expect(useAppStore.getState().tasks).toEqual([]);
  });

  it('should toggle task status when checkbox is clicked', () => {
    useAppStore.setState({
      tasks: [
        {
          id: '1',
          title: 'Test task',
          status: 'todo',
          priority: 'medium',
          createdAt: new Date().toISOString(),
        },
      ],
    });

    render(<TaskPanel />);

    const checkbox = screen.getByText('○').closest('button');
    fireEvent.click(checkbox!);

    const updatedTask = useAppStore.getState().tasks.find(t => t.id === '1');
    expect(updatedTask?.status).toBe('done');
  });

  it('should toggle task back to todo when completed', () => {
    useAppStore.setState({
      tasks: [
        {
          id: '1',
          title: 'Test task',
          status: 'done',
          priority: 'medium',
          createdAt: new Date().toISOString(),
          completedAt: new Date().toISOString(),
        },
      ],
    });

    render(<TaskPanel />);

    const checkbox = screen.getByText('FiCheck').closest('button')!;
    fireEvent.click(checkbox);

    const updatedTask = useAppStore.getState().tasks.find(t => t.id === '1');
    expect(updatedTask?.status).toBe('todo');
  });

  it('should delete task when delete button is clicked', () => {
    useAppStore.setState({
      tasks: [
        {
          id: '1',
          title: 'Task to delete',
          status: 'todo',
          priority: 'medium',
          createdAt: new Date().toISOString(),
        },
      ],
    });

    render(<TaskPanel />);

    const deleteButton = screen.getByText('FiTrash2').closest('button')!;
    fireEvent.click(deleteButton);

    expect(useAppStore.getState().tasks).toEqual([]);
  });

  it('should display tasks in correct groups', () => {
    useAppStore.setState({
      tasks: [
        {
          id: '1',
          title: 'Todo task',
          status: 'todo',
          priority: 'medium',
          createdAt: new Date().toISOString(),
        },
        {
          id: '2',
          title: 'Done task',
          status: 'done',
          priority: 'medium',
          createdAt: new Date().toISOString(),
        },
      ],
    });

    render(<TaskPanel />);

    expect(screen.getByText('To Do')).toBeInTheDocument();
    expect(screen.getByText('Done')).toBeInTheDocument();
    expect(screen.getByText('Todo task')).toBeInTheDocument();
    expect(screen.getByText('Done task')).toBeInTheDocument();
  });

  it('should update task stats when tasks change', () => {
    useAppStore.setState({
      tasks: [
        {
          id: '1',
          title: 'Task 1',
          status: 'todo',
          priority: 'medium',
          createdAt: new Date().toISOString(),
        },
        {
          id: '2',
          title: 'Task 2',
          status: 'done',
          priority: 'medium',
          createdAt: new Date().toISOString(),
        },
      ],
    });

    render(<TaskPanel />);

    expect(screen.getByText('1 todo')).toBeInTheDocument();
    expect(screen.getByText('1 done')).toBeInTheDocument();
  });

  it('should display spec section when spec is provided', () => {
    useAppStore.setState({
      spec: {
        id: 'spec1',
        title: 'Test Spec',
        content: 'Spec content here',
        tasks: [],
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      },
    });

    render(<TaskPanel />);

    expect(screen.getByText('Spec: Test Spec')).toBeInTheDocument();
  });

  it('should group tasks by status', () => {
    useAppStore.setState({
      tasks: [
        { id: '1', title: 'Task 1', status: 'todo', priority: 'medium', createdAt: new Date().toISOString() },
        { id: '2', title: 'Task 2', status: 'todo', priority: 'medium', createdAt: new Date().toISOString() },
        { id: '3', title: 'Task 3', status: 'doing', priority: 'medium', createdAt: new Date().toISOString() },
        { id: '4', title: 'Task 4', status: 'done', priority: 'medium', createdAt: new Date().toISOString() },
      ],
    });

    render(<TaskPanel />);

    expect(screen.getByText('2 todo')).toBeInTheDocument();
    expect(screen.getByText('1 doing')).toBeInTheDocument();
    expect(screen.getByText('1 done')).toBeInTheDocument();
  });

  it('should not show groups with no tasks', () => {
    useAppStore.setState({
      tasks: [
        { id: '1', title: 'Task 1', status: 'todo', priority: 'medium', createdAt: new Date().toISOString() },
      ],
    });

    render(<TaskPanel />);

    expect(screen.queryByText('In Progress')).not.toBeInTheDocument();
    expect(screen.queryByText('Done')).not.toBeInTheDocument();
    expect(screen.getByText('To Do')).toBeInTheDocument();
  });
});
