import { ElectronAPI, GitStatus, GitInfo, CommitInfo, StorageAPI, AIAPI, TerminalAPI, SteeringAPI } from '../../electron/preload';

export interface MockElectronAPI extends ElectronAPI {
  openDirectory: jest.Mock<Promise<string | null>, []>;
  readDirectory: jest.Mock<Promise<{name: string; path: string; isDirectory: boolean}[]>, [string]>;
  readFile: jest.Mock<Promise<string>, [string]>;
  writeFile: jest.Mock<Promise<boolean>, [string, string]>;
  createFile: jest.Mock<Promise<boolean>, [string]>;
  createDirectory: jest.Mock<Promise<boolean>, [string]>;
  deleteFile: jest.Mock<Promise<boolean>, [string]>;
  gitStatus: jest.Mock<Promise<GitStatus>, []>;
  gitBranch: jest.Mock<Promise<string>, []>;
  gitCommit: jest.Mock<Promise<boolean>, [string]>;
  gitStage: jest.Mock<Promise<boolean>, [string[]]>;
  gitUnstage: jest.Mock<Promise<boolean>, [string[]]>;
  gitCheckout: jest.Mock<Promise<boolean>, [string]>;
  gitDiscard: jest.Mock<Promise<boolean>, [string[]]>;
  gitLog: jest.Mock<Promise<CommitInfo[]>, [number?]>;
  gitDiff: jest.Mock<Promise<string>, [string?]>;
  terminal: TerminalAPI;
  ai: AIAPI;
  storage: StorageAPI;
  steering: SteeringAPI;
  codeAnalyzer: {
    analyze: jest.Mock;
    getFunctions: jest.Mock;
    getImports: jest.Mock;
  };
  onFileChange: jest.Mock;
  onGitStatusChange: jest.Mock;
  showContextMenu: jest.Mock;
  minimizeWindow: jest.Mock;
  maximizeWindow: jest.Mock;
  closeWindow: jest.Mock;
  isMaximized: jest.Mock<Promise<boolean>, []>;
}

export const createMockElectronAPI = (): MockElectronAPI => ({
  openDirectory: jest.fn().mockResolvedValue(null),
  readDirectory: jest.fn().mockResolvedValue([]),
  readFile: jest.fn().mockResolvedValue(''),
  writeFile: jest.fn().mockResolvedValue(true),
  createFile: jest.fn().mockResolvedValue(true),
  createDirectory: jest.fn().mockResolvedValue(true),
  deleteFile: jest.fn().mockResolvedValue(true),
  gitStatus: jest.fn().mockResolvedValue({
    modified: [],
    staged: [],
    created: [],
    deleted: [],
    not_added: [],
    current: 'main',
    tracking: 'origin/main'
  }),
  gitBranch: jest.fn().mockResolvedValue('main'),
  gitCommit: jest.fn().mockResolvedValue(true),
  gitStage: jest.fn().mockResolvedValue(true),
  gitUnstage: jest.fn().mockResolvedValue(true),
  gitCheckout: jest.fn().mockResolvedValue(true),
  gitDiscard: jest.fn().mockResolvedValue(true),
  gitLog: jest.fn().mockResolvedValue([]),
  gitDiff: jest.fn().mockResolvedValue(''),
  terminal: {
    write: jest.fn(),
    onData: jest.fn(),
    resize: jest.fn(),
    clear: jest.fn(),
    dispose: jest.fn()
  },
  ai: {
    chat: jest.fn().mockResolvedValue({ content: 'Mock AI response', error: null }),
    isInitialized: jest.fn().mockResolvedValue(true),
    codeReview: jest.fn().mockResolvedValue('Mock code review'),
    generateCode: jest.fn().mockResolvedValue('Mock generated code'),
    explainCode: jest.fn().mockResolvedValue('Mock code explanation')
  },
  storage: {
    getWorkspace: jest.fn().mockResolvedValue(null),
    setWorkspace: jest.fn().mockResolvedValue(true),
    updateUIState: jest.fn().mockResolvedValue(true),
    updateOpenFiles: jest.fn().mockResolvedValue(true),
    getUIState: jest.fn().mockResolvedValue({ expandedFolders: [], openFiles: [] })
  },
  steering: {
    load: jest.fn().mockResolvedValue({ success: false, context: {} }),
    save: jest.fn().mockResolvedValue(true)
  },
  codeAnalyzer: {
    analyze: jest.fn().mockResolvedValue({ functions: [], imports: [], exports: [], complexity: 0, issues: [] }),
    getFunctions: jest.fn().mockResolvedValue([]),
    getImports: jest.fn().mockResolvedValue([])
  },
  onFileChange: jest.fn(),
  onGitStatusChange: jest.fn(),
  showContextMenu: jest.fn(),
  minimizeWindow: jest.fn(),
  maximizeWindow: jest.fn(),
  closeWindow: jest.fn(),
  isMaximized: jest.fn().mockResolvedValue(false)
});

