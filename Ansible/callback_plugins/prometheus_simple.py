import os
import time
import logging
from ansible.plugins.callback import CallbackBase

# ============ НАСТРОЙКА ЛОГИРОВАНИЯ ============
LOG_FILE = '/tmp/ansible_prometheus_callback.log'

logger = logging.getLogger('ansible_prometheus')
logger.setLevel(logging.DEBUG)

# Очищаем лог при каждом запуске (опционально)
# handler = logging.FileHandler(LOG_FILE, mode='w')
handler = logging.FileHandler(LOG_FILE, mode='a')  # дописывать в конец
formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
handler.setFormatter(formatter)
logger.addHandler(handler)

# Пишем приветствие сразу при загрузке модуля
logger.info("🔌 Callback-плагин prometheus_simple ЗАГРУЖЕН")
# ================================================


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = 'prometheus_simple'

    def __init__(self):
        super(CallbackModule, self).__init__()
        logger.info("📦 Инициализация CallbackModule")
        self.start_time = None
        self.playbook_name = None
        self.project_name = 'unknown'
        self.output_dir = '/tmp'
        self.filename = None
        self.tasks_stats = {
            'ok': 0,
            'changed': 0,
            'failed': 0,
            'unreachable': 0,
            'skipped': 0
        }

    def set_options(self, task_keys=None, var_options=None, direct=None):
        super(CallbackModule, self).set_options(
            task_keys=task_keys, var_options=var_options, direct=direct
        )
        try:
            self.output_dir = self.get_option('output_dir')
            self.project_name = self.get_option('project_name')
            logger.info(f"✅ Опции прочитаны: output_dir={self.output_dir}, project_name={self.project_name}")
        except Exception as e:
            logger.error(f"❌ Ошибка чтения опций из ansible.cfg: {e}")
            logger.error("Используются значения по умолчанию")

    def v2_playbook_on_start(self, playbook):
        logger.info(f"▶️  Старт плейбука: {playbook._file_name}")
        self.start_time = time.time()
        self.playbook_name = os.path.basename(
            playbook._file_name
        ) if playbook._file_name else 'unknown'

        if self.filename is None:
            safe_name = self.project_name.replace(' ', '_').replace('/', '_')
            self.filename = f'ansible_{safe_name}.prom'
            logger.info(f"📄 Имя файла метрик: {self.filename}")

    def v2_runner_on_ok(self, result):
        task_name = result._task.get_name()
        if result._result.get('changed', False):
            self.tasks_stats['changed'] += 1
            logger.debug(f"✅ CHANGED: {task_name}")
        else:
            self.tasks_stats['ok'] += 1
            logger.debug(f"🟢 OK: {task_name}")

    def v2_runner_on_failed(self, result, ignore_errors=False):
        task_name = result._task.get_name()
        self.tasks_stats['failed'] += 1
        msg = result._result.get('msg', 'no message')
        logger.error(f"❌ FAILED: {task_name} | {msg}")

    def v2_runner_on_unreachable(self, result):
        host = result._host.get_name()
        self.tasks_stats['unreachable'] += 1
        logger.error(f"🚫 UNREACHABLE: {host}")

    def v2_runner_on_skipped(self, result):
        task_name = result._task.get_name()
        self.tasks_stats['skipped'] += 1
        logger.debug(f"⏭️  SKIPPED: {task_name}")

    def v2_playbook_on_stats(self, stats):
        logger.info(f"📊 Статистика: {self.tasks_stats}")
        duration = time.time() - self.start_time
        timestamp = int(time.time())
        has_errors = (
            self.tasks_stats['failed'] > 0
            or self.tasks_stats['unreachable'] > 0
        )
        status = 1 if has_errors else 0

        lines = [
            '# HELP ansible_playbook_duration_seconds Duration of playbook execution',
            '# TYPE ansible_playbook_duration_seconds gauge',
            f'ansible_playbook_duration_seconds{{project="{self.project_name}",playbook="{self.playbook_name}"}} {duration:.2f}',
            '',
            '# HELP ansible_playbook_status Last run status (0=OK, 1=Failed)',
            '# TYPE ansible_playbook_status gauge',
            f'ansible_playbook_status{{project="{self.project_name}",playbook="{self.playbook_name}"}} {status}',
            '',
            '# HELP ansible_tasks_total Total tasks by status',
            '# TYPE ansible_tasks_total gauge',
        ]
        for s, count in self.tasks_stats.items():
            lines.append(
                f'ansible_tasks_total{{project="{self.project_name}",'
                f'playbook="{self.playbook_name}",status="{s}"}} {count}'
            )
        lines.extend([
            '',
            '# HELP ansible_last_run_timestamp Unix timestamp of last run',
            '# TYPE ansible_last_run_timestamp gauge',
            f'ansible_last_run_timestamp{{project="{self.project_name}"}} {timestamp}',
        ])

        output_path = os.path.join(self.output_dir, self.filename)
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            with open(output_path, 'w') as f:
                f.write('\n'.join(lines) + '\n')
            logger.info(f"✅ Метрики записаны в: {output_path}")
            self._display.display(
                f"✅ [{self.project_name}] Метрики → {output_path}",
                color='green'
            )
        except Exception as e:
            logger.exception(f"❌ Критическая ошибка записи файла: {e}")
            self._display.warning(f"❌ Ошибка записи метрик: {e}")

    DOCUMENTATION = r'''
    name: prometheus_simple
    type: notification
    short_description: Write metrics to Prometheus textfile
    options:
      output_dir:
        description: Directory for .prom files
        type: str
        default: /tmp
        ini:
          - section: callback_prometheus_simple
            key: output_dir
      project_name:
        description: Unique project identifier
        type: str
        default: unknown
        ini:
          - section: callback_prometheus_simple
            key: project_name
    '''