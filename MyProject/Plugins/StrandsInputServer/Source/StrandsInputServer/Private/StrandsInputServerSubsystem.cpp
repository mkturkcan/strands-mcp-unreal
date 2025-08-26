#include "StrandsInputServerSubsystem.h"
#include "StrandsInputServerSettings.h"

#include "Sockets.h"
#include "SocketSubsystem.h"
#include "IPAddress.h"
#include "Common/TcpListener.h"
#include "Interfaces/IPv4/IPv4Endpoint.h"

#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"

#include "Async/Async.h"
#include "Misc/ScopeLock.h"
#include "HAL/PlatformTime.h"

#include "Json.h"
#include "JsonUtilities.h"
#include "HighResScreenshot.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "HAL/FileManager.h"
#include "Components/CapsuleComponent.h"

void UStrandsInputServerSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);

	// Snapshot settings
	const UStrandsInputServerSettings* Settings = GetDefault<UStrandsInputServerSettings>();
	if (Settings)
	{
		bAutoStart = Settings->bAutoStart;
		Port = Settings->Port;
		DefaultMoveDuration = Settings->DefaultMoveDuration;
		DefaultLookDuration = Settings->DefaultLookDuration;
		NormalWalkSpeed = Settings->NormalWalkSpeed;
		SprintWalkSpeed = Settings->SprintWalkSpeed;
	}

	if (bAutoStart)
	{
		if (UWorld* W = GetWorld())
		{
			if (W->IsGameWorld())
			{
				StartServer();
			}
			else
			{
				UE_LOG(LogTemp, Log, TEXT("StrandsInputServer: Skipping auto-start in non-game world (%s)"), *W->GetMapName());
			}
		}
	}
}

void UStrandsInputServerSubsystem::Deinitialize()
{
	StopServer();

	Super::Deinitialize();
}

bool UStrandsInputServerSubsystem::StartServer()
{
	if (bRunning || Listener.IsValid())
	{
		return true;
	}

	FIPv4Endpoint Endpoint(FIPv4Address::InternalLoopback, Port);

	// Create listener
	Listener = MakeUnique<FTcpListener>(Endpoint, FTimespan::FromMilliseconds(10));
	if (!Listener.IsValid())
	{
		UE_LOG(LogTemp, Error, TEXT("StrandsInputServer: Failed to create TCP listener on 127.0.0.1:%d"), Port);
		return false;
	}

	// Bind accept callback - runs on listener thread; enqueue registration on game thread
	Listener->OnConnectionAccepted().BindLambda([this](FSocket* InSocket, const FIPv4Endpoint& InEndpoint)
	{
		if (!InSocket)
		{
			return false;
		}

		InSocket->SetNonBlocking(true);
		InSocket->SetNoDelay(true);

		TWeakObjectPtr<UStrandsInputServerSubsystem> WeakThis(this);
		AsyncTask(ENamedThreads::GameThread, [WeakThis, InSocket]()
		{
			if (!WeakThis.IsValid())
			{
				// If subsystem is gone, close and destroy socket
				ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(InSocket);
				return;
			}

			UStrandsInputServerSubsystem* Self = WeakThis.Get();
			FStrandsClientState NewClient;
			NewClient.Socket = InSocket;
			Self->Clients.Add(MoveTemp(NewClient));
			UE_LOG(LogTemp, Log, TEXT("StrandsInputServer: Client connected."));
			FStrandsClientState& NewRef = Self->Clients.Last();
			Self->DrainClient(NewRef);
		});

		return true;
	});

	bRunning = true;
	UE_LOG(LogTemp, Log, TEXT("StrandsInputServer: Listening on 127.0.0.1:%d"), Port);
	return true;
}

void UStrandsInputServerSubsystem::StopServer()
{
	bRunning = false;

	// Close and destroy all client sockets
	for (FStrandsClientState& C : Clients)
	{
		if (C.Socket)
		{
			C.Socket->Close();
			ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(C.Socket);
			C.Socket = nullptr;
		}
	}
	Clients.Empty();

	// Destroy listener
	if (Listener.IsValid())
	{
		Listener.Reset();
	}

	UE_LOG(LogTemp, Log, TEXT("StrandsInputServer: Stopped."));
}

