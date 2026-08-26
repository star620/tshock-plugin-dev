using Newtonsoft.Json;
using System.Collections.Concurrent;
using static {{插件名}}.Plugin;

namespace {{插件名}};

internal class CacheData
{
    #region 玩家数据缓存
    [JsonProperty("玩家数据", Order = 0)]
    public ConcurrentDictionary<string, PlayerCache> Players { get; set; } = new();

    public class PlayerCache
    {
        [JsonProperty("管理员", Order = 0)]
        public bool Admin { get; set; } = false;
        [JsonProperty("进服时间", Order = 1)]
        public DateTime? Join { get; set; } = null;
        [JsonProperty("出服时间", Order = 2)]
        public DateTime? Leave { get; set; } = null;
        // TODO: 在此追加缓存字段
    }
    #endregion

    #region 数据管理方法
    // 取玩家缓存，不存在则自动创建
    public PlayerCache GetData(string name) => Players.GetOrAdd(name, _ => new PlayerCache());

    // 清空缓存（不传参清全部，传名清单个）
    public void Clear(string? name = null)
    {
        if (string.IsNullOrEmpty(name))
            Players.Clear();
        else if (Players.ContainsKey(name))
            Players.TryRemove(name, out _);
    }
    #endregion

    #region 读取与写入缓存方法
    public void Save()
    {
        string json = JsonConvert.SerializeObject(this, Formatting.Indented);
        File.WriteAllText(CachePath, json);
    }

    public void Load()
    {
        if (!File.Exists(CachePath))
        {
            Save();
            return;
        }
        string jsonContent = File.ReadAllText(CachePath);
        var cache = JsonConvert.DeserializeObject<CacheData>(jsonContent)!;
        Players = cache.Players ?? new();
    }
    #endregion
}
