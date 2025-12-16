from shapely.geometry import shape, Point, mapping

def resolve_land_geometry(land: dict):
    """
    Returns: (geojson_geometry, confidence)
    confidence = high | medium | low
    """

    if land.get("boundary_geom"):
        return land["boundary_geom"], "high"

    if land.get("boundary"):
        return land["boundary"], "high"

    if land.get("boundary_polygon_old"):
        return land["boundary_polygon_old"], "medium"

    lat = land.get("center_lat")
    lon = land.get("center_lon")

    if lat and lon:
        pt = Point(float(lon), float(lat))
        buffered = pt.buffer(0.00036)  # ≈40 meters
        return mapping(buffered), "low"

    raise ValueError(f"Land {land['id']} has no valid geometry")
