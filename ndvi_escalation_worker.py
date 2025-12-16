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

# ─────────────────────────────────────────────
# ENV & CLIENT
# ─────────────────────────────────────────────
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

TODAY = date.today().isoformat()

BATCH_SIZE = 200  # safe for GitHub Actions + Supabase


# ─────────────────────────────────────────────
# GRID NDVI FETCH
# ─────────────────────────────────────────────
def fetch_grid_stats_for_land(land: dict):
    """
    Fetch real NDVI grid data using PostGIS overlap.
    RPC: get_land_ndvi_grids(land_id uuid, max_days_back int)
    """

    resp = supabase.rpc(
        "get_land_ndvi_grids",
        {
            "land_id": land["id"],
            "max_days_back": 7,
        }
    ).execute()

    return resp.data or []


# ─────────────────────────────────────────────
# MAIN WORKER
# ─────────────────────────────────────────────
def run():
    offset = 0
    total_processed = 0

    print("🚜 NDVI escalation worker started")

    while True:
        lands = fetch_active_lands(
            batch_size=BATCH_SIZE,
            offset=offset
        )

        if not lands:
            break

        print(f"📦 Processing batch offset={offset}, count={len(lands)}")

        for land in lands:
            land_id = land["id"]

            try:
                # 1️⃣ Resolve geometry (never skip)
                geometry, geo_conf = resolve_land_geometry(land)

                # 2️⃣ Fetch grid NDVI
                grid_cells = fetch_grid_stats_for_land(land)

                # ─────────────────────────────────
                # NDVI NOT READY (VALID STATE)
                # ─────────────────────────────────
                if not grid_cells:
                    supabase.table("lands").update(
                        {
                            "last_ndvi_calculation": TODAY,
                            "last_processed_at": "now()",
                            "ndvi_tested": False,
                        }
                    ).eq("id", land_id).execute()

                    print(f"⏳ NDVI pending (no grid data yet) for land {land_id}")
                    continue

                # 3️⃣ Aggregate NDVI
                ndvi = aggregate_ndvi_from_grids(grid_cells)
                confidence = ndvi_confidence_score(land, ndvi)

                # 4️⃣ NDVI DATA UPSERT (IDEMPOTENT)
                supabase.table("ndvi_data").upsert(
                    {
                        "land_id": land_id,
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
                    on_conflict="land_id,date",
                ).execute()

                # 5️⃣ Escalation (micro-tile)
                escalate, reason = should_escalate(land, geo_conf, ndvi)

                if escalate:
                    supabase.table("ndvi_micro_tiles").upsert(
                        {
                            "land_id": land_id,
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
                        on_conflict="land_id,acquisition_date",
                    ).execute()

                # 6️⃣ Update land snapshot
                supabase.table("lands").update(
                    {
                        "last_ndvi_value": ndvi["mean_ndvi"],
                        "last_ndvi_calculation": TODAY,
                        "ndvi_tested": True,
                        "last_processed_at": "now()",
                    }
                ).eq("id", land_id).execute()

                print(f"✅ NDVI computed for land {land_id}")
                total_processed += 1

            except Exception as e:
                # HARD RULE: never crash the batch
                print(f"❌ Land {land_id} failed safely: {e}")

        offset += BATCH_SIZE

    print(f"✅ NDVI escalation worker finished. Lands processed: {total_processed}")


# ─────────────────────────────────────────────
if __name__ == "__main__":
    run()
