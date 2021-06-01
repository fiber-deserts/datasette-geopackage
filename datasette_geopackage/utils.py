import math
from mapbox_vector_tile.compat import vector_tile
from mapbox_vector_tile.geom_encoder import GeometryEncoder
import shapely
import pyproj

gps = pyproj.CRS('EPSG:4326')
mercator = pyproj.CRS('EPSG:3857')

transformer = pyproj.Transformer.from_crs(gps, mercator, always_xy=True)

async def detect_geopackage_databases(datasette):
    await datasette.refresh_schemas()
    internal = datasette.get_database("_internal")
    result = await internal.execute(
        """
    select
      columns.database_name,
      columns.table_name,
      group_concat(columns.name) as columns
    from
      columns
    where
      columns.table_name = "gpkg_contents"
    group by
      columns.database_name,
      columns.table_name
    order by
      columns.table_name
    """
    )
    return [
        row["database_name"]
        for row in result.rows
        if set(row["columns"].split(",")).issuperset(
            {"table_name", "data_type", "identifier", "description", "last_change"}
        )
    ]

def latlon_to_tile(lat, lon, zoom):
    x_tile = (lon + 180) / 360 * 2 ** zoom
    y_tile = (
        (
            1
            - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat)))
            / math.pi
        )
        / 2
        * 2 ** zoom
    )
    return x_tile, y_tile


# Given a lat/lon, convert it to OSM tile co-ordinates (nearest actual tile,
# adjusted so the point will be near the centre of a 2x2 tiled map).
def latlon_to_tile_with_adjust(lat, lon, zoom):
    x_tile, y_tile = latlon_to_tile(lat, lon, zoom)

    # Try and have point near centre of map
    if x_tile - int(x_tile) > 0.5:
        x_tile += 1
    if y_tile - int(y_tile) > 0.5:
        y_tile += 1

    return int(x_tile), int(y_tile)


def tile_to_latlon(x, y, zoom):
    n = 2 ** zoom
    lon = x / n * 360 - 180
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return {"lat": lat, "lon": lon}

def _get_feature_type(shape):
    if shape.type == 'Point' or shape.type == 'MultiPoint':
        return vector_tile.tile.GeomType.Point
    elif shape.type == 'LineString' or shape.type == 'MultiLineString':
        return vector_tile.tile.GeomType.LineString
    elif shape.type == 'Polygon' or shape.type == 'MultiPolygon':
        return vector_tile.tile.GeomType.Polygon
    elif shape.type == 'GeometryCollection':
        raise ValueError('Encoding geometry collections not supported')
    else:
        raise ValueError('Cannot encode unknown geometry type: %s' %
                         shape.type)

envelope_length = [0, 32, 48, 48, 64]

def rows_to_tile(layer_name, bounds, rows):
    tile = vector_tile.tile()
    layer = tile.layers.add()
    layer.name = layer_name
    layer.version = 2
    layer.extent = 4096
    bounds = shapely.geometry.box(bounds.left, bounds.bottom, bounds.right, bounds.top)
    projected_bounds = shapely.ops.transform(transformer.transform, bounds)
    minx, miny, maxx, maxy = projected_bounds.bounds
    simplify = (maxx - minx) / 4096 
    scale = 4096 / (maxx - minx)
    origin = (minx, miny)
    attribute_keys = []
    for key in rows[0].keys():
        if key in ("fid", "geom"):
            continue
        attribute_keys.append(key)
        layer.keys.append(key)

    all_values = {}

    def _to_tile(x, y):
        x = x - minx
        y = y - miny
        x *= scale
        y *= scale
        return int(x), int(y)
    i = 0
    for row in rows:
        geom = row["geom"]
        flags = geom[3]
        envelope_type = (flags >> 1) & 0b111
        offset = 8 + envelope_length[envelope_type]
        geom = shapely.wkb.loads(geom[offset:])
        geom = geom.intersection(bounds)

        geom = shapely.ops.transform(transformer.transform, geom).simplify(simplify)
        geom = shapely.ops.transform(_to_tile, geom)
        if geom.is_empty:
            continue
        if isinstance(geom, shapely.geometry.Polygon):
            geom = shapely.geometry.polygon.orient(geom, sign=-1.0)
        elif isinstance(geom, shapely.geometry.MultiPolygon):
            new_polygons = []
            for i, polygon in enumerate(geom):
                new_polygons.append(shapely.geometry.polygon.orient(polygon, sign=-1.0))
            geom = shapely.geometry.MultiPolygon(new_polygons)
        
        encoder = GeometryEncoder(False, 4096, round)
        encoded = encoder.encode(geom)
        if len(encoded) == 0:
            continue
        f = layer.features.add()
        f.id = row["fid"]
        f.type = _get_feature_type(geom)
        f.geometry.extend(encoded)
        for j, key in enumerate(attribute_keys):
            value = row[key]
            if value is None:
                continue
            if value not in all_values:
                all_values[value] = len(all_values)
                v = layer.values.add()
                if isinstance(value, bool):
                    v.bool_value = value
                elif isinstance(value, str):
                    v.string_value = value
                elif isinstance(value, int):
                    v.int_value = value
                elif isinstance(value, float):
                    v.double_value = value
            f.tags.append(j)
            f.tags.append(all_values[value])

    return tile.SerializeToString()
