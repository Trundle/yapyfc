# encoding: utf-8

from setuptools import setup

from yapyfc import __version__


setup(
    name="yapyfc",
    author="Andreas Stührk",
    author_email="andy@hammerhartes.de",
    license="MIT",
    version=__version__,
    url="https://github.com/Trundle/yapyfc",
    packages=["yapyfc"],
    install_requires=[
        "click",
        "pyrepl",
        "termcolor"
    ])
