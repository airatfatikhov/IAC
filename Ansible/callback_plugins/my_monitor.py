from ansible.plugins.callback import CallbackBase

class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = 'my_monitor'

    def v2_runner_on_ok(self, result):
        # Отправить метрику "Успех" в вашу систему
        host = result._host.get_name()
        task = result._task.name
        print(f"METRIC: OK | Host: {host} | Task: {task}")

    def v2_runner_on_failed(self, result, ignore_errors=False):
        # Отправить алерт "Ошибка"
        host = result._host.get_name()
        task = result._task.name
        msg = result._result.get('msg', 'Unknown error')
        print(f"ALERT: FAILED | Host: {host} | Task: {task} | Error: {msg}")