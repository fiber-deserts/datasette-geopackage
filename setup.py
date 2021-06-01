from setuptools import setup
import os

VERSION = "0.1"


def get_long_description():
    with open(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "README.md"),
        encoding="utf8",
    ) as fp:
        return fp.read()


setup(
    name="datasette-geopackage",
    description="Renders geopackage geometry using mapbox vector tiles",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    author="Scott Shawcroft",
    url="https://github.com/tannewt/datasette-geopackage",
    project_urls={
        "Issues": "https://github.com/tannewt/datasette-geopackage/issues",
        "CI": "https://github.com/tannewt/datasette-geopackage/actions",
        "Changelog": "https://github.com/tannewt/datasette-geopackage/releases",
    },
    license="Apache License, Version 2.0",
    version=VERSION,
    packages=["datasette_geopackage"],
    entry_points={"datasette": ["geopackage = datasette_geopackage"]},
    install_requires=["datasette", "mapbox-vector-tile", "morecantile"],
    extras_require={"test": ["pytest", "pytest-asyncio"]},
    tests_require=["datasette-geopackage[test]"],
    package_data={
        "datasette_geopackage": ["static/*", "templates/*"]
    },
    python_requires=">=3.6",
)
