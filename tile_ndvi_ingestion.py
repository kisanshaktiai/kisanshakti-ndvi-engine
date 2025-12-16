# tile_ndvi_ingestion.py
# -------------------------------------------------
# Sentinel-2 → Tile NDVI ingestion
# Microsoft Planetary Computer
# -------------------------------------------------

import os
from datetime import datetime, timedelta
import numpy as np
import pystac_client
import rasterio
from rasterio.mask import mask
from supabase import create_client

# ────────────────────────────────────────────────
# ENV
# ────────────────────────────────────────────────
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ────────────────────────────────────────────────
# CONFIG
# ────────────────────────────────────────────────
DAYS_BACK = 7
NDVI_BINS = np.linspace(-1.0, 1.0, 21)
COLLECTION = "sentinel-2-l2a"

# ────────────────────────────────────────────────
# MPC STAC
# ────────────────────────────────────────────────
stac = pystac_client.Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1"
)

# ────────────────────────────────────────────────
# HELPERS
# ────────────────────────────────────────────────
def cloud_mask(scl):
    """
    Keep vegetation, bare soil, water
    Mask clouds, shadows, cirrus
    """
    return np.isin(scl, [4, 5, 6])


def compute_ndvi(red, nir):
    np.seterr(divide="ignore", invalid="ignore")
    return (nir - red) / (nir + red)


# ────────────────────────────────────────────────
# FETCH AGRICULTURAL TILES
# ────────────────────────────────────────────────
def fetch_agri_tiles(limit=50):
    resp = (
        supabase
        .table("mgrs_tiles")
        .select("id, tile_id, geometry")
        .eq("is_agri", True)
        .eq("is_land_contain", True)
        .order("last_ndvi_update", desc=False)
        .limit(limit)
        .execute()
    )
    return resp.data or []


# ────────────────────────────────────────────────
# PROCESS SINGLE TILE
# ────────────────────────────────────────────────
def process_tile(tile):
    tile_id = tile["tile_id"]
    geom = tile["geometry"]

    start = (datetime.utcnow() - timedelta(days=DAYS_BACK)).date().isoformat()
    end = datetime.utcnow().date().isoformat()

    search = stac.search(
        collections=[COLLECTION],
        datetime=f"{start}/{end}",
        query={"mgrs:tile": {"eq": tile_id}},
        max_items=3,
    )

    items = list(search.items())

    if not items:
        return None

    ndvi_values = []

    for item in items:
        try:
            red_href = item.assets["B04"].href
            nir_href = item.assets["B08"].href
            scl_href = item.assets["SCL"].href

            with rasterio.open(red_href) as red_src, \
                 rasterio.open(nir_href) as nir_src, \
                 rasterio.open(scl_href) as scl_src:

                red, _ = mask(red_src, [geom], crop=True)
                nir, _ = mask(nir_src, [geom], crop=True)
                scl, _ = mask(scl_src, [geom], crop=True)

                valid = cloud_mask(scl[0])
                ndvi = compute_ndvi(red[0], nir[0])

                ndvi = ndvi[valid]
                ndvi = ndvi[~np.isnan(ndvi)]

                if ndvi.size > 0:
                    ndvi_values.extend(ndvi.tolist())

        except Exception:
            continue

    if not ndvi_values:
        return None

    ndvi_arr = np.array(ndvi_values)

    hist, bins = np.histogram(ndvi_arr, bins=NDVI_BINS)

    return {
        "mean": float(np.mean(ndvi_arr)),
        "min": float(np.min(ndvi_arr)),
        "max": float(np.max(ndvi_arr)),
        "std": float(np.std(ndvi_arr)),
        "histogram": {
            "bins": bins.tolist(),
            "counts": hist.tolist(),
        },
    }


# ────────────────────────────────────────────────
# MAIN RUNNER
# ────────────────────────────────────────────────
def run():
    print("🌍 Tile NDVI ingestion started")

    tiles = fetch_agri_tiles()

    for tile in tiles:
        try:
            stats = process_tile(tile)

            if not stats:
                continue

            supabase.table("ndvi_spatial_analytics").insert({
                "satellite_tile_id": tile["id"],
                "region_name": tile["tile_id"],
                "bbox": tile["geometry"],
                "ndvi_histogram": stats["histogram"],
                "processed_at": datetime.utcnow().isoformat(),
            }).execute()

            supabase.table("mgrs_tiles").update({
                "is_ndvi_ready": True,
                "last_ndvi_update": datetime.utcnow().isoformat(),
            }).eq("id", tile["id"]).execute()

            print(f"✅ NDVI computed for tile {tile['tile_id']}")

        except Exception as e:
            print(f"❌ Tile {tile['tile_id']} failed: {e}")

    print("🏁 Tile NDVI ingestion finished")


if __name__ == "__main__":
    run()
