#pragma once

#include "CoreMinimal.h"
#include "Subsystems/TickableWorldSubsystem.h"
#include "StrandsInputServerSubsystem.generated.h"

class FSocket;
class FTcpListener;
class FIPv4Endpoint;

USTRUCT()
struct FStrandsMoveAction
{
	GENERATED_BODY()
	FVector2D Axis = FVector2D::ZeroVector; // X=Forward, Y=Right
	double EndTime = 0.0;
};

USTRUCT()
struct FStrandsLookAction
{
	GENERATED_BODY()
	FVector2D Rate = FVector2D::ZeroVector; // X=YawRate (deg/sec), Y=PitchRate (deg/sec)
	double EndTime = 0.0;
};

USTRUCT()
struct FStrandsClientState
{
	GENERATED_BODY()
	FSocket* Socket = nullptr;
	FString Pending;
};

/**
 * Tickable world subsystem that runs a localhost TCP JSON command server.
 * JSON lines protocol:
 *  { "cmd": "move", "forward": 1.0, "right": 0.0, "duration": 0.25 }
 *  { "cmd": "look", "yawRate": 0.5, "pitchRate": 0.0, "duration": 0.2 }
 *  { "cmd": "jump" }
 *  { "cmd": "sprint", "enabled": true }
 */
UCLASS()
class STRANDSINPUTSERVER_API UStrandsInputServerSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	// UWorldSubsystem
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	// UTickableWorldSubsystem
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UStrandsInputServerSubsystem, STATGROUP_Tickables); }
	virtual bool IsTickableWhenPaused() const override { return true; }

	// Control
	bool StartServer();
	void StopServer();
	bool IsRunning() const { return bRunning; }

private:
	// Networking
	bool HandleConnectionAccepted(FSocket* InSocket, const FIPv4Endpoint& InEndpoint);
	void PollClients(float DeltaSeconds);
	void ProcessLine(const FString& Line);

	// Control
	void ApplyScheduledActions(float DeltaSeconds);
	void ApplySprintIfPending();

private:
	TUniquePtr<FTcpListener> Listener;
	TArray<FStrandsClientState> Clients;
	FThreadSafeBool bRunning = false;

	// Actions
	TArray<FStrandsMoveAction> MoveActions;
	TArray<FStrandsLookAction> LookActions;
	int32 PendingJumpCount = 0;
	TOptional<bool> PendingSprintEnabled;

	// Cached settings (snapshotted at Initialize)
	bool bAutoStart = true;
	int32 Port = 17777;
	float DefaultMoveDuration = 0.25f;
	float DefaultLookDuration = 0.2f;
	float NormalWalkSpeed = 600.0f;
	float SprintWalkSpeed = 1000.0f;
};
