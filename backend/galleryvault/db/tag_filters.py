from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import Select, or_, select
from sqlalchemy.sql.elements import ColumnElement

from .models import GalleryTag, Tag
from .repositories.base import escape_like_wildcards


def _tag_subquery(
    gallery_id_col: Any,
    namespace: str | None,
    name: str,
    tag_match: str = "exact",
    tag_id_map: Mapping[tuple[str | None, str], int] | None = None,
) -> Select:
    tag_id = None
    if tag_match == "exact" and tag_id_map:
        tag_id = tag_id_map.get((namespace, name))
        if tag_id is None and namespace is not None:
            tag_id = tag_id_map.get((namespace.strip(), name.strip()))
    if tag_id is not None:
        return (
            select(1)
            .select_from(GalleryTag)
            .where(
                GalleryTag.gallery_id == gallery_id_col,
                GalleryTag.tag_id == tag_id,
            )
        )
    escaped_name = escape_like_wildcards(name)
    pattern = escaped_name if tag_match == "exact" else f"%{escaped_name}%"
    condition = [Tag.name.ilike(pattern)]
    if namespace:
        condition.append(Tag.namespace == namespace)
    return (
        select(GalleryTag.gallery_id)
        .join(Tag, Tag.id == GalleryTag.tag_id)
        .where(GalleryTag.gallery_id == gallery_id_col, *condition)
    )


def build_tag_predicates(
    gallery_id_col: Any,
    tags: Sequence[tuple[str | None, str]] = (),
    exclude_tags: Sequence[tuple[str | None, str]] = (),
    tag_mode: str = "or",
    tag_match: str = "exact",
    tag_id_map: Mapping[tuple[str | None, str], int] | None = None,
) -> list[ColumnElement[bool]]:
    predicates: list[ColumnElement[bool]] = []
    if tags:
        tag_subqueries = [
            _tag_subquery(gallery_id_col, ns, name, tag_match=tag_match, tag_id_map=tag_id_map)
            for ns, name in tags
        ]
        if tag_mode == "and":
            predicates.extend(subquery.exists() for subquery in tag_subqueries)
        else:
            predicates.append(or_(*[subquery.exists() for subquery in tag_subqueries]))
    if exclude_tags:
        for ns, name in exclude_tags:
            subquery = _tag_subquery(
                gallery_id_col, ns, name, tag_match=tag_match, tag_id_map=tag_id_map
            )
            predicates.append(~subquery.exists())
    return predicates
