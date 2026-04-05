class AppContext:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._logger = None
        return cls._instance

    def set_logger(self, logger_instance):
        self._logger = logger_instance

    def get_logger(self):
        if self._logger is None:
            raise RuntimeError("Logger not initialized")
        return self._logger


APP_CTX = AppContext()