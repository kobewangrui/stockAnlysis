# 美股低估筛选与 BTC 周期仪表盘

这是一个 Windows 桌面软件，用于本地查看美股低估筛选、机构目标价、市场情绪和 BTC 周期数据。

当前交付形式是 exe 安装包。普通用户安装后从桌面或开始菜单打开即可，不需要 Python、不需要 `.venv`，也不需要源码目录。软件打开后是独立桌面应用窗口，不会跳到外部浏览器。

## 功能概览

- 默认扫描 NASDAQ 股票池，并排除中国、香港、澳门相关上市公司
- 股票池最低市值可在页面手动输入，单位为“亿美元”
- 美股行情来自 NASDAQ screener 和 Yahoo Finance chart API
- 机构目标价来自 NASDAQ Analyst Research，StockAnalysis 作为备用
- BTC 当前价来自 CoinGecko
- BTC 历史节奏来自 Yahoo Finance `BTC-USD`
- 市场情绪包含 VIX、CNN Fear & Greed 或 VIX 代理、加密恐慌贪婪指数
- 前端默认 60 秒自动刷新；行情短缓存，机构目标价使用更长缓存以避免公开接口限流

## 目录结构

```text
app.py                       Flask 后端接口和数据计算逻辑
launcher.py                  Windows 桌面应用入口，启动本地服务并打开内嵌桌面窗口
templates\index.html         页面结构
static\app.js                前端交互逻辑
static\styles.css            页面样式
requirements.txt             运行依赖
requirements-build.txt       打包依赖
StockAnalysis.spec           PyInstaller 打包配置
scripts\build_exe.ps1        一键构建 exe 和安装包
packaging\install.cmd        安装包内使用的安装脚本
packaging\uninstall.cmd      安装包内使用的卸载脚本
dist\StockAnalysis.exe       便携版，可直接双击运行
dist\StockAnalysisSetup.exe  安装包，推荐交付普通用户
```

## 普通用户使用

### 安装版

交付普通用户时，只需要给这个文件：

```text
dist\StockAnalysisSetup.exe
```

用户双击安装包后会自动完成：

- 安装到 `%LOCALAPPDATA%\StockAnalysisDashboard`
- 创建桌面快捷方式 `Stock Analysis Dashboard`
- 创建开始菜单快捷方式 `Stock Analysis Dashboard`
- 创建开始菜单卸载入口 `Uninstall Stock Analysis Dashboard`
- 安装完成后自动启动软件

安装后的真实程序入口：

```text
%LOCALAPPDATA%\StockAnalysisDashboard\StockAnalysis.exe
```

使用方式：

1. 双击桌面或开始菜单的 `Stock Analysis Dashboard`。
2. 等待软件主窗口出现。
3. 在软件窗口内使用仪表盘。
4. 关闭软件窗口即可停止本地服务。

### 免安装版

临时使用或测试时，可以直接双击：

```text
dist\StockAnalysis.exe
```

这个文件不需要 Python 环境，也不需要源码目录。

### 页面筛选项

- `股票池`：留空时自动扫描 NASDAQ 股票池；填写股票代码时只扫描指定代码，例如 `AAPL,MSFT,NVDA`
- `最低市值（亿美元）`：只在 `股票池` 留空时生效，默认 `100`，表示扫描市值不低于 100 亿美元的股票
- `扫描数量`：从满足市值门槛的股票池中按市值从高到低取前 N 只，最大 500
- `自动刷新`：前端自动刷新间隔

## 开发环境

### 环境要求

- 操作系统：Windows 10/11，推荐 PowerShell
- Python：已验证 `Python 3.13.12`，建议使用 `Python 3.11+`
- 网络：需要能访问 NASDAQ、Yahoo Finance、CoinGecko、Alternative.me 等公开接口
- 端口：源码运行默认使用 `http://127.0.0.1:5000`

确认 Python 版本：

```powershell
python --version
```

如果输出版本低于 `3.11`，请先安装新版 Python，并在安装时勾选 `Add python.exe to PATH`。

### 首次源码启动

在项目目录打开 PowerShell：

```powershell
cd C:\Users\DELL\Desktop\stockAnlysis
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

看到类似下面的输出就启动成功：

```text
Running on http://127.0.0.1:5000
```

源码运行时手动打开：

```text
http://127.0.0.1:5000
```

### 日常源码启动

已经装过依赖后，只需要：

```powershell
cd C:\Users\DELL\Desktop\stockAnlysis
.\.venv\Scripts\Activate.ps1
python app.py
```

### 桌面入口调试

如果要调试安装版使用的桌面窗口入口：

```powershell
cd C:\Users\DELL\Desktop\stockAnlysis
.\.venv\Scripts\Activate.ps1
python launcher.py
```

这会启动内嵌桌面窗口，不会打开外部浏览器。

## 打包流程

每次修改以下内容后，都需要重新打包，普通用户才会拿到新版本：

- `app.py`
- `launcher.py`
- `templates`
- `static`
- `requirements.txt`
- `packaging`

在项目目录运行：

```powershell
cd C:\Users\DELL\Desktop\stockAnlysis
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_exe.ps1
```

打包脚本会自动完成：

- 创建或复用 `.venv`
- 安装 `requirements.txt`
- 安装 `requirements-build.txt`
- 使用 PyInstaller 生成 `dist\StockAnalysis.exe`
- 使用 Windows IExpress 生成 `dist\StockAnalysisSetup.exe`

构建完成后会生成：

```text
dist\StockAnalysis.exe
dist\StockAnalysisSetup.exe
```

如果只想生成便携版 exe，不生成安装包：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_exe.ps1 -SkipInstaller
```

