/// <reference types="vite/client" />

interface Window {
  electronAPI?: {
    openDirectory: () => Promise<string | undefined>;
    readDirectory: (path: string) => Promise<Array<{
      name: string;
      path: string;
      isDirectory: boolean;
    }>>;
    readFile: (path: string) => Promise<string | null>;
    writeFile: (path: string, content: string) => Promise<boolean>;
    createFile: (path: string) => Promise<boolean>;
    createDirectory: (path: string) => Promise<boolean>;
    deleteFile: (path: string) => Promise<boolean>;
    rename: (oldPath: string, newPath: string) => Promise<boolean>;
  };
}
