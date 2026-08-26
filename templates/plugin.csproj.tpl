<Project Sdk="Microsoft.NET.Sdk">

  <PropertyGroup>
    <TargetFramework>{{TargetFramework}}</TargetFramework> <!-- 由版本解析确定，如 net9.0 -->
    <RootNamespace>$(MSBuildProjectName)</RootNamespace>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
    <GenerateAssemblyInfo>false</GenerateAssemblyInfo>
    <AssemblyName>{{插件名}}</AssemblyName>
  </PropertyGroup>

  <ItemGroup>
    <!-- TShock 官方 NuGet 包，版本 = 目标 TShock 版本 -->
    <PackageReference Include="TShock" Version="{{TShockVersion}}" />
  </ItemGroup>

</Project>
