using TShockAPI;
using static {{插件名}}.Plugin;

namespace {{插件名}};

internal class Commands
{
    #region 命令注册
    // 在 Plugin.Initialize() 中调用：{{插件名}}.Commands.Register();
    public static void Register()
    {
        // 语法：Commands.ChatCommands.Add(new Command(权限, 处理函数, "命令名") { HelpText = "帮助文本" });
        // 注意：Command 构造器的 params string[] 参数全部是「命令别名」，没有帮助文本参数；
        // 帮助文本必须用对象初始化器设置，否则会被注册成多余的命令别名。
        TShockAPI.Commands.ChatCommands.Add(new Command(
            "{{插件名}}.example",   // 权限名
            Example,                // 处理方法
            "example")              // 命令名（玩家输入 /example）
        {
            HelpText = "示例命令"    // 帮助文本（对象初始化器设置，非构造器参数）
        });
    }
    #endregion

    #region 示例命令
    private static void Example(CommandArgs args)
    {
        var plr = args.Player;
        if (!plr.HasPermission("{{插件名}}.example"))
        {
            plr.SendErrorMessage("你没有权限使用此命令。");
            return;
        }

        // args.Parameters 是除命令名外的参数列表
        plr.SendSuccessMessage($"[示例] 参数数量：{args.Parameters.Count}");
    }
    #endregion
}
