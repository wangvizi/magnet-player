# 磁力播放器（iOS 16 + 远端服务器）

一个自部署的磁力链接播放器：**服务器**负责解析磁力、下载、转码成 HLS 流；**iOS App**（SwiftUI，最低 iOS 16）负责提交链接、查看进度、用系统播放器边播边看。

> ⚠️ 磁力/种子类播放器无法上架 App Store，只能通过**自签侧载**安装到自己的 iPhone。本项目仅供学习与技术研究，请仅播放你有权获取的内容。

---

## 架构

```
iPhone App (SwiftUI + AVPlayer)
        │  HTTP (提交磁力 / 查询进度 / 请求播放)
        ▼
远端服务器 (FastAPI)
        │
        ├─ aria2 ──── 磁力/种子下载（BT/DHT/webseed）
        └─ ffmpeg ─── 下载完成后转码为 HLS (m3u8 + ts)
                       │
        ┌──────────────┘
        ▼
   HLS 流 (AVPlayer 直接播放)
```

- 下载用 **aria2**（BT 协议 + DHT + webseed，速度快、资源占用低）。
- 转码用 **ffmpeg**：视频/音频编码兼容时直接无损封装（`-c copy`，秒级）；不兼容时转 H.264/AAC。
- 服务端 API 支持可选的 **API Key 认证**，避免公网服务器被他人滥用。

---

## 目录结构

```
magnet-player/
├── server/                 # 服务器（Python FastAPI + aria2 + ffmpeg）
│   ├── app.py              # 主程序（REST API）
│   ├── downloader.py       # aria2 封装
│   ├── streamer.py         # ffmpeg 转码
│   ├── static/index.html   # 浏览器测试页
│   ├── requirements.txt
│   ├── Dockerfile
│   └── deploy.sh           # VPS 一键部署脚本
├── ios/                    # iOS 客户端（SwiftUI）
│   ├── project.yml         # XcodeGen 工程配置
│   └── MagnetPlayer/       # 源码
└── .github/workflows/
    └── build-ipa.yml       # GitHub Actions 云端构建 IPA
```

---

## 一、部署服务器（必须部署到有公网 IP 的 VPS）

> 沙箱/本地电脑无法让 iPhone 直接访问，正式使用需要一台 VPS（阿里云/腾讯云/任意 Linux 主机）。

### 方式 A：一键脚本（推荐）

```bash
# 1. 登录你的 Ubuntu 20.04/22.04 VPS
# 2. 上传 server 目录（或 git clone 后进入 server）
cd server
sudo bash deploy.sh
```

脚本会自动安装依赖、创建 systemd 服务并启动，**最后会打印一个 API Key，请记下来**（App 设置里要用）。

### 方式 B：Docker

```bash
cd server
docker build -t magnet-player .
docker run -d --name magnet-player \
  -p 8000:8000 -p 6881:6881/tcp -p 6881:6881/udp \
  -e API_KEY=你的密钥 \
  -v /data/magnet-player:/data \
  magnet-player
```

### 防火墙要求

| 端口 | 协议 | 用途 |
|------|------|------|
| 8000 | TCP | HTTP API + HLS 流（必须放行） |
| 6881-6999 | TCP/UDP | BT 下载（建议放行，下载更快更稳） |

### 验证

浏览器打开 `http://你的服务器IP:8000`，应看到测试页，可粘贴磁力链接验证下载与播放。

---

## 二、构建 iOS App（生成 IPA）

编译 iOS 应用必须用 macOS + Xcode。两个方案：

### 方案 A：GitHub Actions 云端构建（本项目已配好）

1. 把整个仓库 push 到 GitHub。
2. 在仓库 **Settings → Secrets and variables → Actions** 添加签名相关 secret（见第三节）。
3. 进入 **Actions → Build iOS IPA → Run workflow** 触发。
4. 构建完成后，在对应 run 页面下载 **MagnetPlayer-ipa** 产物。

> 未配置签名证书时，会自动退化为「仅编译未签名 .app」，供你用 Sideloadly 自行签名（见第四节）。

### 方案 B：本地 Xcode 编译

需要一台 Mac：

```bash
brew install xcodegen
cd ios
xcodegen generate
open MagnetPlayer.xcodeproj   # 在 Xcode 里选好签名 Team 后直接 Run
```

---

## 三、Apple 签名证书（用于云端签名）

### 付费开发者账号（$99/年，推荐，IPA 有效期 1 年）

