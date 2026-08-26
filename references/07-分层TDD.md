# 07 分层 TDD（测试策略）

> 分层原则：**纯逻辑用 xunit 先红后绿；依赖游戏运行时的粘合层用编译+服务器加载验证。** 不追求对粘合层做单测（Terraria 静态状态无法脱离服务器运行），但必须保证编译通过 + 服务器加载无报错。

## 可测性设计（写代码前先这样拆）

| 层 | 特征 | 验证方式 |
|---|---|---|
| 纯逻辑层 | 不触碰 `Main.*`、`TShock.*`、`TShock.Players` 等运行时静态状态；依赖通过参数/构造传入 | **xunit 单测（先红后绿）** |
| 粘合层 | 事件/命令方法，读取玩家、服务器状态 | 编译 + 服务器加载验证 |

示例：物品掉落概率计算 → 纯类 `DropCalculator.Calculate(items, luck)` 可单测；把它包装进事件处理函数 → 粘合层。

## 测试项目搭建

```xml
<!-- tests/{{插件名}}.Tests.csproj -->
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>{{TargetFramework}}</TargetFramework>
    <IsPackable>false</IsPackable>
    <Nullable>enable</Nullable>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.*" />
    <PackageReference Include="xunit" Version="2.*" />
    <PackageReference Include="xunit.runner.visualstudio" Version="2.*" />
    <PackageReference Include="TShock" Version="{{TShockVersion}}" /> <!-- 与被测项目同一版本 -->
  </ItemGroup>
  <ItemGroup>
    <ProjectReference Include="..\{{插件名}}.csproj" />
  </ItemGroup>
</Project>
```

测试可引用 `TShock` 包（类型可用），但被测代码若碰运行时静态状态会在测试中失败——这正是分层拆分的意义。

## Red-Green-Refactor（铁律）

1. **RED**：先写一个最小失败测试，描述期望行为
   ```csharp
   [Fact]
   public void 满血时ShouldNot开启无敌()
   {
       // 期望：CalculateGodMode(生命=满) == false
   }
   ```
   运行 `dotnet test`，确认**因功能缺失而失败**（不是语法错）
2. **GREEN**：写最少代码让测试通过，再跑 `dotnet test` 确认全绿
3. **REFACTOR**：清理重复/命名，保持测试绿
4. 下一个行为 → 重复

## 边界与错误也要测

- 空输入、负数、越界、重复调用
- 配置缺失/损坏 JSON 的读取结果
- 对每个新方法：能测的必测，测不了的说明原因

## 本 skill 的自检标准

- 每个纯逻辑方法有对应测试，且**亲眼看过它先失败再通过**
- `dotnet test` 全绿、输出无警告
- 粘合层代码全部编译通过，并在 Phase 7 服务器加载验证
