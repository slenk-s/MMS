# MMS 物料管理系统

> 车间物料管理系统，支持本地离线缓存、多车间数据同步、固定资产管理、硬件集成（指纹/NFC），以及 FTP 自动更新。

## 系统架构

```
┌─────────────────────────────────────────────────┐
│           MMS-Main.exe（桌面端）                  │
│  PySide6 界面 · 本地 SQLite 缓存 · 数据同步引擎    │
└──────────┬──────────────────────────┬───────────┘
           │                          │
     ┌─────▼──────┐          ┌───────▼───────┐
     │  MySQL 数据库 │          │ MMS-WebServices│
     │  (主数据源)  │          │  FastAPI 查询  │
     └────────────┘          └───────────────┘
                               │
                        ┌──────▼──────┐
                        │  产线查询页面  │
                        │  /api 接口  │
                        └────────────┘
```

## 技术栈

| 组件       | 技术                              |
| ---------- | --------------------------------- |
| 桌面端     | Python 3.11 · PySide6 (Qt6)      |
| Web 服务   | FastAPI · HTTPS                   |
| 数据库     | MySQL (主库) · SQLite (本地缓存)  |
| 打包       | PyInstaller 6.16.0               |
| 性能优化   | Cython (pyd/)                     |
| 更新机制   | FTP 自动下载 + 独立更新程序         |
| 硬件支持   | 串口指纹仪 · NFC 读卡器            |
| 国际化     | 中文 / 西班牙语                    |

## 目录结构

```
mms_823/
├── client/                # 桌面端应用源码
│   ├── main.py            # 应用入口，主窗口
│   ├── MMS-Update.py      # 独立更新程序（PyInstaller onefile）
│   ├── config.py          # 应用配置管理
│   ├── mysql_client.py    # MySQL 连接封装
│   ├── local_db.py        # 本地 SQLite 缓存
│   ├── sync_engine.py     # 离线/在线数据同步引擎
│   ├── network_monitor.py # 网络连通性监测
│   ├── logger.py          # 日志工具
│   ├── build_exe.py       # 打包脚本（生成 MMS-Main/Update/WebServices）
│   │
│   ├── views/             # 界面视图
│   │   ├── login_view.py         # 登录
│   │   ├── register_view.py      # 注册
│   │   ├── inventory_detail_view.py  # 库存明细
│   │   ├── asset_view.py         # 固定资产
│   │   ├── user_manage_view.py   # 用户管理
│   │   └── config_view.py        # 系统配置
│   │
│   ├── widgets/           # 自定义组件
│   │   ├── navigation.py         # 导航栏
│   │   ├── data_table.py         # 数据表格
│   │   ├── shelf_grid_view.py    # 货架网格
│   │   ├── zoomable_image_view.py# 可缩放图片
│   │   ├── toast.py              # 提示消息
│   │   └── sync_status_bar.py    # 同步状态栏 + 版本检查
│   │
│   ├── utils/             # 工具模块
│   │   ├── updater.py            # FTP 自动更新
│   │   ├── ftp_config.py         # FTP 配置
│   │   ├── credential_manager.py # 凭据管理（加密存储）
│   │   ├── app_config.py         # 应用配置
│   │   ├── excel_exporter.py     # Excel 导出
│   │   ├── excel_image_extractor.py # Excel 图片提取
│   │   ├── ui_settings.py        # UI 偏好设置
│   │   ├── theme.py              # 主题配色
│   │   ├── helpers.py            # 通用工具
│   │   └── dialogs.py            # 对话框组件
│   │
│   ├── hardware/          # 硬件接口
│   │   ├── base.py               # 基类
│   │   ├── fingerprint_reader.py # 指纹仪
│   │   └── nfc_reader.py         # NFC 读卡器
│   │
│   ├── pyd/               # Cython 编译扩展
│   │   ├── app_config.py
│   │   ├── credential_manager.py
│   │   └── mysql_client.py
│   │
│   ├── web_/              # FastAPI Web 查询服务
│   │   ├── app.py                # 应用入口 + API Key 认证
│   │   ├── service.py            # 查询服务
│   │   ├── run.py                # 运行入口
│   │   ├── database.py           # 数据库连接
│   │   ├── schemas.py            # 数据模型
│   │   └── routes/query.py       # 查询路由
│   │
│   ├── i18n/              # 国际化
│   │   ├── manager.py
│   │   ├── storage.py
│   │   └── lang/{zh_cn.py, es_es.py}
│   │
│   └── Image/             # 应用资源图片
│
├── MySQL_/                # 数据库建表脚本
│   ├── init.sql / init_clean.sql    # 完整初始化
│   ├── 01~06_MMS_*.sql             # 分模块建表
│   └── 07_v4306_add_workshop.sql   # 车间扩展迁移
│
├── build_web/             # Web 服务打包输出
├── config.ini             # 配置（数据库、FTP、硬件等）
├── config_backups/        # 配置自动备份
├── tests/                 # 测试脚本
│   ├── upload_update.py   # 打包并上传到 FTP
│   └── test_update.py     # 更新流程测试
└── version.txt            # 当前版本号（数字，如 4305）
```

## 配置说明

编辑 `config.ini`：

| 节        | 说明                 |
| --------- | -------------------- |
| `[mysql]` | 数据库连接（密码加密存储）|
| `[app]`   | 运行模式：online / semi_offline / offline |
| `[web_query]` | Web 查询服务配置、API Key |
| `[serial]` | 串口硬件（指纹仪/NFC）配置 |
| `[update]` | FTP 更新服务器配置        |
| `[workshops]` | 车间列表及当前车间        |

## 运行模式

| 模式             | 说明                                      |
| ---------------- | ----------------------------------------- |
| `online`         | 实时连接 MySQL，所有操作直连数据库          |
| `semi_offline`   | 本地缓存为主，定期与服务器同步             |
| `offline`        | 完全离线，仅使用本地 SQLite 缓存          |

## 自动更新机制

登录后自动检查 FTP 服务器最新版本号（仅连接对比，不下载文件）：

- **有新版本**：右下角红底白字加粗，显示 `4305 --> 4306`
- **无新版本**：右下角灰底白字，显示 `4306`

手动点击"手动更新"时下载 `update.zip` → 验证 → `MMS-Update.exe` 解压替换 → 重启。

## 开发 & 打包

```bash
# 安装依赖
pip install PySide6 Cython pymysql fastapi uvicorn

# 编译 Cython 扩展
python client/pyd/setup.py build_ext --inplace

# 打包（生成 dist/MMS-Main/）
python client/build_exe.py
```

打包产物：
- `MMS-Main.exe` — 主程序（窗口模式）
- `MMS-WebServices.exe` — Web 查询服务（控制台模式）
- `MMS-Update.exe` — 独立更新程序（单文件）

## 数据库初始化

```bash
mysql -u root -p < MySQL_/init.sql
```

或执行分模块脚本 `MySQL_/01_MMS_*.sql` ~ `06_MMS_*.sql`。

## 测试更新流程

```bash
# 打包并上传到 FTP
python tests/upload_update.py

# 测试更新流程（下载→验证→解压，不重启）
python tests/test_update.py
```

## 版本记录

| 版本  | 日期       | 说明                        |
| ----- | ---------- | --------------------------- |
| 4306  | 2025-08-25 | 多车间扩展（workshop 字段） |
| 4305  | —          | 版本检查线程修复、FTP 更新增强 |