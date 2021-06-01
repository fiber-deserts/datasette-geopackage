from datasette import hookimpl
from datasette.utils.asgi import Response, NotFound
from datasette_geopackage.utils import (
    detect_geopackage_databases,
    latlon_to_tile_with_adjust,
    tile_to_latlon,
    rows_to_tile
)
import json
import math
import morecantile

# Enable Shapely "speedups" if available
# http://toblerity.org/shapely/manual.html#performance
from shapely import speedups
if speedups.available:
    speedups.enable()

# Empty vector tile from tilemaker
MVT_404 = b"\x1F\x8B\x08\x00\xFA\x78\x18\x5E\x00\x03\x93\xE2\xE3\x62\x8F\x8F\x4F\xCD\x2D\x28\xA9\xD4\x68\x50\xA8\x60\x02\x00\x64\x71\x44\x36\x10\x00\x00\x00"

projection = morecantile.tms.get("WebMercatorQuad")

@hookimpl
def register_routes():
    return [
        (r"/-/gpkg$", index),
        (r"/-/gpkg/(?P<db_name>[^/]+)$", explorer),
        # (r"/-/gpkg/(?P<db_name>[^/]+)/(?P<layer_name>[^/]+)$", layer_explorer),
        (r"/-/gpkg/(?P<db_name>[^/]+)/(?P<layer_name>[^/]+)/spec.json$", tilejson),
        (r"/-/gpkg/(?P<db_name>[^/]+)/(?P<layer_name>[^/]+)/(?P<z>\d+)/(?P<x>\d+)/(?P<y>\d+)\.mvt$", tile),
        (
            r"/-/gpkg-tms/(?P<db_name>[^/]+)/(?P<layer_name>[^/]+)/(?P<z>\d+)/(?P<x>\d+)/(?P<y>\d+)\.mvt$",
            tile_tms,
        )
        ]

async def index(datasette):
    return Response.html(
        await datasette.render_template(
            "gpkg_index.html",
            {"geopackage_databases": await detect_geopackage_databases(datasette)},
        )
    )

async def load_vector_tile(db, request, tms):
    z = int(request.url_vars["z"])
    x = int(request.url_vars["x"])
    y = int(request.url_vars["y"])
    # if not tms:
    #     y = int(math.pow(2, z) - 1 - y)
    layer_name = request.url_vars["layer_name"]
    tile = morecantile.Tile(x, y, z)
    tile_bounds = projection.bounds(tile)
    query = (f"select \"{layer_name}\".* from \"{layer_name}\", \"rtree_{layer_name}_geom\" where \"{layer_name}\".fid = \"rtree_{layer_name}_geom\".id"
        f" and minx <= {tile_bounds.right} and maxx >= {tile_bounds.left}"
        f" and miny <= {tile_bounds.top} and maxy >= {tile_bounds.bottom}")

    result = await db.execute(query)
    if not result.rows:
        return None

    return rows_to_tile(layer_name, tile_bounds, result.rows)

async def tilejson(request, datasette):
    db_name = request.url_vars["db_name"]
    mbtiles_databases = await detect_geopackage_databases(datasette)
    if db_name not in mbtiles_databases:
        raise NotFound("Not a valid geopackage database")
    db = datasette.get_database(db_name)
    layer_name = request.url_vars["layer_name"]
    query = (f"select * from gpkg_contents where table_name='{layer_name}'")
    result = await db.execute(query)
    if not result:
        return Response.json(body={"error": "unknown layer"}, status=404)

    row = result.rows[0]
    print(row.keys())
    info = {
        "tilejson": "2.2.0",
        "name": row["identifier"],
        "description": row["description"],
        "scheme": "xyz",
        "tiles": [f"http://127.0.0.1:8001/-/gpkg/{db_name}/{layer_name}/{{z}}/{{x}}/{{y}}.mvt"],
        "bounds": [
            row["min_x"],
            row["min_y"],
            row["max_x"],
            row["max_y"]
        ]
    }
    return Response.json(body=info)


