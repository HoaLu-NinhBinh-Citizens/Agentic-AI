import React, { useState, useEffect } from 'react';
import clsx from 'clsx';
import { v4 as uuidv4 } from 'uuid';
import {
  CheckCircle2,
  Circle,
  Clock,
  Plus,
  Trash2,
  Edit3,
  ChevronDown,
  ChevronRight,
  AlertCircle,
  ArrowUp,
  ArrowDown,
  FileText,
  ListTodo,
  Layout,
} from 'lucide-react';
import { useAgenticStore, Task, Spec, TaskStatus, TaskPriority, selectTaskStats } from '../store/useAgenticStore';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// Priority icons and colors
const PRIORITY_CONFIG: Record<TaskPriority, { icon: React.ReactNode; color: string; label: string }> = {
  critical: { icon: <AlertCircle className="w-3 h-3" />, color: 'text-red-400', label: 'Critical' },
  high: { icon: <ArrowUp className="w-3 h-3" />, color: 'text-orange-400', label: 'High' },
  medium: { icon: <ArrowDown className="w-3 h-3" />, color: 'text-yellow-400', label: 'Medium' },
  low: { icon: <Circle className="w-3 h-3" />, color: 'text-gray-400', label: 'Low' },
};

// Status icons
const STATUS_ICONS: Record<TaskStatus, React.ReactNode> = {
  todo: <Circle className="w-4 h-4 text-gray-500" />,
  doing: <Clock className="w-4 h-4 text-blue-400 animate-pulse" />,
  done: <CheckCircle2 className="w-4 h-4 text-green-400" />,
};

interface TaskItemProps {
  task: Task;
  onToggle: () => void;
  onDelete: () => void;
  onEdit: () => void;
}

function TaskItem({ task, onToggle, onDelete, onEdit }: TaskItemProps) {
  const [expanded, setExpanded] = useState(false);
  const priorityConfig = PRIORITY_CONFIG[task.priority];

  return (
    <div
      className={clsx(
        'group rounded-lg border transition-all',
        task.status === 'done'
          ? 'border-app-border bg-app-panel/30 opacity-60'
          : 'border-app-border hover:border-app-accent bg-app-panel/50 hover:bg-app-panel'
      )}
    >
      <div className="flex items-center gap-2 p-2">
        <button
          onClick={onToggle}
          className="flex-shrink-0 hover:scale-110 transition-transform"
        >
          {STATUS_ICONS[task.status]}
        </button>

        <button
          onClick={() => setExpanded(!expanded)}
          className="flex-shrink-0 text-app-text-dim hover:text-app-text transition-colors"
        >
          {expanded ? (
            <ChevronDown className="w-4 h-4" />
          ) : (
            <ChevronRight className="w-4 h-4" />
          )}
        </button>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span
              className={clsx(
                'text-sm font-medium truncate',
                task.status === 'done' && 'line-through text-app-text-dim'
              )}
            >
              {task.title}
            </span>
            <span className={clsx('flex items-center gap-1', priorityConfig.color)}>
              {priorityConfig.icon}
              <span className="text-xs opacity-70">{priorityConfig.label}</span>
            </span>
          </div>
        </div>

        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={onEdit}
            className="p-1 rounded hover:bg-app-bg text-app-text-dim hover:text-app-text transition-colors"
            title="Edit"
          >
            <Edit3 className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={onDelete}
            className="p-1 rounded hover:bg-app-bg text-app-text-dim hover:text-red-400 transition-colors"
            title="Delete"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {expanded && task.description && (
        <div className="px-8 pb-2 text-xs text-app-text-dim">
          {task.description}
        </div>
      )}
    </div>
  );
}

interface TaskFormProps {
  task?: Task;
  onSave: (task: Omit<Task, 'id' | 'createdAt' | 'updatedAt'>) => void;
  onCancel: () => void;
}

