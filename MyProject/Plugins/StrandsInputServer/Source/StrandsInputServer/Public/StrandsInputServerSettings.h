#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "StrandsInputServerSettings.generated.h"

/**
 * Configurable settings for Strands Input Server.
 * Lives under Project Settings > Plugins > Strands Input Server.
 * Also configurable via INI: [/Script/StrandsInputServer.StrandsInputServerSettings]
 */
UCLASS(config=Game, defaultconfig, meta=(DisplayName="Strands Input Server"))
class STRANDSINPUTSERVER_API UStrandsInputServerSettings : public UDeveloperSettings
{
	GENERATED_BODY()
public:
	// If true, the server starts automatically at runtime (PIE and packaged).
	UPROPERTY(config, EditAnywhere, Category="Networking")
	bool bAutoStart = true;

	// TCP port to listen on (localhost only).
	UPROPERTY(config, EditAnywhere, Category="Networking", meta=(ClampMin="1024", ClampMax="65535"))
	int32 Port = 17777;

	// Default duration for move commands when not specified (seconds).
	UPROPERTY(config, EditAnywhere, Category="Control", meta=(ClampMin="0.0"))
	float DefaultMoveDuration = 0.25f;

	// Default duration for look commands when not specified (seconds).
	UPROPERTY(config, EditAnywhere, Category="Control", meta=(ClampMin="0.0"))
	float DefaultLookDuration = 0.2f;

	// Walk speed to use when sprint is disabled.
	UPROPERTY(config, EditAnywhere, Category="Character", meta=(ClampMin="0.0"))
	float NormalWalkSpeed = 600.0f;

	// Walk speed to use when sprint is enabled.
	UPROPERTY(config, EditAnywhere, Category="Character", meta=(ClampMin="0.0"))
	float SprintWalkSpeed = 1000.0f;

	// Put this settings object under the Plugins category in Project Settings.
	virtual FName GetCategoryName() const override { return TEXT("Plugins"); }
};