void UStrandsInputServerSubsystem::Tick(float DeltaTime)
{
	if (bRunning)
	{
		PollClients(DeltaTime);
	}

	ApplyScheduledActions(DeltaTime);
	ApplySprintIfPending();
}

bool UStrandsInputServerSubsystem::HandleConnectionAccepted(FSocket* InSocket, const FIPv4Endpoint& InEndpoint)
{
	// Not used (we bind a lambda), but keep implementation to match signature if needed.
	return true;
}

static void Strands_SplitLines(FString& Accumulator, TArray<FString>& OutLines)
{
	int32 NewlineIndex;
	while (Accumulator.FindChar(TEXT('\n'), NewlineIndex))
	{
		FString Line = Accumulator.Left(NewlineIndex);
		Accumulator.RemoveAt(0, NewlineIndex + 1, EAllowShrinking::No);
		Line.TrimStartAndEndInline();
		if (!Line.IsEmpty())
		{
			// Strip optional trailing \r
			if (Line.Len() > 0 && Line[Line.Len() - 1] == TEXT('\r'))
			{
				Line.RemoveAt(Line.Len() - 1, 1, EAllowShrinking::No);
			}
			OutLines.Add(MoveTemp(Line));
		}
	}
}

void UStrandsInputServerSubsystem::DrainClient(FStrandsClientState& Client)
{
	if (!Client.Socket) return;

	uint32 PendingSize = 0;
	while (Client.Socket->HasPendingData(PendingSize) && PendingSize > 0)
	{
		const uint32 ToRead = FMath::Min(PendingSize, (uint32)65536);
		TArray<uint8> Buffer;
		Buffer.SetNumUninitialized(ToRead);

		int32 ActuallyRead = 0;
		if (Client.Socket->Recv(Buffer.GetData(), Buffer.Num(), ActuallyRead, ESocketReceiveFlags::None) && ActuallyRead > 0)
		{
			// Assume ASCII/UTF-8 JSON lines; append bytes to string
			FString Chunk;
			Chunk.Reserve(ActuallyRead);
			for (int32 b = 0; b < ActuallyRead; ++b)
			{
				Chunk.AppendChar((TCHAR)Buffer[b]);
			}

			Client.Pending += Chunk;

			// Extract complete lines
			TArray<FString> Lines;
			Strands_SplitLines(Client.Pending, Lines);
			for (FString& Line : Lines)
			{
				ProcessLine(Line);
			}
		}
		else
		{
			break;
		}
	}
}

void UStrandsInputServerSubsystem::PollClients(float DeltaSeconds)
{
	// Iterate backwards so we can remove disconnected clients
	for (int32 i = Clients.Num() - 1; i >= 0; --i)
	{
		FStrandsClientState& Client = Clients[i];
		if (!Client.Socket)
		{
			Clients.RemoveAtSwap(i);
			continue;
		}

		// Read all pending data FIRST, even if the peer closed after sending
		uint32 PendingSize = 0;
		while (Client.Socket->HasPendingData(PendingSize) && PendingSize > 0)
		{
			const uint32 ToRead = FMath::Min(PendingSize, (uint32)65536);
			TArray<uint8> Buffer;
			Buffer.SetNumUninitialized(ToRead);

			int32 ActuallyRead = 0;
			if (Client.Socket->Recv(Buffer.GetData(), Buffer.Num(), ActuallyRead, ESocketReceiveFlags::None) && ActuallyRead > 0)
			{
				// Assume ASCII/UTF-8 JSON lines; append bytes to string
				FString Chunk;
				Chunk.Reserve(ActuallyRead);
				for (int32 b = 0; b < ActuallyRead; ++b)
				{
					Chunk.AppendChar((TCHAR)Buffer[b]);
				}

				Client.Pending += Chunk;

				// Extract complete lines
				TArray<FString> Lines;
				Strands_SplitLines(Client.Pending, Lines);
				for (FString& Line : Lines)
				{
					ProcessLine(Line);
				}
			}
			else
			{
				break;
			}
		}

		// After attempting to drain any pending data, remove sockets that are no longer connected
		ESocketConnectionState ConnState = Client.Socket->GetConnectionState();
		if (ConnState != SCS_Connected)
		{
			Client.Socket->Close();
			ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(Client.Socket);
			Client.Socket = nullptr;
			Clients.RemoveAtSwap(i);
			UE_LOG(LogTemp, Log, TEXT("StrandsInputServer: Client disconnected."));
			continue;
		}
	}
}

