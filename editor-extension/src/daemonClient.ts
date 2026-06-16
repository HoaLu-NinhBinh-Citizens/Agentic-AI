// JSON-RPC 2.0 client over stdio with LSP-style Content-Length framing —
// the exact wire format the aircore daemon speaks (see editor-core/src/ipc.rs).

import { ChildProcessWithoutNullStreams, spawn } from "child_process";

type Pending = {
  resolve: (value: any) => void;
  reject: (err: Error) => void;
};

export class DaemonClient {
  private proc: ChildProcessWithoutNullStreams | undefined;
  private nextId = 1;
  private pending = new Map<number, Pending>();
  private buffer = Buffer.alloc(0);

  constructor(
    private readonly binaryPath: string,
    private readonly onLog?: (line: string) => void
  ) {}

  start(): void {
    this.proc = spawn(this.binaryPath, [], { stdio: ["pipe", "pipe", "pipe"] });
    this.proc.stdout.on("data", (chunk: Buffer) => this.onData(chunk));
    this.proc.stderr.on("data", (chunk: Buffer) =>
      this.onLog?.(chunk.toString("utf8").trimEnd())
    );
    this.proc.on("exit", (code) => {
      const err = new Error(`aircore exited with code ${code}`);
      for (const p of this.pending.values()) p.reject(err);
      this.pending.clear();
    });
  }

  stop(): void {
    // Best-effort graceful shutdown, then kill.
    this.notify("shutdown", {});
    this.proc?.kill();
    this.proc = undefined;
  }

  /** Send a request and await its response. */
  request<T = any>(method: string, params: unknown): Promise<T> {
    if (!this.proc) return Promise.reject(new Error("daemon not started"));
    const id = this.nextId++;
    const body = JSON.stringify({ jsonrpc: "2.0", id, method, params });
    const promise = new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
    });
    this.write(body);
    return promise;
  }

  /** Fire-and-forget notification (no id, no response). */
  notify(method: string, params: unknown): void {
    if (!this.proc) return;
    this.write(JSON.stringify({ jsonrpc: "2.0", method, params }));
  }

  private write(body: string): void {
    const payload = Buffer.from(body, "utf8");
    const header = Buffer.from(`Content-Length: ${payload.length}\r\n\r\n`, "ascii");
    this.proc!.stdin.write(Buffer.concat([header, payload]));
  }

  // Incremental framed-message parser: headers terminated by \r\n\r\n, then
  // exactly Content-Length bytes of body. Handles partial/coalesced chunks.
  private onData(chunk: Buffer): void {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    for (;;) {
      const sep = this.buffer.indexOf("\r\n\r\n");
      if (sep === -1) return;
      const header = this.buffer.slice(0, sep).toString("ascii");
      const match = /content-length:\s*(\d+)/i.exec(header);
      if (!match) {
        // Unparseable header; drop it to resync.
        this.buffer = this.buffer.slice(sep + 4);
        continue;
      }
      const len = parseInt(match[1], 10);
      const start = sep + 4;
      if (this.buffer.length < start + len) return; // body not fully arrived
      const body = this.buffer.slice(start, start + len).toString("utf8");
      this.buffer = this.buffer.slice(start + len);
      this.dispatch(body);
    }
  }

  private dispatch(body: string): void {
    let msg: any;
    try {
      msg = JSON.parse(body);
    } catch {
      return;
    }
    if (typeof msg.id !== "number") return; // notifications: none expected inbound
    const pending = this.pending.get(msg.id);
    if (!pending) return;
    this.pending.delete(msg.id);
    if (msg.error) {
      pending.reject(new Error(msg.error.message ?? "rpc error"));
    } else {
      pending.resolve(msg.result);
    }
  }
}
