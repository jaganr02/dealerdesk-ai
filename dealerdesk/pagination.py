"""
Standard pagination classes for DealerDesk according to API_CONTRACT.md.
"""

from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """
    Standard contract pagination:
    - Default page_size: 20
    - Query parameter: page_size (max 100)
    - Page query parameter: page (1-based)
    - Shape: {"count": 123, "next": "...", "previous": null, "results": [...]}
    """
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    page_query_param = "page"
