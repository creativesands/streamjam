import logging

from typer import Typer

from .project import create, build


logger = logging.getLogger('streamjam.cli')


app = Typer()


app.command()(create)
app.command()(build)


@app.command()
def run():
    """Run StreamJam server"""
    print('Placeholder command to run StreamJam server')


@app.command()
def dev(host: str = '0.0.0.0', port: int = 7755):
    """Run StreamJam Development Server"""
    print('Placeholder command to run StreamJam dev server')
