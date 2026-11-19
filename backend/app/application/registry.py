from app.domain.exceptions import RegistryDuplicateError, RegistryKeyError


class Registry[T]:
    def __init__(self) -> None:
        self._store: dict[str, T] = {}

    def register(self, key: str, instance: T) -> None:
        normalized = key.lower()
        if normalized in self._store:
            raise RegistryDuplicateError(f"Key already registered: {key!r}")
        self._store[normalized] = instance

    def get(self, key: str) -> T:
        normalized = key.lower()
        if normalized not in self._store:
            raise RegistryKeyError(f"Key not found: {key!r}")
        return self._store[normalized]

    def values(self) -> tuple[T, ...]:
        return tuple(self._store.values())
