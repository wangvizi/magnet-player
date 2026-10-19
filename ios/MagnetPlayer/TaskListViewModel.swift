import Foundation

@MainActor
final class TaskListViewModel: ObservableObject {
    @Published var tasks: [DownloadTask] = []
    @Published var errorMessage: String?
    @Published var isAdding = false

    private let api = APIClient.shared
    private var timer: Timer?

    func startPolling() {
        Task { await refresh() }
        timer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            guard let self else { return }
            Task { await self.refresh() }
        }
    }

    func stopPolling() {
        timer?.invalidate()
        timer = nil
    }

    func refresh() async {
        do {
            tasks = try await api.listTasks()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func addMagnet(_ magnet: String) async {
        let trimmed = magnet.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        isAdding = true
        defer { isAdding = false }
        do {
            _ = try await api.addMagnet(trimmed)
            await refresh()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func delete(_ gid: String) async {
        try? await api.deleteTask(gid)
        await refresh()
    }
}
