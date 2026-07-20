from vibe_visualization_api.data_services.models import DataServiceDescriptor


class DataServiceRegistryError(Exception):
    """Base error for registered data service discovery."""


class DataServiceNotFoundError(DataServiceRegistryError):
    """Raised when a data service ID is not registered."""


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

    def describe(self) -> list[dict[str, object]]:
        return [
            {
                "id": service.id,
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
