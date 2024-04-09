"""
/{{project_name}}
    __init__.py
    main.py
    /public
    /assets
    /components
        __init__.py
        root.py
    .gitignore
    requirements.txt  # ignore .build
    package.json
    /.build
        /public
        /src
            /assets
            /components
                index.js
                Root.svelte
            App.svelte
            main.js
            vite-env.d.ts
        index.html
        jsconfig.json
        package.json
        svelte.config.js
        vite.config.js
"""

import os
import time
from threading import Timer
from cookiecutter import main
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .transpiler import build_project


project_template = "gh:creativesands/streamjam-project-template"


def create():
    """Create a new StreamJam project"""
    main.cookiecutter(template=project_template)


class DebouncedHandler(FileSystemEventHandler):
    def __init__(self, callback, debounce_interval=1.0):
        self.callback = callback
        self.debounce_interval = debounce_interval
        self._timer = None

    def on_any_event(self, event):
        if f'{os.sep}.build{os.sep}' in event.src_path:
            return
        if '__pycache__' in event.src_path:
            return
        if event.src_path.endswith('.py~'):
            return
        if event.is_directory:
            return

        print(f'Change triggered by: {event.src_path!r}')

        if not event.is_directory:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = Timer(self.debounce_interval, self.callback)
            self._timer.start()


def build(path='.'):
    """Transpile and build project"""
    event_handler = DebouncedHandler(build_project)
    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
