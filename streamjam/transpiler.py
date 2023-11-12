import os
import json
import shutil
import typing as tp
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec

from .component import Component


"""
- go through /components
- each file must contain only one component
- convert component to .svelte file
- copy any .svelte files as is
- maintain directory hierarchy
- watch /components for any updates and continuously transpile
"""


SCRIPT_TEMPLATE = """
<script>
    /*---------- BEGIN: STREAMJAM ----------*/

    import {{ getContext, setContext, onDestroy as __onDestroy }} from "svelte"
    import {{ ID }} from "streamjam"

    export let __id = {comp_id}
    export let __restored = {is_root}

    /* Props */
    {prop_init}

    const __client = getContext("streamjam")
    const __parentId = getContext("__parentId")
    const __self = __client.newComponent(__id, __parentId, __restored, {component_name!r}, {{{prop_dict}}})
    setContext("__parentId", __id)

    /* Shadow Stores Init */
    {store_init}

    /* Shadow Stores Reactive Get */
    {store_get}

    /* Shadow Stores Reactive Set */
    {store_set}

    /* Proxy RPCs */
    {rpc_init}

    /* Destroy Component */
    __onDestroy(() => {{
        __client.destroyComponent(__self)
    }})

    /*---------- END: STREAMJAM ----------*/

    {component_script}
</script>
"""


def load_module(module_name, file_path):
    spec = spec_from_file_location(module_name, file_path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def transpile_streamjam_to_svelte(file_path):
    module = load_module(module_name=file_path.stem, file_path=file_path)

    for attr_name in dir(module):
        cls = getattr(module, attr_name)
        if isinstance(cls, type) and issubclass(cls, Component) and cls is not Component:
            prop_dict = []
            prop_init = []
            store_init = []
            store_get = []
            store_set = []
            for prop, default in cls.__prop_defaults__.items():
                prop_dict.append(prop)
                if default is Ellipsis:
                    prop_init.append(f'export let {prop}')
                else:
                    prop_init.append(f'export let {prop} = {json.dumps(default)}')
                store_init.append(f'let _{prop} = __self.newStore({prop!r}, {prop})')
                store_get.append(f'$: {prop} = $_{prop}')
                store_set.append(f'$: if ($_{prop} !== {prop}) _{prop}.set({prop})')

            rpc_init = []
            for name, method in cls.__dict__.items():
                if hasattr(method, 'rpc'):
                    rpc_init.append(f'const {name} = __self.proxyRPC({name!r})')

            component_script = cls.Script.__doc__ or ''
            svelte_html = cls.Layout.__doc__ or ''
            svelte_css = cls.Style.__doc__ or ''
            svelte_script = SCRIPT_TEMPLATE.format(
                comp_id='"root"' if cls.__name__ == 'Root' else 'ID()',
                is_root='true' if cls.__name__ == 'Root' else 'false',
                component_name=cls.__name__,
                prop_dict=', '.join(prop_dict),
                prop_init='\n    '.join(prop_init),
                store_init='\n    '.join(store_init),
                store_get='\n    '.join(store_get),
                store_set='\n    '.join(store_set),
                rpc_init='\n    '.join(rpc_init),
                component_script=component_script
            )

            svelte_content = [svelte_script]
            svelte_html and svelte_content.append(f'{svelte_html}')
            svelte_css and svelte_content.append(f'<style>\n{svelte_css}\n</style>')

            return cls.__name__, '\n\n'.join(svelte_content)  # returns only first component


def create_component_index_js(component_paths: tp.List[Path]):
    imports = '\n'.join([f'import {comp.stem} from "./{comp.as_posix()}"' for comp in component_paths])
    exports = f'export default {{{", ".join([comp.stem for comp in component_paths])}}}'
    return imports + '\n\n' + exports + '\n'


def build_project(base_path, output_path):
    base_path = Path(base_path)
    output_path = Path(output_path)

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
                    print('>>> Transpiling:', file)
                    # Transpile Python files and save as .svelte
                    comp_name, transpiled_content = transpile_streamjam_to_svelte(src_file)
                    dest_file = dest_path / (comp_name + '.svelte')

                    component_paths.append(dest_file.relative_to(components_dest))
                    print('Producing:', dest_file, '\n')
                    with dest_file.open('w') as f:
                        f.write(transpiled_content)
                else:
                    # Copy other files as is
                    dest_file = dest_path / file
                    shutil.copy2(src_file, dest_file)

    index_js = components_dest / 'index.js'
    index_js.write_text(create_component_index_js(component_paths))
