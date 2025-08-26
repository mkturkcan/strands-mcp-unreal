#include "Modules/ModuleManager.h"

class FStrandsInputServerModule : public IModuleInterface
{
public:
	virtual void StartupModule() override {}
	virtual void ShutdownModule() override {}
};

IMPLEMENT_MODULE(FStrandsInputServerModule, StrandsInputServer)
