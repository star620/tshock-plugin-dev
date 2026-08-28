using Terraria;
using TShockAPI;
using TShockAPI.Hooks;
using TerrariaApi.Server;
using static {{插件名}}.Utils;

namespace {{插件名}};

[ApiVersion(2, 1)]
public class Plugin : TerrariaPlugin
{
    #region 插件信息
    public static string PluginName => "{{插件名}}"; // 插件名称
    public override string Name => PluginName;
    public override string Author => "{{作者}}";
    public override Version Version => new({{版本号}}); // 如 1, 0, 0
    public override string Description => "{{描述}}";
    #endregion

    #region 文件路径
    public static readonly string MainPath = Path.Combine(TShock.SavePath, PluginName); // 主文件夹路径
    public static readonly string ConfigPath = Path.Combine(MainPath, "配置文件.json"); // 配置文件路径
    public static readonly string CachePath = Path.Combine(MainPath, "数据缓存.json"); // 缓存文件路径
    #endregion

    #region 注册与释放
    public Plugin(Main game) : base(game) { }

    public override void Initialize()
    {
        LoadConfig(); // 加载配置文件
        GeneralHooks.ReloadEvent += ReloadConfig; // 注册 /reload 重载
        ServerApi.Hooks.NetGreetPlayer.Register(this, OnGreetPlayer); // 玩家进服事件
        ServerApi.Hooks.ServerLeave.Register(this, OnServerLeave); // 玩家离开事件
        {{插件名}}.Commands.Register(); // 注册聊天命令（无命令可删除此行）
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            GeneralHooks.ReloadEvent -= ReloadConfig; // 注销重载
            ServerApi.Hooks.NetGreetPlayer.Deregister(this, OnGreetPlayer); // 注销进服事件
            ServerApi.Hooks.ServerLeave.Deregister(this, OnServerLeave); // 注销离服事件
        }
        base.Dispose(disposing);
    }
    #endregion

    #region 配置重载与读取
    internal static Configuration Config = new(); // 配置文件实例
    internal static CacheData Cache => Config.DataCache; // 缓存数据实例

    private static void ReloadConfig(ReloadEventArgs args)
    {
        LoadConfig(); // 重新读取配置
        args.Player.SendMessage($"[{PluginName}] 配置已重载。", color);
    }

    private static void LoadConfig()
    {
        try
        {
            if (!Directory.Exists(MainPath))
                Directory.CreateDirectory(MainPath); // 创建插件数据目录

            Config = Configuration.Read();
            Config.Write();
        }
        catch (Exception ex)
        {
            // 配置损坏时只报错不崩溃服务器
            TShock.Log.ConsoleError($"[{PluginName}] 配置文件加载失败：\n{ex.Message}");
        }
    }
    #endregion

    #region 玩家进服事件
    private void OnGreetPlayer(GreetPlayerEventArgs args)
    {
        var plr = TShock.Players[args.Who];
        if (plr is null || !plr.RealPlayer || !plr.Active || !plr.IsLoggedIn || !Config.Enabled)
            return; // 过滤：真实且已登录玩家 + 插件开关打开

        // TODO: 在此写进服逻辑（例：创建/刷新玩家缓存数据）
        Cache.GetData(plr.Name).Join = DateTime.UtcNow;
        Cache.Save();
    }
    #endregion

    #region 玩家离开服务器事件
    private void OnServerLeave(LeaveEventArgs args)
    {
        var plr = TShock.Players[args.Who];
        if (plr is null || !plr.RealPlayer || !plr.Active || !plr.IsLoggedIn || !Config.Enabled)
            return;

        // TODO: 在此写离服逻辑（例：记录离开时间/清理缓存）
        Cache.GetData(plr.Name).Leave = DateTime.UtcNow;
        Cache.Save();
    }
    #endregion
}
