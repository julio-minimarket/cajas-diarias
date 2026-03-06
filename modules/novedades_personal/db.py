"""
modules/novedades_personal/db.py
================================
Conexión centralizada a Supabase.
Usa st.secrets igual que el resto del sistema Cajas Diarias.
"""

import streamlit as st
from supabase import create_client, Client

_supabase_client: Client | None = None


def get_supabase() -> Client:
    """
    Devuelve el cliente Supabase (singleton).
    Usa SUPABASE_KEY (service_role key) igual que los demás módulos.
    """
    global _supabase_client
    if _supabase_client is None:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        _supabase_client = create_client(url, key)
    return _supabase_client
