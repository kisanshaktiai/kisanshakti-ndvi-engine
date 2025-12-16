# ndvi_escalation_worker.py

import os
from datetime import date
from supabase import create_client

from land_loader import fetch_active_lands
from land_geometry import resolve_land_geometry
from land_ndvi import (
    aggregate_ndvi_from_grids,
    ndvi_confidence_score,
)
from escalation import should_escalate

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

TODAY = date.today().isoformat()


def fetch_grid_stats_for_land(land):
    """
    Fetch real NDVI grid data using PostGIS overlap.
    Requires RPC: get_land_ndvi_grids(land_id uuid)
    """

    resp = supabase.rpc(
        "get_land_ndvi_grids",
        {"land_id": land["id"]}
    ).execute()

    if not resp.data:
        raise ValueError("No grid NDVI data available")

    return resp.data


def run():
    lands = fetch_active_lands()

    for land in lands:
        try:
            geometry, geo_conf = resolve_land_geometry(land)

            grid_cells = fetch_grid_stats_for_land(land)

            ndvi = aggregate_ndvi_from_grids(grid_cells)
            confidence = ndvi_confidence_score(land, ndvi)

            # ─────────────────────────────────────
            # NDVI DATA UPSERT
            # ─────────────────────────────────────
            supabase.table("ndvi_data").upsert(
                {
                    "land_id": land["id"],
                    "tenant_id": land["tenant_id"],
                    "date": TODAY,
                    "ndvi_value": ndvi["mean_ndvi"],
                    "ndvi_min": ndvi["ndvi_min"],
                    "ndvi_max": ndvi["ndvi_max"],
                    "ndvi_std": ndvi["ndvi_std"],
                    "confidence_level": confidence["confidence_level"],
                    "quality_score": confidence["confidence_score"],
                    "metadata": {
                        "confidence_flags": confidence["confidence_flags"],
                        "geometry_confidence": geo_conf,
                        "method": "grid_weighted",
                    },
                },
                on_conflict="land_id,date"
            ).execute()

            # ─────────────────────────────────────
            # ESCALATION (MICRO TILE)
            # ─────────────────────────────────────
            escalate, reason = should_escalate(land, geo_conf, ndvi)

            if escalate:
                supabase.table("ndvi_micro_tiles").upsert(
                    {
                        "land_id": land["id"],
                        "farmer_id": land["farmer_id"],
                        "tenant_id": land["tenant_id"],
                        "bbox": geometry,
                        "acquisition_date": TODAY,
                        "ndvi_mean": ndvi["mean_ndvi"],
                        "ndvi_min": ndvi["ndvi_min"],
                        "ndvi_max": ndvi["ndvi_max"],
                        "statistics_only": True,
                        "resolution_meters": 10,
                    },
                    on_conflict="land_id,acquisition_date"
                ).execute()

            # ─────────────────────────────────────
            # LAND SNAPSHOT UPDATE
            # ─────────────────────────────────────
            supabase.table("lands").update(
                {
                    "last_ndvi_value": ndvi["mean_ndvi"],
                    "last_ndvi_calculation": TODAY,
                    "ndvi_tested": True,
                    "last_processed_at": "now()",
                }
            ).eq("id", land["id"]).execute()

        except Exception as e:
            print(f"❌ Land {land['id']} failed: {e}")


if __name__ == "__main__":
    run()
