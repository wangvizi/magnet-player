import SwiftUI

struct SettingsView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var serverURL: String = APIClient.shared.baseURL
    @State private var apiKey: String = APIClient.shared.apiKey

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("http://你的服务器IP:8000", text: $serverURL)
                        .keyboardType(.URL)
                        .autocapitalization(.none)
                        .disableAutocorrection(true)
                        .font(.system(.body, design: .monospaced))
                } header: {
                    Text("服务器地址")
                } footer: {
                    Text("填写你部署磁力服务器的那台 VPS 的地址，例如 http://1.2.3.4:8000。iPhone 需要能访问到该地址。")
                }

                Section {
                    SecureField("可选", text: $apiKey)
                        .autocapitalization(.none)
                        .disableAutocorrection(true)
                        .font(.system(.body, design: .monospaced))
                } header: {
                    Text("API Key")
                } footer: {
                    Text("部署脚本会生成一个 API Key（见部署完成时的输出）。若服务器启用了认证，这里必须填写一致才能使用。")
                }

                Section("关于") {
                    LabeledContent("版本", value: "1.0.0")
                    LabeledContent("最低系统", value: "iOS 16.0")
                }
            }
            .navigationTitle("设置")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("保存") {
                        APIClient.shared.baseURL = serverURL
                        APIClient.shared.apiKey = apiKey
                        dismiss()
                    }
                }
            }
        }
    }
}
