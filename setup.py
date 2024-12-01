from setuptools import setup, find_packages

setup(
    name="janito",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "anthropic",
        "prompt_toolkit",
        "rich",
        "typer",
        "watchdog",
        "pytest"
    ],
    python_requires=">=3.8",
)