export const mockAIResponses = {
  chat: {
    simple: { content: 'Hello! How can I help you today?', error: null },
    codeExplanation: { content: 'This function creates a new array by mapping over the input.', error: null },
    codeReview: { content: 'The code looks good overall. Consider adding error handling.', error: null },
    error: { content: '', error: 'API key not configured' },
  },
  codeReview: {
    noIssues: JSON.stringify({
      issues: [],
      summary: 'Code looks great!'
    }),
    withIssues: JSON.stringify({
      issues: [
        {
          type: 'QUAL',
          severity: 'warning',
          line: 5,
          message: 'Unused variable',
          suggestion: 'Remove unused variable'
        }
      ],
      summary: 'Minor issues found'
    })
  }
};

export const mockGitStatus: GitStatus = {
  modified: ['src/index.ts', 'src/utils.ts'],
  staged: ['src/index.ts'],
  created: ['src/new.ts'],
  deleted: [],
  not_added: ['src/new.ts', 'src/untracked.ts'],
  current: 'feature/test',
  tracking: 'origin/feature/test'
};

export const mockGitInfo: GitInfo = {
  isRepo: true,
  branch: 'feature/test',
  branches: ['main', 'feature/test', 'bugfix/issue'],
  status: mockGitStatus,
  remotes: ['origin']
};

export const mockCommitInfo: CommitInfo[] = [
  {
    hash: 'abc123def456',
    message: 'Initial commit',
    author: 'Test User <test@example.com>',
    date: '2024-01-15T10:30:00Z'
  },
  {
    hash: '789ghi012jkl',
    message: 'Add feature X',
    author: 'Test User <test@example.com>',
    date: '2024-01-16T14:20:00Z'
  }
];

export const mockFileTree = [
  {
    name: 'src',
    path: '/workspace/src',
    isDirectory: true,
    children: [
      {
        name: 'components',
        path: '/workspace/src/components',
        isDirectory: true,
        children: [
          { name: 'Button.tsx', path: '/workspace/src/components/Button.tsx', isDirectory: false }
        ]
      },
      { name: 'index.ts', path: '/workspace/src/index.ts', isDirectory: false }
    ]
  },
  { name: 'package.json', path: '/workspace/package.json', isDirectory: false },
  { name: 'README.md', path: '/workspace/README.md', isDirectory: false }
];

export const mockTasks = [
  {
    id: '1',
    title: 'Implement feature X',
    description: 'Add feature X to the application',
    status: 'todo' as const,
    priority: 'high' as const,
    createdAt: '2024-01-15T10:00:00Z'
  },
  {
    id: '2',
    title: 'Write tests',
    status: 'doing' as const,
    priority: 'medium' as const,
    createdAt: '2024-01-15T11:00:00Z'
  },
  {
    id: '3',
    title: 'Fix bug Y',
    status: 'done' as const,
    priority: 'high' as const,
    createdAt: '2024-01-14T09:00:00Z',
    completedAt: '2024-01-14T16:00:00Z'
  }
];

export const mockChatMessages = [
  {
    id: '1',
    role: 'user' as const,
    content: 'Hello, how are you?',
    timestamp: '2024-01-15T10:00:00Z'
  },
  {
    id: '2',
    role: 'assistant' as const,
    content: 'I am doing well, thank you for asking! How can I help you today?',
    timestamp: '2024-01-15T10:00:05Z'
  }
];
