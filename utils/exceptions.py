class LoginRequiredError(RuntimeError):
    pass


class UserSearchError(RuntimeError):
    pass


class ChatOpenError(RuntimeError):
    pass


class MessageSendError(RuntimeError):
    pass


class OCRNotAvailableError(RuntimeError):
    pass
