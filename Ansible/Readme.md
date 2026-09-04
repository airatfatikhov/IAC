# Forks

forks — это параметр конфигурации Ansible, который определяет максимальное количество одновременных подключений (потоков/процессов) к управляемым узлам (серверам) во время выполнения плейбука.

* Значение по умолчанию: 5. Это значит, что даже если у вас в инвентаре 1000 серверов, Ansible будет одновременно работать только с 5 из них.
* Зачем это нужно? Чтобы не «положить» управляющую ноду (сервер, где запущен Ansible) нагрузкой, не исчерпать лимит файловых дескрипторов и не перегрузить сеть или целевые серверы.

````
[defaults]
forks = 5
````

# Callback плагин timer и profile_tasks
Эти плагины встроенные, но их нужно включить в ansible.cfg. Они показывают время выполнения каждой задачи, что помогает найти "узкие места".
В ansible.cfg:
````
[defaults]
# Разделять задачи запятой, если их несколько
callbacks_enabled = timer, profile_tasks, profile_roles
````

# Используйте log_path для аудита

````
[defaults]
log_path = /var/log/ansible.log
````

# Используйте Pipelining
Pipelining — это механизм оптимизации SSH-подключений в Ansible, который позволяет передавать код модулей напрямую в стандартный ввод (stdin) SSH-сессии, минуя создание временных файлов на целевом сервере.

````
# Включить конвейеризацию (убирает копирование файлов на сервер)
pipelining = True
````

# Настройка Prometheus Metrics
* Шаг 1: Создай файл callback_plugins/prometheus_simple.py

Создай папку callback_plugins рядом с твоим ansible.cfg, а внутри неё создай файл prometheus.py и вставь туда этот код:

* Шаг 2: Настрой ansible.cfg
````
[defaults]
callback_plugins = ./callback_plugins
callbacks_enabled = prometheus_simple
````

# Шаг 3: Настройка Node Exporter
Node Exporter должен знать, откуда читать этот файл. Открой конфигурацию сервиса Node Exporter (обычно это /etc/systemd/system/node_exporter.service или файл в /etc/default/node_exporter).
Найди строку ExecStart и добавь туда флаг --collector.textfile.directory:

````
ExecStart=/usr/local/bin/node_exporter \
    --collector.textfile.directory=/var/lib/node_exporter/textfile_collector \
    # ... остальные твои флаги ...
````

# Шаг 4: После изменения перезапусти Node Exporter
````
sudo systemctl daemon-reload
sudo systemctl restart node_exporter
````

# Шаг 5: Проверка и тестирование

1. Запусти любой тестовый плейбук
2.  Проверь содержимое созданного файла

