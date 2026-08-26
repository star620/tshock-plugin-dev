using Terraria;
using TShockAPI;
using Microsoft.Xna.Framework;

namespace {{插件名}};

internal class Utils
{
    #region 颜色
    public static Color color => new(240, 250, 150); // 插件主色调
    #endregion

    #region 消息发送
    // 给单个玩家发送带插件名的消息（玩家为空时忽略）
    public static void Send(TSPlayer? plr, string text)
    {
        if (plr is null) return;
        plr.SendMessage($"[{Plugin.PluginName}] {text}", color);
    }

    // 广播给全员
    public static void Broadcast(string text)
        => TSPlayer.All.SendMessage($"[{Plugin.PluginName}] {text}", color);
    #endregion

    #region 文本格式化
    // 物品图标文本，如 [i:物品ID] / [i/s数量:物品ID]
    public static string ItemIcon(int itemID, int stack = 1)
        => stack > 1 ? $"[i/s{stack}:{itemID}]" : $"[i:{itemID}]";
    #endregion
}
