from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os
import time
import json
from ansible.plugins.callback import CallbackBase

class CallbackModule(CallbackBase):
    """
    Callback plugin that saves Ansible execution metrics to a file 
    in Prometheus text format for Node Exporter textfile collector.
    """
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = 'prometheus_simple'
    
    def __init__(self):
        super(CallbackModule, self).__init__()
        self.start_time = None
        self.playbook_name = None
        self.tasks_stats = {
            'ok': 0,
            'changed': 0,
            'failed': 0,
            'unreachable': 0,
            'skipped': 0
        }
        # Путь по умолчанию, можно переопределить через ENV
        self.output_dir = os.environ.get('ANSIBLE_PROMETHEUS_DIR', '/tmp')
        self.filename = 'ansible_metrics.prom'

    def v2_playbook_on_start(self, playbook):
        self.start_time = time.time()
        # Получаем имя плейбука
        self.playbook_name = os.path.basename(playbook._file_name) if playbook._file_name else 'unknown'

    def v2_runner_on_ok(self, result):
        if result._result.get('changed', False):
            self.tasks_stats['changed'] += 1
        else:
            self.tasks_stats['ok'] += 1

    def v2_runner_on_failed(self, result, ignore_errors=False):
        self.tasks_stats['failed'] += 1

    def v2_runner_on_unreachable(self, result):
        self.tasks_stats['unreachable'] += 1

    def v2_runner_on_skipped(self, result):
        self.tasks_stats['skipped'] += 1

    def v2_playbook_on_stats(self, stats):
        duration = time.time() - self.start_time
        timestamp = int(time.time())
        
        # Формируем строки метрик
        lines = []
        
        # 1. Длительность выполнения
        lines.append('# HELP ansible_playbook_duration_seconds Duration of the last playbook execution in seconds')
        lines.append('# TYPE ansible_playbook_duration_seconds gauge')
        lines.append(f'ansible_playbook_duration_seconds{{playbook="{self.playbook_name}"}} {duration:.2f}')
        
        # 2. Статус выполнения (0 - успех, 1 - есть ошибки)
        status = 1 if self.tasks_stats['failed'] > 0 or self.tasks_stats['unreachable'] > 0 else 0
        lines.append('# HELP ansible_playbook_status Status of the last run (0=OK, 1=Failed)')
        lines.append('# TYPE ansible_playbook_status gauge')
        lines.append(f'ansible_playbook_status{{playbook="{self.playbook_name}"}} {status}')
        
        # 3. Количество задач по статусам
        lines.append('# HELP ansible_tasks_total Total number of tasks by status')
        lines.append('# TYPE ansible_tasks_total counter')
        for status_name, count in self.tasks_stats.items():
            lines.append(f'ansible_tasks_total{{playbook="{self.playbook_name}",status="{status_name}"}} {count}')
            
        # 4. Timestamp последнего запуска
        lines.append('# HELP ansible_last_run_timestamp Unix timestamp of the last run')
        lines.append('# TYPE ansible_last_run_timestamp gauge')
        lines.append(f'ansible_last_run_timestamp{{playbook="{self.playbook_name}"}} {timestamp}')

        # Записываем в файл
        output_path = os.path.join(self.output_dir, self.filename)
        try:
            with open(output_path, 'w') as f:
                f.write('\n'.join(lines) + '\n')
            self._display.display(f"✅ Prometheus metrics saved to: {output_path}", color='green')
        except Exception as e:
            self._display.warning(f"❌ Could not write metrics file: {e}")