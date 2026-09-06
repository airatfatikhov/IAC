# plugins/callback/my_logger.py

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os
import time
import tempfile
import datetime
from ansible.plugins.callback import CallbackBase

DOCUMENTATION = '''
    callback: my_logger
    type: notification
    short_description: Экспорт метрик Ansible для Node Exporter (офлайн)
    description: >
        Записывает результаты плейбука в файл формата Prometheus textfile,
        который подхватывается Node Exporter через textfile collector.
'''

class CallbackModule(CallbackBase):

    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = 'my_logger'

    # Директория, которую читает Node Exporter
    TEXTFILE_DIR = '/var/lib/node_exporter/textfile_collector'
    # Имя выходного файла (ОБЯЗАТЕЛЬНО .prom)
    METRICS_FILE = os.path.join(TEXTFILE_DIR, 'ansible_report.prom')

    def __init__(self):
        super(CallbackModule, self).__init__()

        # Счётчики по каждому хосту
        # Формат: { 'hostname': {'ok': 0, 'failed': 0, 'changed': 0, 'unreachable': 0} }
        self.host_stats = {}
        self.playbook_start_time = time.time()
        self.playbook_name = 'unknown'

    def _ensure_host(self, host):
        """Инициализирует счётчики для хоста, если их ещё нет"""
        if host not in self.host_stats:
            self.host_stats[host] = {
                'ok': 0,
                'failed': 0,
                'changed': 0,
                'unreachable': 0
            }

    # ──────────────────────────────────────────────
    # ПЕРЕХВАТЧИКИ СОБЫТИЙ
    # ──────────────────────────────────────────────

    def v2_playbook_on_play_start(self, play):
        """Срабатывает в начале каждого play. Запоминаем имя плейбука."""
        # play.get_name() возвращает значение поля 'name:' из плейбука
        name = play.get_name()
        if name:
            self.playbook_name = name

    def v2_runner_on_ok(self, result):
        """Задача завершилась успешно"""
        host = result._host.get_name()
        self._ensure_host(host)
        self.host_stats[host]['ok'] += 1
        if result.is_changed():
            self.host_stats[host]['changed'] += 1

    def v2_runner_on_failed(self, result, ignore_errors=False):
        """Задача упала"""
        host = result._host.get_name()
        self._ensure_host(host)
        self.host_stats[host]['failed'] += 1

    def v2_runner_on_unreachable(self, result):
        """Хост недоступен"""
        host = result._host.get_name()
        self._ensure_host(host)
        self.host_stats[host]['unreachable'] += 1

    # ──────────────────────────────────────────────
    # ФИНАЛИЗАЦИЯ: записываем .prom файл
    # ──────────────────────────────────────────────

    def v2_playbook_on_stats(self, stats):
        """
        Срабатывает ОДИН раз в самом конце всего плейбука.
        Здесь мы формируем содержимое .prom файла и записываем его.
        """
        duration = time.time() - self.playbook_start_time
        now_iso = datetime.datetime.now().isoformat()

        lines = []

        # --- Метрика 1: длительность последнего прогона ---
        lines.append('# HELP ansible_playbook_duration_seconds '
                     'Duration of the last playbook run in seconds')
        lines.append('# TYPE ansible_playbook_duration_seconds gauge')
        lines.append('ansible_playbook_duration_seconds{playbook="%s"} %.4f'
                     % (self._escape(self.playbook_name), duration))
        lines.append('')

        # --- Метрика 2: время последнего прогона (Unix timestamp) ---
        lines.append('# HELP ansible_last_run_timestamp_seconds '
                     'Unix timestamp of the last playbook run')
        lines.append('# TYPE ansible_last_run_timestamp_seconds gauge')
        lines.append('ansible_last_run_timestamp_seconds{playbook="%s"} %.0f'
                     % (self._escape(self.playbook_name), time.time()))
        lines.append('')

        # --- Метрики 3-6: счётчики по каждому хосту ---
        # Мы создаём по одной метрике на каждый тип результата,
        # с лейблом host, чтобы Prometheus мог фильтровать по хостам.

        lines.append('# HELP ansible_tasks_ok Number of ok tasks per host')
        lines.append('# TYPE ansible_tasks_ok gauge')
        for host, counts in sorted(self.host_stats.items()):
            lines.append('ansible_tasks_ok{host="%s",playbook="%s"} %d'
                         % (self._escape(host),
                            self._escape(self.playbook_name),
                            counts['ok']))
        lines.append('')

        lines.append('# HELP ansible_tasks_failed Number of failed tasks per host')
        lines.append('# TYPE ansible_tasks_failed gauge')
        for host, counts in sorted(self.host_stats.items()):
            lines.append('ansible_tasks_failed{host="%s",playbook="%s"} %d'
                         % (self._escape(host),
                            self._escape(self.playbook_name),
                            counts['failed']))
        lines.append('')

        lines.append('# HELP ansible_tasks_changed Number of changed tasks per host')
        lines.append('# TYPE ansible_tasks_changed gauge')
        for host, counts in sorted(self.host_stats.items()):
            lines.append('ansible_tasks_changed{host="%s",playbook="%s"} %d'
                         % (self._escape(host),
                            self._escape(self.playbook_name),
                            counts['changed']))
        lines.append('')

        lines.append('# HELP ansible_tasks_unreachable Number of unreachable hosts')
        lines.append('# TYPE ansible_tasks_unreachable gauge')
        for host, counts in sorted(self.host_stats.items()):
            lines.append('ansible_tasks_unreachable{host="%s",playbook="%s"} %d'
                         % (self._escape(host),
                            self._escape(self.playbook_name),
                            counts['unreachable']))
        lines.append('')

        content = '\n'.join(lines) + '\n'

        # --- Безопасная запись (atomic write) ---
        self._write_atomic(self.METRICS_FILE, content)

        self._display.display(
            ">>> Метрики Ansible записаны в: %s" % self.METRICS_FILE,
            color='green'
        )

    # ──────────────────────────────────────────────
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ──────────────────────────────────────────────

    @staticmethod
    def _write_atomic(filepath, content):
        """
        Атомарная запись файла с явным указанием прав доступа.
        """
        dir_name = os.path.dirname(filepath)
        
        # Проверяем, существует ли директория
        if not os.path.isdir(dir_name):
            raise RuntimeError("Директория для метрик не существует: %s" % dir_name)

        try:
            # Создаем временный файл в той же директории
            # suffix='.tmp' чтобы node_exporter игнорировал его (по умолчанию игнорирует всё кроме .prom)
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
            try:
                with os.fdopen(fd, 'w') as f:
                    f.write(content)
                
                # !!! ВАЖНО: Устанавливаем права ДО переименования
                # 0o644 = rw-r--r-- (владелец пишет, все читают)
                # 0o664 = rw-rw-r-- (владелец и группа пишут, все читают)
                # Выберите подходящие права. Для node_exporter достаточно чтения.
                os.chmod(tmp_path, 0o644)
                
                # Атомарная замена
                os.rename(tmp_path, filepath)
                
            except Exception:
                # Если ошибка при записи или chmod — удаляем временный файл
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as e:
            raise RuntimeError("Не удалось записать метрики в %s: %s"
                               % (filepath, str(e)))