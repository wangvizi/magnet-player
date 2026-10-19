import SwiftUI

struct ContentView: View {
    @StateObject private var vm = TaskListViewModel()
    @State private var magnetInput = ""
    @State private var showSettings = false
    @State private var playItem: PlayItem?

    var body: some View {
        List {
            Section {
                HStack(spacing: 8) {
                    TextField("粘贴 magnet: 磁力链接", text: $magnetInput)
                        .font(.system(.footnote, design: .monospaced))
                        .autocapitalization(.none)
                        .disableAutocorrection(true)
                    Button {
                        let m = magnetInput
                        magnetInput = ""
                        Task { await vm.addMagnet(m) }
                    } label: {
                        if vm.isAdding {
                            ProgressView()
                        } else {
                            Text("添加")
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(vm.isAdding || trimmed.isEmpty)
                }
                .padding(.vertical, 2)
            } header: {
                Text("磁力链接")
            } footer: {
                Text("服务器：\(APIClient.shared.baseURL)")
            }

            Section("下载任务") {
                if vm.tasks.isEmpty {
                    Text("暂无任务")
                        .foregroundColor(.secondary)
                }
                ForEach(vm.tasks) { task in
                    TaskRow(task: task) {
                        Task { await vm.delete(task.gid) }
                    } onPlay: {
                        playItem = PlayItem(gid: task.gid, name: task.displayName)
                    }
                }
            }
        }
        .navigationTitle("磁力播放器")
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button {
                    showSettings = true
                } label: {
                    Image(systemName: "gearshape")
                }
            }
        }
        .refreshable {
            await vm.refresh()
        }
        .fullScreenCover(item: $playItem) { item in
            PlayerView(item: item)
        }
        .sheet(isPresented: $showSettings) {
            SettingsView()
        }
        .alert("提示", isPresented: Binding(
            get: { vm.errorMessage != nil },
            set: { if !$0 { vm.errorMessage = nil } }
        )) {
            Button("好", role: .cancel) {}
        } message: {
            Text(vm.errorMessage ?? "")
        }
        .onAppear { vm.startPolling() }
        .onDisappear { vm.stopPolling() }
    }

    private var trimmed: String {
        magnetInput.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

struct TaskRow: View {
    let task: DownloadTask
    let onDelete: () -> Void
    let onPlay: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(task.displayName)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
                Spacer()
                statusBadge
            }

            ProgressView(value: task.progress)
                .progressViewStyle(.linear)

            HStack {
                Text(metaText)
                    .font(.caption2)
                    .foregroundColor(.secondary)
                Spacer()
                if task.isComplete {
                    Button("播放") { onPlay() }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                }
                Button(role: .destructive) { onDelete() } label: {
                    Image(systemName: "trash")
                }
                .buttonStyle(.borderless)
                .controlSize(.small)
            }
        }
        .padding(.vertical, 4)
    }

    private var statusBadge: some View {
        Group {
            if task.isComplete {
                Label("完成", systemImage: "checkmark.circle.fill")
                    .foregroundColor(.green)
            } else if task.isError {
                Label("出错", systemImage: "xmark.circle.fill")
                    .foregroundColor(.red)
            } else {
                Text(String(format: "%.1f%%", task.progress * 100))
                    .foregroundColor(.secondary)
            }
        }
        .font(.caption)
    }

    private var metaText: String {
        if task.isError {
            return task.error.isEmpty ? "下载失败" : task.error
        }
        let size = "\(ByteFormat.string(task.completedLength)) / \(ByteFormat.string(task.totalLength))"
        if task.isComplete {
            return size
        }
        return "\(size) · \(ByteFormat.speed(task.downloadSpeed)) · \(task.numSeeders) 源"
    }
}
