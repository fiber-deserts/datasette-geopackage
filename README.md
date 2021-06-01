# datasette-geopackage

[![PyPI](https://img.shields.io/pypi/v/datasette-geopackage.svg)](https://pypi.org/project/datasette-geopackage/)
[![Changelog](https://img.shields.io/github/v/release/tannewt/datasette-geopackage?include_prereleases&label=changelog)](https://github.com/tannewt/datasette-geopackage/releases)
[![Tests](https://github.com/tannewt/datasette-geopackage/workflows/Test/badge.svg)](https://github.com/tannewt/datasette-geopackage/actions?query=workflow%3ATest)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/tannewt/datasette-geopackage/blob/main/LICENSE)

Renders geopackage geometry using mapbox vector tiles

## Installation

Install this plugin in the same environment as Datasette.

    $ datasette install datasette-geopackage

## Usage

Usage instructions go here.

## Development

To set up this plugin locally, first checkout the code. Then create a new virtual environment:

    cd datasette-geopackage
    python3 -mvenv venv
    source venv/bin/activate

Or if you are using `pipenv`:

    pipenv shell

Now install the dependencies and tests:

    pip install -e '.[test]'

To run the tests:

    pytest
