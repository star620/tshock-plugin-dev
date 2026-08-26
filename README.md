# TShock 插件开发 Skill（tshock-plugin-dev）

面向 **Terraria 1.4.5+ / TShock** 的插件全流程开发技能。从需求采集、环境探测、参考源码获取，到分层 TDD 编码、代码审查、编译、部署与服务器加载验证，一站式完成 TShock 插件开发。兼顾高级开发者（使用本地版本化源码）与小白（零本地环境，全自动准备）。

## 功能特性

- **需求采集（必答问卷）**：版本门禁校验，防止为无对应 NuGet 包的 Terraria 版本编写插件
- **动态版本解析**：客户端 ↔ 服务端 ↔ TShock ↔ .NET TFM 四元组每轮开发必做
- **分层参考源码**：本地源码 > 插件仓库 > NuGet 包 > 自动下载，四层策略
- **分层 TDD**：纯逻辑先写失败测试再实现；粘合层编译 + 服务器加载验证
- **交付前终审**：方法名、缺陷、多余字段、整体质量四项终审，问题全部修复才可交付
- **中文注释规范**：统一 `//` 单行注释，禁止 `/// <summary>` XML 文档注释
- **分类封装**：命令/配置/缓存/工具/业务逻辑各归其类，每类 ≤ 400 行

## 工作流（十阶段）

| 阶段 | 内容 |
|---|---|
| Phase 0 | 需求采集（必答问卷 + 版本门禁） |
| Phase 1 | 环境与版本探测（动态解析四元组） |
| Phase 2 | 参考源码获取（L1 本地 / L2 仓库 / L3 NuGet / L4 自动下载） |
| Phase 3 | 项目脚手架（csproj + 分类结构 + 测试项目） |
| Phase 4 | 分层 TDD 实现（Red-Green-Refactor） |
| Phase 5 | 代码审查（开发中自查：线程安全/权限/异常/兼容性） |
| Phase 6 | 编译验证（build 无错误无警告 + test 全绿） |
| Phase 7 | 部署与加载验证（ServerPlugins + 重启检查日志） |
| Phase 8 | 终审代码审查（方法名/缺陷/多余字段/整体质量） |
| Phase 9 | 交付（DLL + README + 单测报告 + 审查结论） |

## 安装方法

1. 将本仓库的 `tshock-plugin-dev` 文件夹放入你的 AI 助手 Skills 目录：
   - TRAE：`<用户目录>\.trae-cn\skills\`
   - Claude Code：`<项目>\.claude\skills\`
2. 重启 AI 助手，向它发起 TShock 插件开发需求即可自动调用。

## 目录结构

```
tshock-plugin-dev/
├── SKILL.md              # 技能主入口（工作流 + 硬性规则）
├── README.md             # 本项目说明
├── LICENSE               # MIT License
├── references/           # 阶段参考文档（00-11）
│   ├── 00-需求采集.md        # 必答问卷与需求引导
│   ├── 01-环境检测与自动准备.md
│   ├── 02-版本解析与兼容性.md
│   ├── 03-参考源码获取.md    # 四层参考源策略
│   ├── 04-项目脚手架.md
│   ├── 05-代码组织规范.md    # 分类封装 + 注释规范
│   ├── 06-TShockAPI速查.md
│   ├── 07-分层TDD.md
│   ├── 08-代码审查清单.md
│   ├── 09-编译部署加载验证.md
│   ├── 10-排错手册.md
│   └── 11-终审代码审查.md    # 交付前终审清单
├── templates/            # 插件工程模板
│   ├── plugin.csproj.tpl
│   ├── Plugin.cs.tpl
│   ├── Configuration.cs.tpl
│   ├── CacheData.cs.tpl
│   ├── Utils.cs.tpl
│   ├── Commands.cs.tpl
│   ├── README.md.tpl
│   └── 需求问卷.md
└── mcp-server/           # 配套 MCP 工具（可选，未安装时 skill 照常工作）
    ├── server.py             # MCP 入口（stdio）
    ├── README.md             # 安装与 TRAE 注册方式
    └── tools/                # version_resolver / build_check / load_log_check / fetch_tshock_source
```

## 技术要求

- Terraria 1.4.5+（含 1.4.5.6）
- TShock 6.0.0+（当前稳定版 6.1.0，对应 Terraria 1.4.5.6）
- .NET SDK（编译环境，自动检测/安装）

## 许可证

MIT License
