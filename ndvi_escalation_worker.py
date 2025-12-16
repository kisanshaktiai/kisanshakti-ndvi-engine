import os
from datetime import date
from supabase import create_client

from land_loader import fetch_active_lands
from land_geometry import resolve_land_geometry
from land_ndvi import aggregate_ndvi_from_grids
from escalation import should_escalate

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def fetch_grid_stats_for_land(land):
    """
    Fetch precomputed NDVI grid stats using tile_ids.
    """
    if not land.get("tile_ids"):
        return []

    resp = (
        supabase
        .table("ndvi_spatial_analytics")
        .select("ndvi_histogram")
        .limit(5)
        .execute()
    )

    # Placeholder mapping
    return [{
        "ndvi_mean": 0.55,
        "ndvi_min": 0.32,
        "ndvi_max": 0.71,
        "overlap_ratio": 0.8
    }]

def run():
    lands = fetch_active_lands()

    for land in lands:
        try:
            geometry, geo_conf = resolve_land_geometry(land)
            grid_cells = fetch_grid_stats_for_land(land)

            ndvi = aggregate_ndvi_from_grids(grid_cells)

            # Write ndvi_data
            supabase.table("ndvi_data").upsert({
                "land_id": land["id"],
                "tenant_id": land["tenant_id"],
                "date": date.today().isoformat(),
                "ndvi_value": ndvi["mean_ndvi"],
                "ndvi_min": ndvi["ndvi_min"],
                "ndvi_max": ndvi["ndvi_max"],
                "coverage": ndvi["coverage_percentage"],
                "confidence_level": ndvi["confidence_level"],
                "quality_score": ndvi["quality_score"],
                "metadata": {
                    "geometry_confidence": geo_conf,
                    "method": "grid_weighted"
                }
            }).execute()

            # Escalation
            escalate, reason = should_escalate(land, geo_conf, ndvi)
            if escalate:
                supabase.table("ndvi_micro_tiles").upsert({
                    "land_id": land["id"],
                    "farmer_id": land["farmer_id"],
                    "tenant_id": land["tenant_id"],
                    "bbox": geometry,
                    "acquisition_date": date.today().isoformat(),
                    "ndvi_mean": ndvi["mean_ndvi"],
                    "ndvi_min": ndvi["ndvi_min"],
                    "ndvi_max": ndvi["ndvi_max"],
                    "statistics_only": True,
                    "resolution_meters": 10,
                }).execute()

            # Update lands snapshot
            supabase.table("lands").update({
                "last_ndvi_value": ndvi["mean_ndvi"],
                "last_ndvi_calculation": date.today().isoformat(),
                "ndvi_tested": True,
                "last_processed_at": "now()"
            }).eq("id", land["id"]).execute()

        except Exception as e:
            print(f"❌ Land {land['id']} failed: {e}")

if __name__ == "__main__":
    run()