1. 登录 [developer.apple.com](https://developer.apple.com) → **Certificates, Identifiers & Profiles**。
2. **Certificates** → 创建 **Apple Distribution** 证书 → 下载 `.cer` 文件。
3. 在 Mac 上双击 `.cer` 导入钥匙串，然后在「钥匙串访问」里找到该证书，**右键 → 导出为 `.p12`**，设置一个导出密码（记作 `P12_PASSWORD`）。
4. **Identifiers** → 注册 App ID：`com.magnetplayer.app`。
5. **Devices** → 添加你 iPhone 的 UDID（见下文「获取 UDID」）。
6. **Profiles** → 创建 **Ad Hoc** 描述文件，勾选上面证书、App ID、你的设备 → 下载 `.mobileprovision`。

### 免费 Apple ID（IPA 仅 7 天有效）

步骤类似，但证书选 **Apple Development**、描述文件选 **iOS App Development**。需要每 7 天重签。

### 获取 UDID

- Mac + 数据线连 iPhone，打开 Xcode → Window → Devices and Simulators，即可看到 **Identifier（UDID）**。
- 或手机浏览器访问 `https://udid.tech` 等工具（第三方，自行判断风险）。

### 填入 GitHub Secrets

在 Mac 终端把两个文件转成 base64：

```bash
base64 -i 你的证书.p12 | pbcopy        # 粘到 BUILD_CERTIFICATE_BASE64
base64 -i 你的描述文件.mobileprovision | pbcopy  # 粘到 BUILD_PROVISION_PROFILE_BASE64
```

需要添加的 secrets：

| Secret 名 | 值 |
|-----------|-----|
| `BUILD_CERTIFICATE_BASE64` | `.p12` 文件的 base64 |
| `P12_PASSWORD` | 导出 `.p12` 时设置的密码 |
| `KEYCHAIN_PASSWORD` | 随便设一个，如 `ci-build-keychain` |
| `BUILD_PROVISION_PROFILE_BASE64` | `.mobileprovision` 的 base64 |
| `DEVELOPMENT_TEAM` | 你的 Team ID（开发者后台账号页可见，10 位） |
| `PROVISIONING_PROFILE_NAME` | 描述文件名称 |

---

## 四、把 IPA 安装到 iOS 16

| 方式 | 签名要求 | 有效期 | 说明 |
|------|----------|--------|------|
| **付费账号 + Ad Hoc** | 付费账号 | 1 年 | 最省心，可用 Apple Configurator 2 / Xcode / AltStore 安装 |
| **AltStore / Sideloadly** | 免费 Apple ID 即可 | 7 天（需重签） | 电脑上操作，Wi-Fi 同网可自动刷新 |
| **TrollStore** | 无需电脑 | 永久 | 仅支持 iOS 14.0–16.6.1 及 17.0（16.7 以上不支持） |

### Sideloadly 安装（免费账号，最通用）

1. Mac/PC 安装 [Sideloadly](https://sideloadly.io/)。
2. 数据线连 iPhone，把 IPA 拖入 Sideloadly。
3. 填你的 Apple ID（免费账号即可），点 Start。
4. 首次安装需在 iPhone 上信任证书：**设置 → 通用 → VPN 与设备管理 → 信任**。

### AltStore 安装

1. 电脑安装 [AltServer](https://altstore.io/)，安装 AltStore 到 iPhone。
2. 把 IPA 传到手机，用 AltStore 打开安装。
3. 7 天后在 AltStore 里点 Refresh 续签（需与 AltServer 同 Wi-Fi）。

### TrollStore（若你的 iOS 是 15.0–16.6.1）

先通过漏洞安装 TrollStore，之后直接打开 IPA 即可永久安装，无需电脑与证书。

---

## 五、使用

1. 打开 App → 右上角**设置** → 填服务器地址和 API Key。
2. 首页粘贴 `magnet:?xt=urn:btih:...` 磁力链接 → 添加。
3. 等待下载进度条走完 → 点**播放**。
4. 服务器转码完成后自动开始播放（大文件首次转码需要几分钟）。

---

## 六、常见问题

**Q：一直卡在「下载中 0%」，速度是 0？**
磁力解析元数据需要 DHT/peer，请确认 VPS 已放行 6881-6999 端口，且该资源有可用做种者。冷门资源可能无源。

**Q：播放时报「下载未完成」？**
部分视频需完整下载后才能转码播放，请等进度到 100%。

**Q：为什么免费账号只能装 7 天？**
Apple 对免费 Apple ID 的个人开发签名限制为 7 天，这是系统限制。要长期使用建议付费账号，或用 TrollStore（若系统版本支持）。

**Q：能边下边播吗？**
当前版本为「下载完成后播放」。边下边播需要顺序下载 + 实时切片，将在后续版本加入。

---

## 免责声明

本项目仅用于技术学习与研究。请勿使用本项目下载、传播或播放任何侵权内容；使用者需遵守所在国家/地区的法律法规，并对自己的行为负责。