async def tile(request, datasette):
    return await _tile(request, datasette, tms=False)


async def tile_tms(request, datasette):
    return await _tile(request, datasette, tms=True)


async def _tile(request, datasette, tms):
    db_name = request.url_vars["db_name"]
    mbtiles_databases = await detect_geopackage_databases(datasette)
    if db_name not in mbtiles_databases:
        raise NotFound("Not a valid geopackage database")
    db = datasette.get_database(db_name)
    tile = await load_vector_tile(db, request, tms)
    if tile is None:
        return Response(body=MVT_404, content_type="application/vnd.mapbox-vector-tile", status=404)
    return Response(body=tile, content_type="application/vnd.mapbox-vector-tile")

async def explorer(datasette, request):
    db_name = request.url_vars["db_name"]
    mbtiles_databases = await detect_geopackage_databases(datasette)
    if db_name not in mbtiles_databases:
        raise NotFound("Not a valid mbtiles database")
    db = datasette.get_database(db_name)
    metadata = {
        row["name"]: row["value"]
        for row in (await db.execute("select name, value from metadata")).rows
    }
    default_latitude = 0
    default_longitude = 0
    default_zoom = 0
    if metadata.get("center") and len(metadata["center"].split(",")) == 3:
        default_longitude, default_latitude, default_zoom = metadata["center"].split(
            ","
        )
    min_zoom = 0
    max_zoom = 19
    if metadata.get("minzoom"):
        min_zoom = int(metadata["minzoom"])
    if metadata.get("maxzoom"):
        max_zoom = int(metadata["maxzoom"])
    attribution = metadata.get("attribution") or None

    # Provided location data
    lat = float(request.args.get("lat", default_latitude))
    lon = float(request.args.get("lon", default_longitude))
    zoom = int(request.args.get("z", default_zoom))
    if zoom > max_zoom:
        zoom = max_zoom
    if zoom < min_zoom:
        zoom = min_zoom
    x_tile, y_tile = latlon_to_tile_with_adjust(lat, lon, zoom)

    return Response.html(
        await datasette.render_template(
            "tiles_explorer.html",
            {
                "nojs": request.args.get("nojs") or request.args.get("lat"),
                "metadata": metadata,
                "db_name": db_name,
                "db_path": datasette.urls.database(db_name),
                "default_latitude": default_latitude,
                "default_longitude": default_longitude,
                "default_zoom": default_zoom,
                "min_zoom": min_zoom,
                "max_zoom": max_zoom,
                "attribution": json.dumps(attribution),
                "current_latitude": lat,
                "current_longitude": lon,
                "can_zoom_in": zoom < max_zoom,
                "can_zoom_out": zoom > min_zoom,
                "current_zoom": zoom,
                "current_x": x_tile,
                "current_y": y_tile,
                "compass": {
                    "n": tile_to_latlon(x_tile, y_tile - 1, zoom),
                    "s": tile_to_latlon(x_tile, y_tile + 1, zoom),
                    "e": tile_to_latlon(x_tile + 1, y_tile, zoom),
                    "w": tile_to_latlon(x_tile - 1, y_tile, zoom),
                },
            },
        )
    )

@hookimpl
def database_actions(datasette, database):
    async def inner():
        mbtiles_databases = await detect_geopackage_databases(datasette)
        if database in mbtiles_databases:
            return [
                {
                    "href": datasette.urls.path("/-/gpkg/{}".format(database)),
                    "label": "Explore these tiles on a map",
                }
            ]

    return inner


@hookimpl
def table_actions(datasette, database, table):
    async def inner():
        if table != "tiles":
            return None
        mbtiles_databases = await detect_geopackage_databases(datasette)
        if database in mbtiles_databases:
            return [
                {
                    "href": datasette.urls.path("/-/gpkg/{}/{}".format(database, table)),
                    "label": "Explore this layer on a map",
                }
            ]

    return inner