void UStrandsInputServerSubsystem::ProcessLine(const FString& Line)
{
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Line);
	TSharedPtr<FJsonObject> Obj;
	if (!FJsonSerializer::Deserialize(Reader, Obj) || !Obj.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("StrandsInputServer: Failed to parse JSON: %s"), *Line);
		return;
	}

	const FString Cmd = Obj->GetStringField(TEXT("cmd"));
	UE_LOG(LogTemp, Log, TEXT("StrandsInputServer: Received cmd '%s'"), *Cmd);

	const double Now = FPlatformTime::Seconds();

	if (Cmd.Equals(TEXT("move"), ESearchCase::IgnoreCase))
	{
		double Forward = 0.0;
		double Right = 0.0;
		double Duration = DefaultMoveDuration;

		if (Obj->HasTypedField<EJson::Number>(TEXT("forward"))) Forward = Obj->GetNumberField(TEXT("forward"));
		if (Obj->HasTypedField<EJson::Number>(TEXT("right"))) Right = Obj->GetNumberField(TEXT("right"));
		if (Obj->HasTypedField<EJson::Number>(TEXT("duration"))) Duration = Obj->GetNumberField(TEXT("duration"));

		FStrandsMoveAction Action;
		Action.Axis = FVector2D((float)Forward, (float)Right);
		Action.EndTime = Now + FMath::Max(0.0, Duration);
		MoveActions.Add(MoveTemp(Action));
	}
	else if (Cmd.Equals(TEXT("look"), ESearchCase::IgnoreCase))
	{
		double YawRate = 0.0;
		double PitchRate = 0.0;
		double Duration = DefaultLookDuration;

		if (Obj->HasTypedField<EJson::Number>(TEXT("yawRate"))) YawRate = Obj->GetNumberField(TEXT("yawRate"));
		if (Obj->HasTypedField<EJson::Number>(TEXT("pitchRate"))) PitchRate = Obj->GetNumberField(TEXT("pitchRate"));
		if (Obj->HasTypedField<EJson::Number>(TEXT("duration"))) Duration = Obj->GetNumberField(TEXT("duration"));

		FStrandsLookAction Action;
		Action.Rate = FVector2D((float)YawRate, (float)PitchRate); // degrees/sec
		Action.EndTime = Now + FMath::Max(0.0, Duration);
		LookActions.Add(MoveTemp(Action));
	}
	else if (Cmd.Equals(TEXT("jump"), ESearchCase::IgnoreCase))
	{
		PendingJumpCount += 1;
	}
	else if (Cmd.Equals(TEXT("sprint"), ESearchCase::IgnoreCase))
	{
		bool bEnabled = false;
		if (Obj->HasField(TEXT("enabled")))
		{
			if (Obj->TryGetBoolField(TEXT("enabled"), bEnabled))
			{
				PendingSprintEnabled = bEnabled;
			}
		}
	}
	else if (Cmd.Equals(TEXT("screenshot"), ESearchCase::IgnoreCase))
	{
		FString OutPath = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("AutoScreenshot.png"));
		bool bShowUI = false;
		if (Obj->HasTypedField<EJson::String>(TEXT("path")))
		{
			OutPath = Obj->GetStringField(TEXT("path"));
		}
		if (Obj->HasTypedField<EJson::Boolean>(TEXT("showUI")))
		{
			bShowUI = Obj->GetBoolField(TEXT("showUI"));
		}

		FScreenshotRequest::RequestScreenshot(OutPath, bShowUI, /*bAddFilenameSuffix*/ false);
		UE_LOG(LogTemp, Log, TEXT("StrandsInputServer: Requested screenshot -> %s (showUI=%s)"), *OutPath, bShowUI ? TEXT("true") : TEXT("false"));
	}
	else if (Cmd.Equals(TEXT("state"), ESearchCase::IgnoreCase))
	{
		FString OutPath = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("WorldState/agent_state.json"));
		if (Obj->HasTypedField<EJson::String>(TEXT("path")))
		{
			OutPath = Obj->GetStringField(TEXT("path"));
		}
		WriteWorldStateToFile(OutPath);
		UE_LOG(LogTemp, Log, TEXT("StrandsInputServer: Wrote state -> %s"), *OutPath);
	}
	else
	{
		UE_LOG(LogTemp, Warning, TEXT("StrandsInputServer: Unknown cmd '%s'"), *Cmd);
	}
}