## 验收流程

### 1. 检查产物

```powershell
Get-Item .\dist\StockAnalysis.exe, .\dist\StockAnalysisSetup.exe
```

两个文件都存在，才算构建产物完整。

### 2. 验证便携版后端服务

```powershell
$p = Start-Process -FilePath .\dist\StockAnalysis.exe -ArgumentList '--smoke-test' -Wait -PassThru
$p.ExitCode
```

输出 `0` 表示后端服务可启动。

### 3. 验证便携版桌面窗口

```powershell
$p = Start-Process -FilePath .\dist\StockAnalysis.exe -ArgumentList '--webview-smoke-test' -Wait -PassThru
$p.ExitCode
```

输出 `0` 表示内嵌桌面窗口可启动，不依赖外部浏览器。

### 4. 验证安装包完整链路

```powershell
$env:STOCK_ANALYSIS_SKIP_LAUNCH='1'
$setup = (Resolve-Path .\dist\StockAnalysisSetup.exe).Path
Start-Process -FilePath $setup -ArgumentList '/Q' -Wait
Remove-Item Env:\STOCK_ANALYSIS_SKIP_LAUNCH -ErrorAction SilentlyContinue

$appExe = Join-Path $env:LOCALAPPDATA 'StockAnalysisDashboard\StockAnalysis.exe'
Test-Path $appExe

$p1 = Start-Process -FilePath $appExe -ArgumentList '--smoke-test' -Wait -PassThru
$p1.ExitCode

$p2 = Start-Process -FilePath $appExe -ArgumentList '--webview-smoke-test' -Wait -PassThru
$p2.ExitCode
```

通过标准：

- `Test-Path $appExe` 输出 `True`
- `$p1.ExitCode` 输出 `0`
- `$p2.ExitCode` 输出 `0`

验收完成后卸载测试安装：

```powershell
$uninstall = Join-Path $env:LOCALAPPDATA 'StockAnalysisDashboard\uninstall.cmd'
Start-Process -FilePath $uninstall -Wait
```

## 发布流程

推荐发布步骤：

1. 修改源码或页面。
2. 用源码启动确认功能正常。
3. 运行 `scripts\build_exe.ps1` 重新打包。
4. 验证 `dist\StockAnalysis.exe` 的 `--smoke-test`。
5. 验证 `dist\StockAnalysis.exe` 的 `--webview-smoke-test`。
6. 安装 `dist\StockAnalysisSetup.exe` 验证快捷方式、启动行为和卸载行为。
7. 把新的 `dist\StockAnalysisSetup.exe` 发给使用者。

用户安装新版时，可以直接运行新的安装包覆盖旧版。如果遇到异常，先从开始菜单运行 `Uninstall Stock Analysis Dashboard` 卸载，再安装新版。

## 卸载说明

普通用户卸载方式：

- 开始菜单打开 `Uninstall Stock Analysis Dashboard`

手动清理路径：

```text
%LOCALAPPDATA%\StockAnalysisDashboard
```

卸载脚本会同时删除桌面快捷方式和开始菜单快捷方式。

## 评分逻辑

股票低估评分使用：

- NASDAQ screener 的市值、行业、成交量和现价
- NASDAQ Analyst Research 的机构目标价 Low / Average / High
- Buy / Hold / Sell 评级分布和分析师覆盖数量
- 目标均价相对当前价的上行空间
- 52 周高点折价、趋势偏离程度

BTC 信号使用：

- 当前 BTC/USD 价格
- 减半后天数与下轮减半倒计时
- 历史顶底节奏与周期预测
- RSI 辅助观察
- 加密市场恐慌贪婪指数

## 常见问题

如果 PowerShell 不允许激活虚拟环境或执行脚本：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

如果提示 `Address already in use` 或 `端口 5000 被占用`，说明服务可能已经在运行。关闭旧窗口后再启动，或者等待启动器自动选择 5000 附近的可用端口。

如果系统找不到 `iexpress.exe`，安装包会跳过生成，但 `dist\StockAnalysis.exe` 仍然可用。

如果杀毒软件提示未知发布者，这是因为当前 exe 没有代码签名证书。内部自用可以忽略；对外分发建议购买代码签名证书并签名。

如果用户启动后页面数据加载失败，优先检查网络是否能访问 NASDAQ、Yahoo Finance、CoinGecko、Alternative.me。

公开免费数据不等于交易所逐笔实时行情，可能存在延迟、缺失或限流。此工具用于研究和风控，不构成投资建议。
