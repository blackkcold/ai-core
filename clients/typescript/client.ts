/** Browser/Node fetch client. Never embed a provider API key in an application build. */
export interface ClientOptions {
  baseUrl?: string;
  token?: string;
  project?: string;
  fetchImpl?: typeof fetch;
}

export type ChatMessage = {
  role: "system" | "developer" | "user" | "assistant" | "tool";
  content: string | null;
  tool_call_id?: string;
  tool_calls?: unknown[];
};

export type ChatRequest = {
  provider: string;
  model: string;
  messages: ChatMessage[];
  max_tokens?: number;
  temperature?: number;
  tools?: unknown[];
  stream?: boolean;
};

export class AICoreClient {
  private baseUrl: string;
  private token: string;
  private project?: string;
  private fetchImpl: typeof fetch;

  constructor(options: ClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? "http://127.0.0.1:8765").replace(/\/+$/, "");
    this.token = options.token ?? "";
    this.project = options.project;
    this.fetchImpl = options.fetchImpl ?? fetch;
  }

  private headers(): Record<string, string> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (this.token) headers.Authorization = "Bearer " + this.token;
    if (this.project) headers["X-AI-Core-Project"] = this.project;
    return headers;
  }

  private async request(path: string, payload?: unknown): Promise<any> {
    if (!path.startsWith("/v1/")) throw new Error("unsupported route");
    const response = await this.fetchImpl(this.baseUrl + path, {
      method: payload === undefined ? "GET" : "POST",
      headers: this.headers(),
      body: payload === undefined ? undefined : JSON.stringify(payload),
    });
    if (!response.ok) throw new Error("AI Core HTTP " + response.status);
    return await response.json();
  }

  providers(): Promise<any> {
    return this.request("/v1/providers");
  }

  searchProviders(): Promise<any> {
    return this.request("/v1/search/providers");
  }

  models(provider: string, refresh = false): Promise<any> {
    return this.request("/v1/models?provider=" + encodeURIComponent(provider) + (refresh ? "&refresh=1" : ""));
  }

  search(query: string, options: {limit?: number; provider?: string; mode?: "free-first" | "deep"} = {}): Promise<any> {
    return this.request("/v1/tools/web_search", {query, ...options});
  }

  fetchPage(url: string): Promise<any> {
    return this.request("/v1/tools/web_fetch", {url});
  }

  chat(body: ChatRequest): Promise<any> {
    return this.request("/v1/chat/completions", {...body, stream: false});
  }

  usage(): Promise<any> {
    return this.request("/v1/usage");
  }

  /** SSE messages are normalized OpenAI-compatible chunks, not raw vendor SSE. */
  async *streamChat(body: ChatRequest): AsyncGenerator<any, void, unknown> {
    const response = await this.fetchImpl(this.baseUrl + "/v1/chat/completions", {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({...body, stream: true}),
    });
    if (!response.ok || !response.body) throw new Error("AI Core stream HTTP " + response.status);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      while (true) {
        const {value, done} = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, {stream: true}).replace(/\r\n/g, "\n");
        while (true) {
          const cut = buffer.indexOf("\n\n");
          if (cut < 0) break;
          const frame = buffer.slice(0, cut);
          buffer = buffer.slice(cut + 2);
          const json = frame.split("\n").filter(l => l.startsWith("data:"))
            .map(l => l.slice(5).trimStart()).join("\n");
          if (json === "[DONE]") return;
          if (json) {
            const chunk = JSON.parse(json);
            if (chunk.error) throw new Error(chunk.error.message ?? "stream error");
            yield chunk;
          }
        }
      }
    } finally {
      await reader.cancel().catch(() => {});
    }
  }
}
