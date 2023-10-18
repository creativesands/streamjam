from setuptools import setup, find_packages

setup(
    name="StreamJam",
    version="0.0.1",
    packages=find_packages(),
    install_requires=[
        # List your dependencies here
    ],
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
