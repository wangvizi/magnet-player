import AVKit
import SwiftUI

struct PlayItem: Identifiable {
    let id = UUID()
    let gid: String
    let name: String
}

struct PlayerView: View {
    let item: PlayItem
    @Environment(\.dismiss) private var dismiss
    @State private var player: AVPlayer?
    @State private var errorMessage: String?
    @State private var statusText = "正在准备播放…"

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            if let player {
                VideoPlayer(player: player)
                    .ignoresSafeArea()
            } else if let errorMessage {
                VStack(spacing: 16) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 44))
                        .foregroundColor(.yellow)
                    Text(errorMessage)
                        .foregroundColor(.white)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 32)
                    Button("关闭") { dismiss() }
                        .buttonStyle(.borderedProminent)
                }
            } else {
                VStack(spacing: 16) {
                    ProgressView()
                        .scaleEffect(1.4)
                        .tint(.white)
                    Text(statusText)
                        .foregroundColor(.white)
                    Button("取消") { dismiss() }
                        .buttonStyle(.bordered)
                }
            }
        }
        .task { await prepare() }
    }

    private func prepare() async {
        let api = APIClient.shared
        do {
            switch try await api.play(item.gid) {
            case .ready(let streamPath):
                startPlayback(path: streamPath)
            case .generating:
                statusText = "正在转码，请稍候…"
                for _ in 0..<300 {  // 最多轮询约 10 分钟
                    try? await Task.sleep(nanoseconds: 2_000_000_000)
                    if let t = try? await api.task(item.gid), t.hlsReady {
                        startPlayback(path: "/hls/\(item.gid)/index.m3u8")
                        return
                    }
                }
                errorMessage = "转码超时，请稍后重试"
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func startPlayback(path: String) {
        let url = APIClient.shared.streamURL(for: path)
        let p = AVPlayer(url: url)
        player = p
        p.play()
    }
}
