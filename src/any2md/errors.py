class Any2MDError(Exception):
    pass


class UnsupportedFormatError(Any2MDError):
    pass


class OutputPathError(Any2MDError):
    pass


class InputDiscoveryError(Any2MDError):
    pass


class OcrNotConfiguredError(Any2MDError):
    pass
