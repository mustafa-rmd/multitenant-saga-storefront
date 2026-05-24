"""Pagination class that emits our envelope shape."""

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.core.responses import envelope


class EnvelopePagination(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response(
            envelope(
                data=data,
                request=self.request,
                meta={
                    "pagination": {
                        "count": self.page.paginator.count,
                        "page": self.page.number,
                        "page_size": self.get_page_size(self.request),
                        "total_pages": self.page.paginator.num_pages,
                        "next": self.get_next_link(),
                        "previous": self.get_previous_link(),
                    },
                },
            )
        )
