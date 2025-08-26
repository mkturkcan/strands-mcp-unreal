using UnrealBuildTool;

public class StrandsInputServer : ModuleRules
{
    public StrandsInputServer(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(new string[]
        {
            "Core",
            "CoreUObject",
            "Engine",
            "DeveloperSettings"
        });

        PrivateDependencyModuleNames.AddRange(new string[]
        {
            "Sockets",
            "Networking",
            "Json",
            "JsonUtilities"
        });

        // We are a runtime module
        if (Target.Type == TargetType.Server || Target.Type == TargetType.Client || Target.Type == TargetType.Game || Target.Type == TargetType.Editor)
        {
            bUseRTTI = false;
        }
    }
}
