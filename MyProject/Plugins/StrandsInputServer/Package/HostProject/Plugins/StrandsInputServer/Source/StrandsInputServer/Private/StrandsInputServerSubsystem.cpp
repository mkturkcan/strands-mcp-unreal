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
		StartServer();
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
		Accumulator.RemoveAt(0, NewlineIndex + 1, /*bAllowShrinking*/false);
		Line.TrimStartAndEndInline();
		if (!Line.IsEmpty())
		{
			// Strip optional trailing \r
			if (Line.Len() > 0 && Line[Line.Len() - 1] == TEXT('\r'))
			{
				Line.RemoveAt(Line.Len() - 1, 1, false);
			}
			OutLines.Add(MoveTemp(Line));
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

		// Read all pending data
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
	ACharacter* Character = Strands_GetControlledCharacter(GetWorld());
	APawn* Pawn = Character ? (APawn*)Character : Strands_GetControlledPawn(GetWorld());

	if (Character)
	{
		if (!MoveAxis.IsNearlyZero())
		{
			Character->AddMovementInput(Character->GetActorForwardVector(), MoveAxis.X);
			Character->AddMovementInput(Character->GetActorRightVector(), MoveAxis.Y);
		}

		if (PendingJumpCount > 0)
		{
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
