"""
Settings Data Model
Integrates with the unified CMS configuration table (cms_configs) in PostgreSQL,
allowing seamless bidirectional synchronization between the JARVIS Settings UI,
the Settings REST API, and the future Admin Panel / CMS.
"""

from app.models.cms import CMSConfig

# Setting model mapping to cms_configs table
Setting = CMSConfig

__all__ = ["Setting", "CMSConfig"]
