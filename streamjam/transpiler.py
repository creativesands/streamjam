import os
import re
import sys
import json
import shutil
import inspect
import typing as tp
from pathlib import Path
from datetime import datetime
from importlib.util import spec_from_file_location, module_from_spec

from .component import Component


"""
- go through /components
- each file must contain only one component
- convert component to .svelte file
- copy any .svelte files as is
- maintain directory hierarchy
- watch /components for any updates and continuously transpile
----
- write heuristics for __has_server__
"""


SCRIPT_TEMPLATE = open(os.path.dirname(__file__) + '/svelte_component_template.html').read()


def load_module(module_name, file_path):
    spec = spec_from_file_location(module_name, file_path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def find_project_root(start_path: Path) -> Path | None:
    for parent in start_path.parents:
        if (parent / '__root__.py').exists():
            return parent.absolute()
    return None


def load_package_module(file_path):
    """
    Load a module programmatically from a file path, respecting its package structure.
    Adjusts Python path as necessary to ensure package recognition.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"No such file: {file_path}")

    # find project root
    root_project_path = find_project_root(file_path)
    if not root_project_path:
        raise FileNotFoundError(f"Project root file: '__root__.py' not found!")
    # add to sys.path in order to support relative import of modules
    sys.path.insert(0, str(root_project_path.parent))

    # Construct relative module name within the package
    # Eg. ..services.socket -> <root>/services/socket
    relative_module_path = file_path.absolute().relative_to(root_project_path.parent).with_suffix('')
    relative_module_name = str(relative_module_path).replace(os.sep, '.')
    # print(f'Path DEBUG: {root_project_path=}, {relative_module_path=}, {relative_module_name=})')
    spec = spec_from_file_location(relative_module_name, file_path)

    if spec is None:
        raise ImportError(f"Cannot find module {relative_module_name}")

    module = module_from_spec(spec)
    sys.modules[relative_module_name] = module  # Important for relative imports
    spec.loader.exec_module(module)
    return module


def transpile_component(cls: tp.Type[Component], cls_path: str, imports: tp.List[tp.Type[Component]]):
    prop_dict = []
    prop_init = []
    store_init = []
    store_from_state = []
    store_from_props = []
    store_get = []
    store_set = []
    for prop, default in cls.__prop_defaults__.items():
        prop_dict.append(prop)
        if default is Ellipsis:
            prop_init.append(f'export let {prop}')
        else:
            prop_init.append(f'export let {prop} = {json.dumps(default)}')
        store_init.append(f'let _{prop}')
        store_from_state.append(f'_{prop} = __self.newStore({prop!r}, __client.state[id][{prop!r}])')
        store_from_props.append(f'_{prop} = __self.newStore({prop!r}, {prop})')
        store_get.append(f'$: {prop} = $_{prop}')
        store_set.append(f'$: if ($_{prop} !== {prop}) _{prop}.set({prop})')

    rpc_init = []
    for name, method in cls.__dict__.items():
        if hasattr(method, 'rpc'):
            rpc_init.append(f'const {name} = __self.proxyRPC({name!r})')

    import_components = []
    for imp_cls in imports:
        imp_cls_file_path = inspect.getmodule(imp_cls).__file__
        rel_parent = Path(os.path.relpath(imp_cls_file_path, os.path.dirname(cls_path))).parent
        rel_imp_path = rel_parent / f'{imp_cls.__name__}.svelte'
        import_components.append(f"import {imp_cls.__name__} from './{rel_imp_path}'")

    svelte_code = (cls.UI.__doc__ or '').replace('@\n', '', 1)
    script_tag_regex = r'<script[^>]*>([\s\S]*?)</script>'
    svelte_script_tag = re.search(script_tag_regex, svelte_code)
    svelte_html_css = re.sub(script_tag_regex, '', svelte_code)
    svelte_js = svelte_script_tag.group(1) if svelte_script_tag else ''

    svelte_content = SCRIPT_TEMPLATE.format(
        import_components='\n    '.join(import_components),
        comp_id='"root"' if cls.__name__ == 'Root' else 'null',
        is_root='true' if cls.__name__ == 'Root' else 'false',
        component_name=cls.__name__,
        prop_dict=', '.join(prop_dict),
        prop_init='\n    '.join(prop_init),
        has_server='true' if cls.__has_server__ else 'false',
        store_init='\n    '.join(store_init),
        store_from_state='\n        '.join(store_from_state),
        store_from_props='\n        '.join(store_from_props),
        store_get='\n    '.join(store_get),
        store_set='\n    '.join(store_set),
        rpc_init='\n    '.join(rpc_init),
        svelte_js=svelte_js,
        svelte_html_css=svelte_html_css
    )

    return cls.__name__, svelte_content


def transpile_streamjam_to_svelte(file_path):
    sys.path.append(os.path.dirname(file_path))
    module = load_package_module(file_path=file_path)
    imported_components = []
    main_component = None
    for name, obj in inspect.getmembers(module):
        if inspect.isclass(obj) and issubclass(obj, Component) and obj is not Component:
            try:
                cls_path = inspect.getsourcefile(obj)
                if str(file_path.absolute()) == cls_path:
                    main_component = obj
                else:
                    imported_components.append(obj)
            except TypeError:
                main_component = obj
    if main_component is not None:
        return transpile_component(main_component, file_path, imported_components)


def create_component_index_js(component_paths: tp.List[Path]):
    imports = '\n'.join([f'import {comp.stem} from "./{comp.as_posix()}"' for comp in component_paths])
    exports = f'export default {{{", ".join([comp.stem for comp in component_paths])}}}'
    return imports + '\n\n' + exports + '\n'


def get_components_in_project(base_path='.'):
    base_path = Path(base_path)
    components_src = base_path / 'components'
    sys.path.append(str(base_path.absolute()))

    components = {}
    for root, dirs, files in os.walk(components_src):
        if root.startswith('__'):
            print('ignoring', root)
            continue

        root_path = Path(root)

        for file in files:
            src_file = root_path / file
            if file.startswith('__'):
                continue
            if file.endswith('.py'):
                module = load_package_module(file_path=src_file)
                for attr_name in dir(module):
                    cls = getattr(module, attr_name)
                    if isinstance(cls, type) and issubclass(cls, Component) and cls is not Component:
                        components[attr_name] = cls

    return components


def build_project(base_path='.', output_path='.build'):
    print('Building project...')
    base_path = Path(base_path)
    output_path = Path(output_path)
    sys.path.append(str(base_path.absolute()))

    # Copy /public folder
    public_src = base_path / 'public'
    public_dest = output_path / 'public'
    if public_src.exists():
        shutil.copytree(public_src, public_dest, dirs_exist_ok=True)

    # Process /components folder
    components_src = base_path / 'components'
    components_dest = output_path / 'src/components'

    component_paths = []
    if components_src.exists():
        for root, dirs, files in os.walk(components_src):
            if root.startswith('__'):
                print('ignoring', root)
                continue

            root_path = Path(root)
            relative_path = root_path.relative_to(components_src)
            dest_path = components_dest / relative_path

            # Create directories in destination
            dest_path.mkdir(parents=True, exist_ok=True)

            for file in files:
                src_file = root_path / file
                if file.startswith('__'):
                    continue
                if file.endswith('.py'):
                    print(f'[{datetime.now().strftime("%H:%M:%S")}] >>> Transpiling: ', file)
                    # Transpile Python files and save as .svelte
                    did_transpile = transpile_streamjam_to_svelte(src_file)
                    if did_transpile:
                        comp_name, transpiled_content = did_transpile
                    else:
                        # python file does not contain a streamjam component definition
                        continue
                    dest_file = dest_path / (comp_name + '.svelte')

                    component_paths.append(dest_file.relative_to(components_dest))
                    print('Producing:', dest_file, '\n')
                    with dest_file.open('w', encoding='utf-8') as f:
                        f.write(transpiled_content)
                else:
                    # Copy other files as is
                    dest_file = dest_path / file
                    shutil.copy2(src_file, dest_file)

    index_js = components_dest / 'index.js'
    index_js.write_text(create_component_index_js(component_paths))
