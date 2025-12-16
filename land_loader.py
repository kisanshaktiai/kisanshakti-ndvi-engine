import os
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def fetch_active_lands(batch_size=500):
    """
    Fetch active, non-deleted lands.
    """
    resp = (
        supabase
        .table("lands")
        .select("*")
        .eq("is_active", True)
        .is_("deleted_at", None)
        .limit(batch_size)
        .execute()
    )
    return resp.data or []
