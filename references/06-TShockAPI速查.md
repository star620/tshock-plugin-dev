# 06 TShockAPI 速查

> 注意：API 随 TShock 版本变化。**写代码前务必对照 L1/L3 参考源核对签名**，本速查为常用模式，非权威签名来源。

## 插件主类

```csharp
using Terraria;
using TShockAPI;
using TerrariaApi.Server;

namespace {{插件名}};

[ApiVersion(2, 1)]                          // API 版本号，勿改
public class Plugin : TerrariaPlugin        // 必须继承 TerrariaPlugin
{
    public override string Name => "插件名";
    public override string Author => "作者";
    public override Version Version => new(1, 0, 0);
    public override string Description => "描述";

    public Plugin(Main game) : base(game) { }

    public override void Initialize() { /* 注册事件/命令 */ }

    protected override void Dispose(bool disposing)
    {
        if (disposing) { /* 注销事件/命令 */ }
        base.Dispose(disposing);
    }
}
```

## 聊天命令注册

```csharp
using TShockAPI;
// 在 Initialize() 或静态构造函数中：
Commands.ChatCommands.Add(new Command(
    "myplugin.admin",       // 权限名（可多个：new List<string>{"a","b"}）
    CmdHandler,             // 处理方法 void CmdHandler(CommandArgs args)
    "mycmd",                // 命令名（玩家输入 /mycmd）
    "help"                  // 帮助文本（可省略）
));
```

命令处理方法：
```csharp
private void CmdHandler(CommandArgs args)
{
    // args.Player    触发玩家（TSPlayer）
    // args.Parameters 参数列表（除命令名外）
    if (args.Parameters.Count < 1) { args.Player.SendInfoMessage("用法：/mycmd <参数>"); return; }
    if (!args.Player.HasPermission("myplugin.admin")) return; // 双重校验可选
    // ... 业务逻辑
}
```

## 常用事件钩子

| 事件 | 注册方式 | 用途 |
|---|---|---|
| 服务器更新（每 tick） | `ServerApi.Hooks.GameUpdate.Register(this, OnUpdate)` | 定时逻辑、每秒累计 |
| 玩家进服 | `ServerApi.Hooks.NetGreetPlayer.Register(this, OnGreet)` | 进服初始化 |
| 玩家离开 | `ServerApi.Hooks.ServerLeave.Register(this, OnLeave)` | 离服清理 |
| 服务器重载 | `GeneralHooks.ReloadEvent += ReloadConfig;`（`TShockAPI.Hooks`） | 配置文件重载 |
| 玩家数据包 | `GetDataHandlers.PlayerUpdate.Register(this.OnPlayerUpdate)` | 拦截/响应玩家动作 |

## 玩家与服务器对象

```csharp
TSPlayer plr = TShock.Players[args.Who];   // 按索引取玩家（可能为 null）
plr.Name          // 玩家名
plr.RealPlayer    // 是否真实玩家（非消息/测试）
plr.IsLoggedIn    // 是否已登录
plr.Active        // 是否在游戏中
plr.Group.HasPermission("perm")  // 权限判断
plr.IP            // IP
plr.TPlayer       // 底层 Terraria Player

plr.SendMessage("文本", Color);   // 发消息给单个玩家
TSPlayer.All.SendMessage("文本", Color); // 广播全员
TShock.Utils.GetActivePlayerCount()      // 在线人数
TShock.Config.Settings.MaxSlots          // 服务器上限
```

## 配置/数据文件路径约定

```csharp
public static readonly string MainPath = Path.Combine(TShock.SavePath, 插件名); // tshock/插件名/
public static readonly string ConfigPath = Path.Combine(MainPath, "配置文件.json");
public static readonly string CachePath = Path.Combine(MainPath, "数据缓存.json");
```

## 常用技巧
- 消息颜色标签：`[c/FFFFFF:文本]`；物品图标：`[i:物品ID]`、`[i/s数量:物品ID]`
- 游戏进度：`Main.hardMode`、`NPC.downedMoonlord` 等静态字段（`Terraria` 命名空间）
- 异步任务用 `Task.Run`，回主线程用 `Main.QueueMainThreadAction` 或 TaskScheduler 回调

## 核对 API 的正确姿势
1. 优先查用户本地源码夹（L1）中对应类文件
2. 无源码时用 NuGet 包内程序集反射/XML 文档（L3）
3. 最后才参考本速查（可能滞后于版本）