static ACharacter* Strands_GetControlledCharacter(UWorld* World)
{
	if (!World) return nullptr;
	APlayerController* PC = World->GetFirstPlayerController();
	if (!PC) return nullptr;
	APawn* Pawn = PC->GetPawn();
	return Pawn ? Cast<ACharacter>(Pawn) : nullptr;
}

static APawn* Strands_GetControlledPawn(UWorld* World)
{
	if (!World) return nullptr;
	APlayerController* PC = World->GetFirstPlayerController();
	if (!PC) return nullptr;
	return PC->GetPawn();
}

void UStrandsInputServerSubsystem::ApplyScheduledActions(float DeltaSeconds)
{
	const double Now = FPlatformTime::Seconds();

	// Sum active move actions, remove expired
	FVector2D MoveAxis(0.f, 0.f);
	for (int32 i = MoveActions.Num() - 1; i >= 0; --i)
	{
		if (MoveActions[i].EndTime <= Now)
		{
			MoveActions.RemoveAtSwap(i);
			continue;
		}
		MoveAxis += MoveActions[i].Axis;
	}
	MoveAxis.X = FMath::Clamp(MoveAxis.X, -1.f, 1.f);
	MoveAxis.Y = FMath::Clamp(MoveAxis.Y, -1.f, 1.f);

	// Sum active look actions, remove expired (rates are deg/sec)
	FVector2D LookRate(0.f, 0.f);
	for (int32 i = LookActions.Num() - 1; i >= 0; --i)
	{
		if (LookActions[i].EndTime <= Now)
		{
			LookActions.RemoveAtSwap(i);
			continue;
		}
		LookRate += LookActions[i].Rate;
	}

	// Apply to current controlled pawn/character
	UE_LOG(LogTemp, Log, TEXT("StrandsInputServer: Axes Move=(%0.2f,%0.2f) LookRate=(%0.2f,%0.2f) PendingJump=%d"), MoveAxis.X, MoveAxis.Y, LookRate.X, LookRate.Y, PendingJumpCount);
	ACharacter* Character = Strands_GetControlledCharacter(GetWorld());
	APawn* Pawn = Character ? (APawn*)Character : Strands_GetControlledPawn(GetWorld());
	if (!Character)
	{
		UE_LOG(LogTemp, Log, TEXT("StrandsInputServer: No ACharacter possessed."));
	}
	if (!Pawn)
	{
		UE_LOG(LogTemp, Log, TEXT("StrandsInputServer: No Pawn/Controller."));
	}

	if (Character)
	{
		if (!MoveAxis.IsNearlyZero())
		{
			Character->AddMovementInput(Character->GetActorForwardVector(), MoveAxis.X);
			Character->AddMovementInput(Character->GetActorRightVector(), MoveAxis.Y);
		}

		if (PendingJumpCount > 0)
		{
			UE_LOG(LogTemp, Log, TEXT("StrandsInputServer: Jumping %d time(s)"), PendingJumpCount);
			for (int32 i = 0; i < PendingJumpCount; ++i)
			{
				Character->Jump();
			}
			PendingJumpCount = 0;
		}
	}

	if (Pawn)
	{
		if (!LookRate.IsNearlyZero())
		{
			// Convert deg/sec to per-tick input
			const float YawDelta = LookRate.X * DeltaSeconds;
			const float PitchDelta = LookRate.Y * DeltaSeconds;
			Pawn->AddControllerYawInput(YawDelta);
			Pawn->AddControllerPitchInput(PitchDelta);
		}
	}
}