function TaskForm({ task, onSave, onCancel }: TaskFormProps) {
  const [title, setTitle] = useState(task?.title || '');
  const [description, setDescription] = useState(task?.description || '');
  const [priority, setPriority] = useState<TaskPriority>(task?.priority || 'medium');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;

    onSave({
      title: title.trim(),
      description: description.trim() || undefined,
      priority,
      status: task?.status || 'todo',
      tags: task?.tags,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3 p-3 bg-app-bg rounded-lg border border-app-border">
      <input
        type="text"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Task title..."
        className="w-full px-3 py-2 bg-app-panel border border-app-border rounded text-sm text-app-text placeholder:text-app-text-dim focus:outline-none focus:border-app-accent"
        autoFocus
      />
      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Description (optional)..."
        rows={2}
        className="w-full px-3 py-2 bg-app-panel border border-app-border rounded text-sm text-app-text placeholder:text-app-text-dim focus:outline-none focus:border-app-accent resize-none"
      />
      <div className="flex items-center justify-between">
        <select
          value={priority}
          onChange={(e) => setPriority(e.target.value as TaskPriority)}
          className="px-3 py-1.5 bg-app-panel border border-app-border rounded text-sm text-app-text focus:outline-none focus:border-app-accent"
        >
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="px-3 py-1.5 text-sm text-app-text-dim hover:text-app-text transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            className="px-3 py-1.5 text-sm bg-app-accent text-white rounded hover:opacity-90 transition-opacity"
          >
            {task ? 'Update' : 'Add'} Task
          </button>
        </div>
      </div>
    </form>
  );
}

interface SpecFormProps {
  spec?: Spec;
  onSave: (spec: Omit<Spec, 'id' | 'createdAt' | 'updatedAt'>) => void;
  onCancel: () => void;
}

function SpecForm({ spec, onSave, onCancel }: SpecFormProps) {
  const [title, setTitle] = useState(spec?.title || '');
  const [description, setDescription] = useState(spec?.description || '');
  const [requirements, setRequirements] = useState(spec?.requirements.join('\n') || '');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;

    onSave({
      title: title.trim(),
      description: description.trim(),
      requirements: requirements.split('\n').filter((r) => r.trim()),
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3 p-3 bg-app-bg rounded-lg border border-app-border">
      <input
        type="text"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Spec title..."
        className="w-full px-3 py-2 bg-app-panel border border-app-border rounded text-sm text-app-text placeholder:text-app-text-dim focus:outline-none focus:border-app-accent"
        autoFocus
      />
      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Description..."
        rows={2}
        className="w-full px-3 py-2 bg-app-panel border border-app-border rounded text-sm text-app-text placeholder:text-app-text-dim focus:outline-none focus:border-app-accent resize-none"
      />
      <textarea
        value={requirements}
        onChange={(e) => setRequirements(e.target.value)}
        placeholder="Requirements (one per line)..."
        rows={4}
        className="w-full px-3 py-2 bg-app-panel border border-app-border rounded text-sm text-app-text placeholder:text-app-text-dim focus:outline-none focus:border-app-accent resize-none"
      />
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-1.5 text-sm text-app-text-dim hover:text-app-text transition-colors"
        >
          Cancel
        </button>
        <button
          type="submit"
          className="px-3 py-1.5 text-sm bg-app-accent text-white rounded hover:opacity-90 transition-opacity"
        >
          {spec ? 'Update' : 'Create'} Spec
        </button>
      </div>
    </form>
  );
}

// Main TaskPanel Component
export function TaskPanel() {
  const {
    tasks,
    currentSpec,
    setTasks,
    addTask,
    updateTask,
    deleteTask,
    toggleTaskStatus,
    setCurrentSpec,
    addMessage,
  } = useAgenticStore();

  const [showTaskForm, setShowTaskForm] = useState(false);
  const [showSpecForm, setShowSpecForm] = useState(false);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [editingSpec, setEditingSpec] = useState<Spec | null>(null);
  const [activeTab, setActiveTab] = useState<'spec' | 'tasks' | 'plan'>('tasks');
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['todo', 'doing']));

  const stats = useAgenticStore(selectTaskStats);

  // Load initial data
  useEffect(() => {
    async function loadData() {
      try {
        const [loadedSpec, loadedTasks] = await Promise.all([
          window.electronAPI?.loadSpec(),
          window.electronAPI?.loadTasks(),
        ]);
        if (loadedSpec) setCurrentSpec(loadedSpec);
        if (loadedTasks && loadedTasks.length > 0) {
          setTasks(loadedTasks.map((t: Task) => ({
            ...t,
            createdAt: t.createdAt || Date.now(),
            updatedAt: t.updatedAt || Date.now(),
          })));
        }
      } catch (error) {
        console.error('Error loading data:', error);
      }
    }
    loadData();
  }, [setCurrentSpec, setTasks]);

  // Save tasks when changed
  useEffect(() => {
    if (tasks.length > 0) {
      window.electronAPI?.saveTasks(tasks);
    }
  }, [tasks]);

  const handleAddTask = (task: Omit<Task, 'id' | 'createdAt' | 'updatedAt'>) => {
    if (editingTask) {
      updateTask(editingTask.id, task);
      setEditingTask(null);
    } else {
      addTask(task);
    }
    setShowTaskForm(false);
  };

  const handleSaveSpec = (spec: Omit<Spec, 'id' | 'createdAt' | 'updatedAt'>) => {
    if (editingSpec) {
      setCurrentSpec({ ...editingSpec, ...spec, updatedAt: Date.now() });
    } else {
      setCurrentSpec({
        ...spec,
        id: uuidv4(),
        createdAt: Date.now(),
        updatedAt: Date.now(),
      });
    }
    setShowSpecForm(false);
    setEditingSpec(null);
    window.electronAPI?.saveSpec({ ...currentSpec!, ...spec });
  };

  const toggleSection = (section: string) => {
    const newExpanded = new Set(expandedSections);
    if (newExpanded.has(section)) {
      newExpanded.delete(section);
    } else {
      newExpanded.add(section);
    }
    setExpandedSections(newExpanded);
  };

  const handleGenerateTasks = () => {
    if (!currentSpec) {
      addMessage({
        role: 'assistant',
        content: 'Vui lòng tạo Spec trước để tôi có thể tạo task list tự động.',
      });
      setActiveTab('spec');
      setShowSpecForm(true);
      return;
    }

    // Generate tasks from spec requirements
    const newTasks: Omit<Task, 'id' | 'createdAt' | 'updatedAt'>[] = currentSpec.requirements.map((req, idx) => ({
      title: req,
      description: `Implement requirement: ${req}`,
      status: 'todo',
      priority: idx < 2 ? 'high' : 'medium',
    }));

    newTasks.forEach((task) => addTask(task));
    
    addMessage({
      role: 'assistant',
      content: `Đã tạo ${newTasks.length} tasks từ spec "${currentSpec.title}". Các tasks đã được thêm vào danh sách.`,
    });
  };

  const groupedTasks = {
    todo: tasks.filter((t) => t.status === 'todo'),
    doing: tasks.filter((t) => t.status === 'doing'),
    done: tasks.filter((t) => t.status === 'done'),
  };

  return (
    <div className="h-full flex flex-col bg-app-sidebar">
      {/* Tab Header */}
      <div className="flex items-center border-b border-app-border">
        <button
          onClick={() => setActiveTab('spec')}
          className={clsx(
            'flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors',
            activeTab === 'spec'
              ? 'text-app-accent border-b-2 border-app-accent bg-app-panel/50'
              : 'text-app-text-dim hover:text-app-text'
          )}
        >
          <FileText className="w-3.5 h-3.5" />
          Spec
        </button>
        <button
          onClick={() => setActiveTab('tasks')}
          className={clsx(
            'flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors',
            activeTab === 'tasks'
              ? 'text-app-accent border-b-2 border-app-accent bg-app-panel/50'
              : 'text-app-text-dim hover:text-app-text'
          )}
        >
          <ListTodo className="w-3.5 h-3.5" />
          Tasks
          <span className="ml-1 px-1.5 py-0.5 text-xs bg-app-panel rounded-full">
            {stats.total}
          </span>
        </button>
        <button
          onClick={() => setActiveTab('plan')}
          className={clsx(
            'flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors',
            activeTab === 'plan'
              ? 'text-app-accent border-b-2 border-app-accent bg-app-panel/50'
              : 'text-app-text-dim hover:text-app-text'
          )}
        >
          <Layout className="w-3.5 h-3.5" />
          Plan
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {/* Spec Tab */}
        {activeTab === 'spec' && (
          <div className="p-3 space-y-3">
            {showSpecForm || editingSpec ? (
              <SpecForm
                spec={editingSpec || undefined}
                onSave={handleSaveSpec}
                onCancel={() => {
                  setShowSpecForm(false);
                  setEditingSpec(null);
                }}
              />
            ) : currentSpec ? (
              <div className="space-y-3">
                <div className="p-3 bg-app-panel rounded-lg border border-app-border">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="font-semibold text-app-text">{currentSpec.title}</h3>
                    <button
                      onClick={() => setEditingSpec(currentSpec)}
                      className="p-1 rounded hover:bg-app-bg text-app-text-dim hover:text-app-text transition-colors"
                    >
                      <Edit3 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <p className="text-sm text-app-text-dim mb-3">{currentSpec.description}</p>
                  <div className="text-xs text-app-text-dim">
                    {currentSpec.requirements.length} requirements
                  </div>
                </div>

                <div className="space-y-1">
                  <h4 className="text-xs font-semibold text-app-text-dim uppercase tracking-wider">
                    Requirements
                  </h4>
                  {currentSpec.requirements.map((req, idx) => (
                    <div key={idx} className="flex items-start gap-2 p-2 bg-app-bg rounded text-sm">
                      <span className="text-app-accent font-mono">{idx + 1}.</span>
                      <span className="text-app-text">{req}</span>
                    </div>
                  ))}
                </div>

                <button
                  onClick={handleGenerateTasks}
                  className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-app-accent text-white text-sm rounded hover:opacity-90 transition-opacity"
                >
                  <ListTodo className="w-4 h-4" />
                  Generate Tasks from Spec
                </button>
              </div>
            ) : (
              <div className="text-center py-8">
                <FileText className="w-12 h-12 mx-auto mb-3 text-app-text-dim opacity-50" />
                <p className="text-sm text-app-text-dim mb-4">No spec created yet</p>
                <button
                  onClick={() => setShowSpecForm(true)}
                  className="flex items-center justify-center gap-2 px-4 py-2 bg-app-accent text-white text-sm rounded hover:opacity-90 transition-opacity mx-auto"
                >
                  <Plus className="w-4 h-4" />
                  Create Spec
                </button>
              </div>
            )}
          </div>
        )}

        {/* Tasks Tab */}
        {activeTab === 'tasks' && (
          <div className="p-3 space-y-3">
            {/* Add Task Button */}
            {!showTaskForm && (
              <button
                onClick={() => {
                  setShowTaskForm(true);
                  setEditingTask(null);
                }}
                className="w-full flex items-center justify-center gap-2 px-3 py-2 border border-dashed border-app-border rounded-lg text-sm text-app-text-dim hover:text-app-text hover:border-app-accent transition-colors"
              >
                <Plus className="w-4 h-4" />
                Add Task
              </button>
            )}

            {/* Task Form */}
            {showTaskForm && (
              <TaskForm
                onSave={handleAddTask}
                onCancel={() => {
                  setShowTaskForm(false);
                  setEditingTask(null);
                }}
              />
            )}

            {/* Stats */}
            <div className="flex gap-2 text-xs">
              <span className="px-2 py-1 bg-red-500/20 text-red-400 rounded">
                {stats.todo} todo
              </span>
              <span className="px-2 py-1 bg-blue-500/20 text-blue-400 rounded">
                {stats.doing} doing
              </span>
              <span className="px-2 py-1 bg-green-500/20 text-green-400 rounded">
                {stats.done} done
              </span>
            </div>

            {/* Task Sections */}
            {(['todo', 'doing', 'done'] as TaskStatus[]).map((status) => (
              <div key={status} className="space-y-2">
                <button
                  onClick={() => toggleSection(status)}
                  className="flex items-center gap-2 w-full text-xs font-semibold text-app-text-dim uppercase tracking-wider hover:text-app-text transition-colors"
                >
                  {expandedSections.has(status) ? (
                    <ChevronDown className="w-3 h-3" />
                  ) : (
                    <ChevronRight className="w-3 h-3" />
                  )}
                  {status === 'todo' ? 'To Do' : status === 'doing' ? 'In Progress' : 'Done'}
                  <span className="ml-auto px-1.5 py-0.5 bg-app-panel rounded">
                    {groupedTasks[status].length}
                  </span>
                </button>

                {expandedSections.has(status) && (
                  <div className="space-y-1.5">
                    {groupedTasks[status].map((task) => (
                      <TaskItem
                        key={task.id}
                        task={task}
                        onToggle={() => toggleTaskStatus(task.id)}
                        onDelete={() => deleteTask(task.id)}
                        onEdit={() => {
                          setEditingTask(task);
                          setShowTaskForm(true);
                        }}
                      />
                    ))}
                    {groupedTasks[status].length === 0 && (
                      <div className="py-2 text-xs text-app-text-dim text-center">
                        No tasks
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Plan Tab */}
        {activeTab === 'plan' && (
          <div className="p-3">
            {currentSpec ? (
              <div className="space-y-4">
                <div className="p-3 bg-app-panel rounded-lg border border-app-border">
                  <h3 className="font-semibold text-app-text mb-2">Implementation Plan</h3>
                  <p className="text-sm text-app-text-dim">{currentSpec.title}</p>
                </div>

                <div className="space-y-3">
                  {tasks.length === 0 ? (
                    <div className="text-center py-8">
                      <Layout className="w-12 h-12 mx-auto mb-3 text-app-text-dim opacity-50" />
                      <p className="text-sm text-app-text-dim mb-4">
                        No tasks to plan. Create tasks first.
                      </p>
                    </div>
                  ) : (
                    tasks.map((task, idx) => (
                      <div
                        key={task.id}
                        className={clsx(
                          'p-3 rounded-lg border',
                          task.status === 'done'
                            ? 'bg-green-500/10 border-green-500/30'
                            : task.status === 'doing'
                            ? 'bg-blue-500/10 border-blue-500/30'
                            : 'bg-app-panel border-app-border'
                        )}
                      >
                        <div className="flex items-start gap-3">
                          <span
                            className={clsx(
                              'flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold',
                              task.status === 'done'
                                ? 'bg-green-500 text-white'
                                : 'bg-app-border text-app-text-dim'
                            )}
                          >
                            {idx + 1}
                          </span>
                          <div className="flex-1 min-w-0">
                            <div
                              className={clsx(
                                'font-medium',
                                task.status === 'done' && 'line-through text-app-text-dim'
                              )}
                            >
                              {task.title}
                            </div>
                            {task.description && (
                              <div className="text-xs text-app-text-dim mt-1">
                                {task.description}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>

                {stats.done > 0 && stats.total > 0 && (
                  <div className="mt-4">
                    <div className="flex justify-between text-xs text-app-text-dim mb-2">
                      <span>Progress</span>
                      <span>{Math.round((stats.done / stats.total) * 100)}%</span>
                    </div>
                    <div className="h-2 bg-app-panel rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-app-accent to-green-400 transition-all"
                        style={{ width: `${(stats.done / stats.total) * 100}%` }}
                      />
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-8">
                <Layout className="w-12 h-12 mx-auto mb-3 text-app-text-dim opacity-50" />
                <p className="text-sm text-app-text-dim">
                  Create a spec first to generate an implementation plan.
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
