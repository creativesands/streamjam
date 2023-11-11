import json
from importlib.util import spec_from_file_location, module_from_spec

from .component import Component


"""
- go through /components
- each file must contain only one component
- convert component to .svelte file
- copy any .svelte files as is
- maintain directory hierarchy
- watch /components for any updates and continnuously transpile
"""


SCRIPT_TEMPLATE = """
<script>
    /*---------- BEGIN: STREAMJAM ----------*/

    import {{ getContext, setContext, onDestroy as __onDestroy }} from "svelte"
    import {{ ID }} from "streamjam"

    export let __id = ID()
    export let __restored = false

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


def transpile(file_path):
    print('Transpiling:', file_path)
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
                    rpc_init.append(f'__self.proxyRPC({name!r})')

            component_script = cls.Script.__doc__ or ''
            svelte_html = cls.Layout.__doc__ or ''
            svelte_css = cls.Style.__doc__ or ''
            svelte_script = SCRIPT_TEMPLATE.format(
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

            return '\n\n'.join(svelte_content)  # returns only first component
