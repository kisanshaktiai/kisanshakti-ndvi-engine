from supabase import create_client
from typing import List, Dict
import os

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError("Missing required environment variables")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

LAND_SELECT_FIELDS = """
id,
tenant_id,
farmer_id,
crop_type,
crop_stage,
sowing_date,
area_hectare,
boundary,
boundary_geom,
boundary_polygon_old,
center_lat,
center_lon
"""

def fetch_lands_by_ids(
    tenant_id: str,
    land_ids: List[str]
) -> List[Dict]:
    """
    Fetch lands with geometry in ONE query.
    Never fetch per land.
    """

    if not land_ids:
        return []

    resp = (
        supabase
        .table("lands")
        .select(LAND_SELECT_FIELDS)
        .eq("tenant_id", tenant_id)
        .in_("id", land_ids)
        .execute()
    )

    lands = resp.data or []

    # Hard validation — never allow silent geometry failure
    for land in lands:
        if not any([
            land.get("boundary_geom"),
            land.get("boundary"),
            land.get("boundary_polygon_old"),
            land.get("center_lat")
        ]):
            land["_geometry_warning"] = "no_valid_geometry_fields"

    return lands
