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

from cookiecutter import main


project_template = "gh:creativesands/streamjam-project-template"


def create():
    """Create a new StreamJam project"""
    main.cookiecutter(template=project_template)