void UStrandsInputServerSubsystem::ApplySprintIfPending()
{
	if (!PendingSprintEnabled.IsSet())
	{
		return;
	}

	ACharacter* Character = Strands_GetControlledCharacter(GetWorld());
	if (Character)
	{
		if (UCharacterMovementComponent* MoveComp = Character->GetCharacterMovement())
		{
			MoveComp->MaxWalkSpeed = PendingSprintEnabled.GetValue() ? SprintWalkSpeed : NormalWalkSpeed;
		}
	}

	PendingSprintEnabled.Reset();
}

void UStrandsInputServerSubsystem::BuildWorldState(TSharedRef<FJsonObject>& Out, UWorld* World) const
{
	if (!World) { return; }

	ACharacter* Character = Strands_GetControlledCharacter(World);
	APawn* Pawn = Character ? static_cast<APawn*>(Character) : Strands_GetControlledPawn(World);

	const double Now = FPlatformTime::Seconds();
	Out->SetNumberField(TEXT("ts"), Now);

	// Pawn info
	TSharedPtr<FJsonObject> PawnObj = MakeShared<FJsonObject>();
	if (Pawn)
	{
		PawnObj->SetStringField(TEXT("name"), Pawn->GetName());
		PawnObj->SetStringField(TEXT("class"), Pawn->GetClass() ? Pawn->GetClass()->GetName() : TEXT("Unknown"));
		Out->SetObjectField(TEXT("pawn"), PawnObj);

		const FVector Loc = Pawn->GetActorLocation();
		TArray<TSharedPtr<FJsonValue>> PosArray;
		PosArray.Add(MakeShared<FJsonValueNumber>(Loc.X));
		PosArray.Add(MakeShared<FJsonValueNumber>(Loc.Y));
		PosArray.Add(MakeShared<FJsonValueNumber>(Loc.Z));
		Out->SetArrayField(TEXT("pos"), PosArray);

		const FRotator Rot = Pawn->GetActorRotation();
		TSharedPtr<FJsonObject> RotObj = MakeShared<FJsonObject>();
		RotObj->SetNumberField(TEXT("yaw"), Rot.Yaw);
		RotObj->SetNumberField(TEXT("pitch"), Rot.Pitch);
		RotObj->SetNumberField(TEXT("roll"), Rot.Roll);
		Out->SetObjectField(TEXT("rot"), RotObj);

		const FVector Vel = Pawn->GetVelocity();
		TArray<TSharedPtr<FJsonValue>> VelArray;
		VelArray.Add(MakeShared<FJsonValueNumber>(Vel.X));
		VelArray.Add(MakeShared<FJsonValueNumber>(Vel.Y));
		VelArray.Add(MakeShared<FJsonValueNumber>(Vel.Z));
		Out->SetArrayField(TEXT("vel"), VelArray);
		Out->SetNumberField(TEXT("speed"), Vel.Length());
	}
	else
	{
		Out->SetObjectField(TEXT("pawn"), PawnObj);
	}

	// Movement
	TSharedPtr<FJsonObject> MoveObj = MakeShared<FJsonObject>();
	if (Character)
	{
		if (UCharacterMovementComponent* MoveComp = Character->GetCharacterMovement())
		{
			FString ModeStr = TEXT("None");
			switch (MoveComp->MovementMode)
			{
			case MOVE_Walking: ModeStr = TEXT("Walking"); break;
			case MOVE_NavWalking: ModeStr = TEXT("NavWalking"); break;
			case MOVE_Falling: ModeStr = TEXT("Falling"); break;
			case MOVE_Swimming: ModeStr = TEXT("Swimming"); break;
			case MOVE_Flying: ModeStr = TEXT("Flying"); break;
			case MOVE_Custom: ModeStr = TEXT("Custom"); break;
			default: break;
			}
			MoveObj->SetStringField(TEXT("mode"), ModeStr);
			MoveObj->SetBoolField(TEXT("isFalling"), MoveComp->IsFalling());
			MoveObj->SetBoolField(TEXT("isCrouched"), Character->bIsCrouched);
		}
	}
	Out->SetObjectField(TEXT("move"), MoveObj);

	// Traces
	TSharedPtr<FJsonObject> TraceObj = MakeShared<FJsonObject>();
	float ForwardKnee = 0.f, ForwardWaist = 0.f, ForwardChest = 0.f;
	float LeftWaist = 0.f, RightWaist = 0.f;
	float DownDist = 0.f;

	if (Pawn)
	{
		const FVector BaseLoc = Pawn->GetActorLocation();
		const FVector Fwd = Pawn->GetActorForwardVector();
		const FVector Right = Pawn->GetActorRightVector();
		const FVector Up = Pawn->GetActorUpVector();

		float HalfHeight = 88.f;
		if (Character)
		{
			if (const UCapsuleComponent* Capsule = Character->GetCapsuleComponent())
			{
				HalfHeight = Capsule->GetScaledCapsuleHalfHeight();
			}
		}

		auto TraceDist = [World](const FVector& Start, const FVector& Dir, float Length, const AActor* Ignore)->float
		{
			FHitResult Hit;
			FCollisionQueryParams Params(SCENE_QUERY_STAT(StrandsStateTrace), false, Ignore);
			const bool bHit = World->LineTraceSingleByChannel(Hit, Start, Start + Dir * Length, ECollisionChannel::ECC_Visibility, Params);
			return bHit ? Hit.Distance : Length;
		};

		const float RangeFwd = 200.f;
		const float RangeSide = 200.f;
		const float RangeDown = 300.f;
		const float Knee = 50.f;
		const float Waist = 90.f;
		const float Chest = 140.f;

		const FVector KneeStart = BaseLoc + Up * (Knee - HalfHeight);
		const FVector WaistStart = BaseLoc + Up * (Waist - HalfHeight);
		const FVector ChestStart = BaseLoc + Up * (Chest - HalfHeight);

		ForwardKnee = TraceDist(KneeStart, Fwd, RangeFwd, Pawn);
		ForwardWaist = TraceDist(WaistStart, Fwd, RangeFwd, Pawn);
		ForwardChest = TraceDist(ChestStart, Fwd, RangeFwd, Pawn);

		LeftWaist = TraceDist(WaistStart, -Right, RangeSide, Pawn);
		RightWaist = TraceDist(WaistStart, Right, RangeSide, Pawn);

		DownDist = TraceDist(BaseLoc, -Up, RangeDown, Pawn);
	}

	TSharedPtr<FJsonObject> ForwardObj = MakeShared<FJsonObject>();
	ForwardObj->SetNumberField(TEXT("knee"), ForwardKnee);
	ForwardObj->SetNumberField(TEXT("waist"), ForwardWaist);
	ForwardObj->SetNumberField(TEXT("chest"), ForwardChest);
	TraceObj->SetObjectField(TEXT("forward"), ForwardObj);

	TSharedPtr<FJsonObject> LeftObj = MakeShared<FJsonObject>();
	LeftObj->SetNumberField(TEXT("waist"), LeftWaist);
	TraceObj->SetObjectField(TEXT("left"), LeftObj);

	TSharedPtr<FJsonObject> RightObj = MakeShared<FJsonObject>();
	RightObj->SetNumberField(TEXT("waist"), RightWaist);
	TraceObj->SetObjectField(TEXT("right"), RightObj);

	TSharedPtr<FJsonObject> DownObj = MakeShared<FJsonObject>();
	DownObj->SetNumberField(TEXT("dist"), DownDist);
	TraceObj->SetObjectField(TEXT("down"), DownObj);

	Out->SetObjectField(TEXT("trace"), TraceObj);

	// Derived flags
	TSharedPtr<FJsonObject> BlockedObj = MakeShared<FJsonObject>();
	BlockedObj->SetBoolField(TEXT("forward"), ForwardWaist > 0.f && ForwardWaist < 100.f);
	Out->SetObjectField(TEXT("blocked"), BlockedObj);
}

void UStrandsInputServerSubsystem::WriteWorldStateToFile(const FString& OutPath)
{
	UWorld* World = GetWorld();
	TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
	BuildWorldState(Root, World);

	const FString Dir = FPaths::GetPath(OutPath);
	if (!Dir.IsEmpty())
	{
		IFileManager::Get().MakeDirectory(*Dir, true);
	}

	FString Output;
	TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Output);
	FJsonSerializer::Serialize(Root, Writer);

	FFileHelper::SaveStringToFile(Output, *OutPath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
}
