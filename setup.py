from setuptools import setup, find_packages

with open('requirements.txt') as f:
    requirements = f.read().splitlines()

setup(
    name="StreamJam",
    version="0.0.1",
    packages=find_packages(),
    install_requires=requirements,
    entry_points={
        "console_scripts": ["streamjam=streamjam.cli:app"]
    },
    author="Sandeep S Kumar",
    author_email="sanygeek@gmail.com",
    description="Unifying frontend and backend into one Pythonic experience for sleek, interactive web apps.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/creativesands/streamjam",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
