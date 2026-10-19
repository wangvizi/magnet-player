import Foundation

/// 下载任务（与服务器 /api/tasks 返回字段一一对应）。
struct DownloadTask: Identifiable, Codable {
    let gid: String
    var name: String
    var status: String
    var totalLength: Int64
    var completedLength: Int64
    var progress: Double
    var downloadSpeed: Int64
    var numSeeders: Int
    var error: String
    var hlsReady: Bool
    var hlsGenerating: Bool
    var createdAt: Double

    var id: String { gid }

    var isComplete: Bool { status == "complete" }
    var isError: Bool { status == "error" || status == "removed" }

    var displayName: String {
        let n = name.trimmingCharacters(in: .whitespacesAndNewlines)
        return n.isEmpty ? gid : n
    }
}

/// /play 接口返回。
struct PlayResponse: Decodable {
    let streamPath: String
    let name: String

    enum CodingKeys: String, CodingKey {
        case streamPath = "stream_path"
        case name
    }
}

/// 服务器错误信息（409 等）。
struct ServerError: Decodable {
    let error: String
}

enum ByteFormat {
    static func string(_ bytes: Int64) -> String {
        guard bytes > 0 else { return "0 B" }
        let units = ["B", "KB", "MB", "GB", "TB"]
        var value = Double(bytes)
        var i = 0
        while value >= 1024 && i < units.count - 1 {
            value /= 1024
            i += 1
        }
        return i == 0 ? "\(Int(value)) B" : String(format: "%.1f %@", value, units[i])
    }

    static func speed(_ bytesPerSec: Int64) -> String {
        string(bytesPerSec) + "/s"
    }
}
