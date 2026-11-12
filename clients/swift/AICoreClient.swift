import Foundation

/// Native Swift client for macOS/iOS. Configure per-project tokens at runtime.
public struct AICoreClient {
    public let baseURL: URL
    public let token: String
    public let project: String?

    public init(baseURL: URL = URL(string: "http://127.0.0.1:8765")!,
                token: String = "", project: String? = nil) {
        self.baseURL = baseURL
        self.token = token
        self.project = project
    }

    private func request(_ path: String, method: String = "GET",
                         query: [URLQueryItem] = [], body: [String: Any]? = nil) async throws -> Data {
        guard path.hasPrefix("/v1/") else { throw URLError(.badURL) }
        var url = baseURL
        for component in path.split(separator: "/") {
            url.appendPathComponent(String(component))
        }
        guard var components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
            throw URLError(.badURL)
        }
        if !query.isEmpty { components.queryItems = query }
        guard let url = components.url else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if !token.isEmpty {
            request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        }
        if let project {
            request.setValue(project, forHTTPHeaderField: "X-AI-Core-Project")
        }
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
        return data
    }

    public func providers() async throws -> Data {
        try await request("/v1/providers")
    }

    public func models(provider: String, refresh: Bool = false) async throws -> Data {
        try await request("/v1/models", query: [
            URLQueryItem(name: "provider", value: provider),
            URLQueryItem(name: "refresh", value: refresh ? "1" : "0")
        ])
    }

    public func search(_ query: String, limit: Int = 6) async throws -> Data {
        try await request("/v1/tools/web_search", method: "POST",
                          body: ["query": query, "limit": limit])
    }

    public func fetchPage(_ url: String) async throws -> Data {
        try await request("/v1/tools/web_fetch", method: "POST", body: ["url": url])
    }

    public func chat(provider: String, model: String,
                     messages: [[String: Any]]) async throws -> Data {
        try await request("/v1/chat/completions", method: "POST",
                          body: ["provider": provider, "model": model, "messages": messages])
    }

    public func usage() async throws -> Data {
        try await request("/v1/usage")
    }
}
