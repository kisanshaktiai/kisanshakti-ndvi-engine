import os
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def fetch_active_lands(batch_size=500, offset=0):
    """
    Fetch active, non-deleted lands in paginated batches.
    Production-safe for large datasets.
    """

    resp = (
        supabase
        .table("lands")
        .select("*")
        .eq("is_active", True)
        .is_("deleted_at", "null")
        .order("created_at", desc=False)
        .range(offset, offset + batch_size - 1)
        .execute()
    )

    return resp.data or []
