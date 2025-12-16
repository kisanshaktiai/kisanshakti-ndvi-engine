import os
import numpy as np
from datetime import date, timedelta
from supabase import create_client
from pystac_client import Client
import planetary_computer
import rasterio
from rasterio.mask import mask

# ─────────────────────────────────────────────
# ENV & CLIENTS
# ─────────────────────────────────────────────
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "sentinel-2-l2a"

stac = Client.open(STAC_URL)

MAX_CLOUD = 30
LOOKBACK_DAYS = 5

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def fetch_active_tiles(limit=50):
    """
    Fetch agricultural Sentinel tiles that need NDVI processing.
    """
    resp = (
        supabase
        .table("satellite_tiles")
        .select("id, tile_id, bbox, last_processed_at")
        .limit(limit)
        .execute()
    )
    return resp.data or []


def search_sentinel_item(tile_bbox):
    """
    Search Sentinel-2 scene for tile bbox.
    """
    start = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    end = date.today().isoformat()

    search = stac.search(
        collections=[COLLECTION],
        bbox=tile_bbox,
        datetime=f"{start}/{end}",
        query={"eo:cloud_cover": {"lt": MAX_CLOUD}},
        limit=1
    )

    items = list(search.get_items())
    return planetary_computer.sign(items[0]) if items else None


def compute_ndvi(item):
    """
    Compute NDVI statistics from Sentinel-2 bands.
    """
    with rasterio.open(item.assets["B08"].href) as nir, \
         rasterio.open(item.assets["B04"].href) as red:

        nir_data = nir.read(1).astype("float32")
        red_data = red.read(1).astype("float32")

        ndvi = (nir_data - red_data) / (nir_data + red_data + 1e-6)
        ndvi = np.clip(ndvi, -1, 1)

        valid = np.isfinite(ndvi)

        if valid.sum() < 50:
            return None

        return {
            "mean": float(np.mean(ndvi[valid])),
            "min": float(np.min(ndvi[valid])),
            "max": float(np.max(ndvi[valid])),
            "std": float(np.std(ndvi[valid])),
            "histogram": np.histogram(ndvi[valid], bins=10, range=(-1, 1))[0].tolist()
        }


def classify_zones(hist):
    """
    Very lightweight vegetation zoning.
    """
    return {
        "bare": hist[0:2],
        "stressed": hist[2:4],
        "healthy": hist[4:7],
        "dense": hist[7:10]
    }

# ─────────────────────────────────────────────
# MAIN CRON
# ─────────────────────────────────────────────

def run():
    tiles = fetch_active_tiles()

    for tile in tiles:
        try:
            item = search_sentinel_item(tile["bbox"])
            if not item:
                print(f"⚠️ No Sentinel data for tile {tile['tile_id']}")
                continue

            ndvi = compute_ndvi(item)
            if not ndvi:
                print(f"⚠️ Insufficient NDVI pixels for tile {tile['tile_id']}")
                continue

            zones = classify_zones(ndvi["histogram"])

            supabase.table("ndvi_spatial_analytics").upsert({
                "satellite_tile_id": tile["id"],
                "region_name": tile["tile_id"],
                "bbox": tile["bbox"],
                "ndvi_histogram": ndvi["histogram"],
                "vegetation_zones": zones,
                "temporal_comparison": {
                    "mean_ndvi": ndvi["mean"]
                },
                "anomaly_detection": {},
                "quality_flags": {
                    "cloud_filter": MAX_CLOUD
                }
            }).execute()

            supabase.table("satellite_tiles").update({
                "last_processed_at": "now()"
            }).eq("id", tile["id"]).execute()

            print(f"✅ Tile {tile['tile_id']} NDVI processed")

        except Exception as e:
            print(f"❌ Tile {tile['tile_id']} failed: {e}")

if __name__ == "__main__":
    run()
