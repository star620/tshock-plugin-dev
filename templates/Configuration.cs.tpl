using Newtonsoft.Json;
using static {{插件名}}.Plugin;

namespace {{插件名}};

internal class Configuration
{
    #region 配置项
    [JsonProperty("插件开关", Order = 0)]
    public bool Enabled { get; set; } = true;
    // TODO: 在此追加配置项，例如：
    // [JsonProperty("同步秒数", Order = 1)]
    // public int SyncCacheTime { get; set; } = 60;
    #endregion

    #region 预设默认值
    public void SetDefault()
    {
        // 需要在首次创建时写入的非默认值在此设置（有默认值的属性可留空）
    }
    #endregion

    #region 读取与写入方法
    public void Write()
    {
        string json = JsonConvert.SerializeObject(this, Formatting.Indented);
        File.WriteAllText(ConfigPath, json);
        DataCache.Save(); // 顺带保存缓存数据
    }

    public static Configuration Read()
    {
        if (!File.Exists(ConfigPath))
        {
            var cfg = new Configuration();
            cfg.SetDefault();
            cfg.Write();
            return cfg;
        }
        try
        {
            string json = File.ReadAllText(ConfigPath);
            var cfg = JsonConvert.DeserializeObject<Configuration>(json)!;
            cfg.DataCache.Load(); // 读取缓存数据
            return cfg;
        }
        catch (JsonException ex)
        {
            // 配置文件损坏时给出可读错误信息，不崩溃服务器
            throw new Exception($"配置文件解析失败，路径：{ConfigPath}\n错误：{ex.Message}", ex);
        }
    }
    #endregion

    #region 缓存数据（高频变化，分离到独立文件）
    private CacheData _dataCache = new();
    [JsonIgnore]
    public CacheData DataCache => _dataCache;
    #endregion
}
