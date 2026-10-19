import Foundation

enum APIError: Error, LocalizedError {
    case invalidURL
    case badStatus(Int, String)
    case serverError(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "服务器地址无效，请在设置中检查"
        case .badStatus(let code, let msg):
            return "请求失败（\(code)）：\(msg)"
        case .serverError(let msg):
            return msg
        }
    }
}

/// 与服务器通信的客户端。
final class APIClient {
    static let shared = APIClient()

    private let serverKey = "serverURL"
    private let apiKeyKey = "apiKey"

    var baseURL: String {
        get {
            let v = UserDefaults.standard.string(forKey: serverKey) ?? ""
            return v.isEmpty ? "http://192.168.1.100:8000" : v
        }
        set { UserDefaults.standard.set(newValue, forKey: serverKey) }
    }

    var apiKey: String {
        get { UserDefaults.standard.string(forKey: apiKeyKey) ?? "" }
        set { UserDefaults.standard.set(newValue, forKey: apiKeyKey) }
    }

    private let session: URLSession = {
        let cfg = URLSessionConfiguration.default
        cfg.timeoutIntervalForRequest = 20
        return URLSession(configuration: cfg)
    }()

    // MARK: - 请求构造

    private func makeURL(_ path: String) throws -> URL {
        var base = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        if base.hasSuffix("/") { base.removeLast() }
        guard let url = URL(string: base + path) else { throw APIError.invalidURL }
        return url
    }

    private func makeRequest(_ path: String, method: String, body: Data? = nil) throws -> URLRequest {
        var req = URLRequest(url: try makeURL(path))
        req.httpMethod = method
        let key = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
        if !key.isEmpty {
            req.setValue(key, forHTTPHeaderField: "X-API-Key")
        }
        if let body {
            req.httpBody = body
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        return req
    }

    // MARK: - 接口

    func addMagnet(_ magnet: String) async throws -> DownloadTask {
        let body = try JSONSerialization.data(withJSONObject: ["magnet": magnet])
        return try await send(makeRequest("/api/task", method: "POST", body: body))
    }

    func listTasks() async throws -> [DownloadTask] {
        try await send(makeRequest("/api/tasks", method: "GET"))
    }

    func task(_ gid: String) async throws -> DownloadTask {
        try await send(makeRequest("/api/task/\(gid)", method: "GET"))
    }

    enum PlayResult {
        case ready(streamPath: String)
        case generating
    }

    func play(_ gid: String) async throws -> PlayResult {
        let (data, resp) = try await session.data(for: makeRequest("/api/task/\(gid)/play", method: "POST"))
        guard let http = resp as? HTTPURLResponse else { throw APIError.badStatus(-1, "无响应") }
        switch http.statusCode {
        case 200:
            let r = try JSONDecoder().decode(PlayResponse.self, from: data)
            return .ready(streamPath: r.streamPath)
        case 202:
            return .generating
        case 409:
            let obj = try? JSONDecoder().decode(ServerError.self, from: data)
            throw APIError.serverError(obj?.error ?? "下载未完成")
        default:
            throw APIError.badStatus(http.statusCode, String(data: data, encoding: .utf8) ?? "")
        }
    }

    func deleteTask(_ gid: String) async throws {
        let (_, resp) = try await session.data(for: makeRequest("/api/task/\(gid)", method: "DELETE"))
        guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw APIError.badStatus((resp as? HTTPURLResponse)?.statusCode ?? -1, "删除失败")
        }
    }

    func streamURL(for path: String) -> URL {
        var base = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        if base.hasSuffix("/") { base.removeLast() }
        return URL(string: base + path) ?? URL(string: "http://localhost")!
    }

    // MARK: - 通用

    private func send<T: Decodable>(_ req: URLRequest) async throws -> T {
        let (data, resp) = try await session.data(for: req)
        guard let http = resp as? HTTPURLResponse else {
            throw APIError.badStatus(-1, "无响应")
        }
        guard (200..<300).contains(http.statusCode) else {
            let msg = String(data: data, encoding: .utf8) ?? ""
            throw APIError.badStatus(http.statusCode, msg)
        }
        return try JSONDecoder().decode(T.self, from: data)
    }
}
