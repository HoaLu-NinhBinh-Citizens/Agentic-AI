import React, { useState } from 'react';
import { useAppStore } from '../store/useAppStore';
import { FiPlus, FiCheck, FiTrash2 } from 'react-icons/fi';
import ReactMarkdown from 'react-markdown';

export const TaskPanel: React.FC = () => {
  const { tasks, addTask, updateTask, deleteTask, spec } = useAppStore();
  const [newTaskTitle, setNewTaskTitle] = useState('');
  const [showSpec, setShowSpec] = useState(true);

  const createTask = () => {
    if (!newTaskTitle.trim()) return;
    
    const task = {
      id: Date.now().toString(),
      title: newTaskTitle,
      status: 'todo' as const,
      priority: 'medium' as const,
      createdAt: new Date().toISOString()
    };
    
    addTask(task);
    setNewTaskTitle('');
  };

  const toggleTaskStatus = (id: string) => {
    const task = tasks.find(t => t.id === id);
    if (task) {
      const newStatus = task.status === 'done' ? 'todo' : 'done';
      updateTask(id, { 
        status: newStatus,
        completedAt: newStatus === 'done' ? new Date().toISOString() : undefined
      });
    }
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'high': return '#ff6b6b';
      case 'medium': return '#ffd93d';
      case 'low': return '#6bcb77';
      default: return '#888';
    }
  };

  const todoTasks = tasks.filter(t => t.status === 'todo');
  const doingTasks = tasks.filter(t => t.status === 'doing');
  const doneTasks = tasks.filter(t => t.status === 'done');

  return (
    <div className="task-panel">
      <div className="task-panel-header">
        <h3>Tasks</h3>
        <div className="task-stats">
          <span className="stat">{todoTasks.length} todo</span>
          <span className="stat">{doingTasks.length} doing</span>
          <span className="stat">{doneTasks.length} done</span>
        </div>
      </div>

      {spec && showSpec && (
        <div className="spec-section">
          <div className="spec-header" onClick={() => setShowSpec(false)}>
            <h4>Spec: {spec.title}</h4>
          </div>
          {showSpec && (
            <div className="spec-content">
              <ReactMarkdown>{spec.content}</ReactMarkdown>
            </div>
          )}
        </div>
      )}

      <div className="new-task">
        <input
          type="text"
          placeholder="Add new task..."
          value={newTaskTitle}
          onChange={(e) => setNewTaskTitle(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && createTask()}
        />
        <button onClick={createTask}><FiPlus /></button>
      </div>

      <div className="task-list">
        {doingTasks.length > 0 && (
          <div className="task-group">
            <h5>In Progress</h5>
            {doingTasks.map(task => (
              <TaskItem 
                key={task.id} 
                task={task} 
                onToggle={() => toggleTaskStatus(task.id)}
                onDelete={() => deleteTask(task.id)}
                priorityColor={getPriorityColor(task.priority)}
              />
            ))}
          </div>
        )}
        
        {todoTasks.length > 0 && (
          <div className="task-group">
            <h5>To Do</h5>
            {todoTasks.map(task => (
              <TaskItem 
                key={task.id} 
                task={task} 
                onToggle={() => toggleTaskStatus(task.id)}
                onDelete={() => deleteTask(task.id)}
                priorityColor={getPriorityColor(task.priority)}
              />
            ))}
          </div>
        )}

        {doneTasks.length > 0 && (
          <div className="task-group done">
            <h5>Done</h5>
            {doneTasks.map(task => (
              <TaskItem 
                key={task.id} 
                task={task} 
                onToggle={() => toggleTaskStatus(task.id)}
                onDelete={() => deleteTask(task.id)}
                priorityColor={getPriorityColor(task.priority)}
              />
            ))}
          </div>
        )}

        {tasks.length === 0 && (
          <div className="no-tasks">
            <p>No tasks yet. Add one above!</p>
          </div>
        )}
      </div>
    </div>
  );
};

const TaskItem: React.FC<{
  task: any;
  onToggle: () => void;
  onDelete: () => void;
  priorityColor: string;
}> = ({ task, onToggle, onDelete, priorityColor }) => (
  <div className={`task-item ${task.status}`}>
    <button className="task-checkbox" onClick={onToggle}>
      {task.status === 'done' ? <FiCheck /> : <span style={{ color: priorityColor }}>○</span>}
    </button>
    <div className="task-content">
      <span className="task-title">{task.title}</span>
      {task.description && <p className="task-desc">{task.description}</p>}
    </div>
    <button className="task-delete" onClick={onDelete}><FiTrash2 /></button>
  </div>
);
