import asyncio
from streamjam import StreamJam

app = StreamJam(
    name="{{cookiecutter.project_slug}}",
    component_map={}
)


if __name__ == '__main__':
    asyncio.run(app.serve())
