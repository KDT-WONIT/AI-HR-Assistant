class StorageUnavailable(Exception):
    """DB 오류 상세나 비밀번호를 HTTP 응답에 노출하지 않습니다."""


class ConversationConflict(Exception):
    pass


class ModelUnavailable(Exception):
    pass


class RagUnavailable(Exception):
    pass


class MCPUnavailable(Exception):
    pass
