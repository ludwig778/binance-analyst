from uuid import UUID


def trunk_uuid(uuid: UUID, length: int = 8) -> str:
    return str(uuid)[:8]
