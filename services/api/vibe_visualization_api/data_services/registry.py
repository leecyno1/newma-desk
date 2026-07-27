from vibe_visualization_api.data_services.models import DataServiceDescriptor


class DataServiceRegistryError(Exception):
    """Base error for registered data service discovery."""


class DataServiceNotFoundError(DataServiceRegistryError):
    """Raised when a data service ID is not registered."""


class DataCapabilityNotFoundError(DataServiceRegistryError):
    """Raised when no registered service provides a capability."""


class PreferredDataServiceUnavailable(DataServiceRegistryError):
    """Raised when a saved provider no longer exposes the capability."""


class DataServiceRegistry:
    def __init__(self, services: list[DataServiceDescriptor]):
        self._services: dict[str, DataServiceDescriptor] = {}
        for service in services:
            if service.id in self._services:
                raise ValueError(f"duplicate data service {service.id!r}")
            self._services[service.id] = service

    def get(self, service_id: str) -> DataServiceDescriptor:
        try:
            return self._services[service_id]
        except KeyError as error:
            raise DataServiceNotFoundError(
                f"data service {service_id!r} is not registered"
            ) from error

    def capabilities(self) -> list[str]:
        return sorted(
            {
                capability_id
                for service in self._services.values()
                for capability_id in service.capabilities
            }
        )

    def providers(self, capability_id: str) -> list[DataServiceDescriptor]:
        return sorted(
            [
                service
                for service in self._services.values()
                if capability_id in service.capabilities
            ],
            key=lambda service: (service.priority, service.id),
        )

    def resolve(
        self,
        capability_id: str,
        preferred_service_id: str | None = None,
    ) -> DataServiceDescriptor:
        providers = self.providers(capability_id)
        if not providers:
            raise DataCapabilityNotFoundError(
                f"data capability {capability_id!r} is not registered"
            )
        if preferred_service_id is None:
            return providers[0]
        for provider in providers:
            if provider.id == preferred_service_id:
                return provider
        raise PreferredDataServiceUnavailable(
            f"data service {preferred_service_id!r} does not provide {capability_id!r}"
        )

    def catalog(self) -> dict[str, object]:
        capabilities: list[dict[str, object]] = []
        for capability_id in self.capabilities():
            providers = self.providers(capability_id)
            permissions = sorted(
                {
                    provider.capabilities[capability_id].permission
                    for provider in providers
                }
            )
            capabilities.append(
                {
                    "id": capability_id,
                    "permissions": permissions,
                    "providers": [
                        {
                            "id": provider.id,
                            "name": provider.name or provider.id,
                            "description": provider.description or "",
                            "priority": provider.priority,
                            "transport": provider.transport,
                        }
                        for provider in providers
                    ],
                }
            )
        return {"version": "1.0", "capabilities": capabilities}

    def describe(self) -> list[dict[str, object]]:
        return [
            {
                "id": service.id,
                "name": service.name or service.id,
                "description": service.description or "",
                "priority": service.priority,
                "transport": service.transport,
                "capabilities": {
                    capability_id: capability.model_dump(mode="json")
                    for capability_id, capability in sorted(
                        service.capabilities.items()
                    )
                },
            }
            for service in sorted(self._services.values(), key=lambda item: item.id)
        ]
